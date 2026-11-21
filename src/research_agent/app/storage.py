"""Persistent job tickets and isolated uploaded documents."""

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path, PureWindowsPath
from typing import BinaryIO
from uuid import uuid4

from research_agent.rag.documents import MAX_FILE_BYTES
from research_agent.security import open_authorized

JOB_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    options TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','running','completed','partial','failed','interrupted')),
    run_id TEXT,
    report TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    bytes INTEGER NOT NULL
);
"""
ID = re.compile(r"[a-f0-9]{32}")


class QueueFull(ValueError):
    """The local worker queue is full."""


def document_name(name: str) -> str:
    if (not 1 <= len(name) <= 100 or name != name.strip() or name.startswith(".")
            or any(not char.isprintable() or char in '<>:"/\\|?*' for char in name)
            or PureWindowsPath(name).is_reserved()
            or Path(name).suffix.lower() not in {".txt", ".md", ".pdf"}):
        raise ValueError("Use a simple TXT, Markdown or PDF filename")
    return name


class AppStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "jobs.sqlite3"
        with self.connect() as db:
            db.executescript(JOB_SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db

    @contextmanager
    def upload(self, name: str) -> Iterator[tuple[str, BinaryIO]]:
        name = document_name(name)
        key = uuid4().hex
        folder = self.root / "uploads" / key
        folder.mkdir(parents=True)
        path = folder / name
        complete = False
        try:
            with path.open("xb") as handle:
                yield key, handle
                size = handle.tell()
            if not 0 < size <= MAX_FILE_BYTES:
                raise ValueError("Document size must be between 1 byte and 12 MiB")
            with self.connect() as db:
                db.execute("INSERT INTO uploads VALUES (?, ?, ?)", (key, name, size))
            complete = True
        finally:
            if not complete:
                path.unlink(missing_ok=True)
                folder.rmdir()

    def documents(self, keys: list[str]) -> list[dict]:
        if len(keys) > 8 or len(set(keys)) != len(keys) or not all(ID.fullmatch(key) for key in keys):
            raise ValueError("Provide up to eight distinct uploaded document IDs")
        with self.connect() as db:
            items = [db.execute("SELECT * FROM uploads WHERE id=?", (key,)).fetchone() for key in keys]
        if any(row is None for row in items):
            raise ValueError("An uploaded document ID was not found")
        documents = [dict(row) for row in items]
        if sum(doc["bytes"] for doc in documents) > 32 * 1024 * 1024:
            raise ValueError("Documents exceed the 32 MiB limit per job")
        if len({doc["name"].casefold() for doc in documents}) != len(documents):
            raise ValueError("Document filenames must be distinct within a job")
        return documents

    def stage(self, job_id: str, documents: list[dict]) -> Path | None:
        if not documents:
            return None
        root = self.root / "sources" / job_id
        root.mkdir(parents=True, exist_ok=True)
        for doc in documents:
            name = document_name(doc["name"])
            source = self.root / "uploads" / doc["id"]
            with open_authorized(source, source / name) as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
            if len(data) != doc["bytes"]:
                raise ValueError("An uploaded document changed or is unavailable")
            (root / name).write_bytes(data)
        return root

    def interrupt_pending(self) -> None:
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='interrupted' WHERE status IN ('queued','running')")

    def enqueue(self, topic: str, options: dict) -> str:
        key = uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._check_capacity(db)
            db.execute("INSERT INTO jobs (id, topic, options, status) VALUES (?, ?, ?, 'queued')",
                       (key, topic, json.dumps(options, ensure_ascii=False)))
        return key

    def resume(self, key: str) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._check_capacity(db)
            cursor = db.execute("UPDATE jobs SET status='queued', error=NULL WHERE id=? AND status='interrupted'",
                                (key,))
            if cursor.rowcount != 1:
                raise ValueError("Only interrupted jobs can be resumed")

    @staticmethod
    def _check_capacity(db: sqlite3.Connection) -> None:
        if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= 4:
            raise QueueFull("The local worker queue is full. Try again when a job finishes.")

    def update(self, key: str, status: str, *, run_id: str | None = None,
               report: str | None = None, error: str | None = None) -> None:
        with self.connect() as db:
            db.execute("""
                UPDATE jobs SET status=?, run_id=coalesce(?, run_id), report=coalesce(?, report), error=?
                WHERE id=?
            """, (status, run_id, report, error, key))

    def get(self, key: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        job = dict(row)
        job["options"] = json.loads(job["options"])
        return job

    def list_jobs(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT id, topic, status, created_at FROM jobs ORDER BY rowid DESC LIMIT 50").fetchall()
        return [dict(row) for row in rows]
