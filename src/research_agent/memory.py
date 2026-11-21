"""SQLite storage for plans, task checkpoints and conversation messages."""

import json
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from research_agent.agent.executor import TaskState
from research_agent.agent.planning import TaskManager
from research_agent.llm.base import JsonObject, Message, ToolCall

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    plan TEXT NOT NULL,
    options TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS task_states (
    run_id TEXT NOT NULL REFERENCES runs(id),
    task_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'blocked')),
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    data TEXT,
    error TEXT,
    PRIMARY KEY (run_id, task_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_run ON messages(run_id, id);
"""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True)
class RunRecord:
    id: str
    topic: str
    plan: TaskManager
    options: JsonObject
    created_at: str


class TaskMemory:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db

    def create(self, topic: str, plan: TaskManager, options: JsonObject | None = None) -> str:
        run_id = uuid4().hex
        with self._connect() as db:
            db.execute("INSERT INTO runs (id, topic, plan, options) VALUES (?, ?, ?, ?)",
                       (run_id, topic, _json(plan.as_dict()), _json(options or {})))
        return run_id

    def load(self, run_id: str) -> RunRecord:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown run: {run_id}")
        return RunRecord(row["id"], row["topic"], TaskManager.from_dict(json.loads(row["plan"])),
                         json.loads(row["options"]), row["created_at"])

    def list_runs(self, limit: int = 20) -> list[JsonObject]:
        with self._connect() as db:
            rows = db.execute("""
                SELECT runs.id, topic, created_at, plan,
                       COUNT(task_id) AS started,
                       SUM(CASE WHEN status <> 'running' THEN 1 ELSE 0 END) AS finished,
                       SUM(CASE WHEN status IN ('failed', 'blocked') THEN 1 ELSE 0 END) AS issues
                FROM runs LEFT JOIN task_states ON runs.id = run_id
                GROUP BY runs.id ORDER BY runs.rowid DESC LIMIT ?
            """, (limit,)).fetchall()
        return [{
            "id": row["id"], "topic": row["topic"], "created_at": row["created_at"],
            "started": row["started"], "finished": row["finished"], "issues": row["issues"],
            "total": len(json.loads(row["plan"])["tasks"]),
        } for row in rows]

    def states(self, run_id: str) -> dict[str, TaskState]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM task_states WHERE run_id=?", (run_id,)).fetchall()
        return {
            row["task_id"]: TaskState(row["status"], row["attempts"],
                                      json.loads(row["data"]) if row["data"] is not None else None,
                                      row["error"])
            for row in rows
        }

    def checkpoint(self, run_id: str, task_id: str, state: TaskState,
                   *, messages: tuple[Message, ...] = ()) -> None:
        with self._connect() as db:
            db.execute("""
                INSERT INTO task_states VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, task_id) DO UPDATE SET
                    status=excluded.status, attempts=excluded.attempts,
                    data=excluded.data, error=excluded.error
            """, (run_id, task_id, state.status, state.attempts,
                  _json(state.data) if state.data is not None else None, state.error))
            self._write_messages(db, run_id, messages)

    def append_messages(self, run_id: str, messages: tuple[Message, ...]) -> None:
        with self._connect() as db:
            self._write_messages(db, run_id, messages)

    @staticmethod
    def _write_messages(db: sqlite3.Connection, run_id: str, messages: tuple[Message, ...]) -> None:
        db.executemany("INSERT INTO messages (run_id, message) VALUES (?, ?)",
                       ((run_id, _json(asdict(message))) for message in messages))

    def messages(self, run_id: str) -> tuple[Message, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT message FROM messages WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        messages = []
        for row in rows:
            data = json.loads(row["message"])
            data["tool_calls"] = tuple(ToolCall(**call) for call in data["tool_calls"])
            messages.append(Message(**data))
        return tuple(messages)

    @contextmanager
    def claim(self, run_id: str) -> Iterator[None]:
        """Hold a process-released, non-blocking lock for a known run."""
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("Invalid run ID")
        self.load(run_id)
        lock_dir = self.path.with_name(self.path.name + ".locks")
        lock_dir.mkdir(exist_ok=True)
        with (lock_dir / run_id).open("a+b", buffering=0) as lock:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ValueError(f"Run {run_id} is already active or could not be locked") from error
            yield
