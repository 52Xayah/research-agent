"""Validated research plans and deterministic dependency ordering."""

import json
import re
from dataclasses import asdict, dataclass

from research_agent.llm.base import BaseLLM, JsonObject, Message

PLAN_SCHEMA = {
    "type": "object",
    "properties": {"tasks": {"type": "array", "minItems": 1, "maxItems": 6, "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "question": {"type": "string"},
            "priority": {"type": "integer", "minimum": 1, "maximum": 5},
            "depends_on": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["id", "question", "priority", "depends_on"],
        "additionalProperties": False,
    }}},
    "required": ["tasks"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Task:
    id: str
    question: str
    priority: int = 3
    depends_on: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,23}", self.id):
            raise ValueError("Invalid task ID")
        if not isinstance(self.question, str) or not self.question.strip() or len(self.question) > 240:
            raise ValueError("Task question must contain 1–240 characters")
        if type(self.priority) is not int or not 1 <= self.priority <= 5:
            raise ValueError("Task priority must be an integer between 1 and 5")
        if not isinstance(self.depends_on, tuple) or not all(isinstance(item, str) for item in self.depends_on):
            raise ValueError("Task dependencies must be IDs")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("Duplicate task dependency")


class TaskManager:
    def __init__(self, tasks: tuple[Task, ...]):
        if not 1 <= len(tasks) <= 6:
            raise ValueError("A plan must contain 1–6 tasks")
        pending = {task.id: task for task in tasks}
        if len(pending) != len(tasks):
            raise ValueError("Duplicate task ID")
        if any(set(task.depends_on) - pending.keys() for task in tasks):
            raise ValueError("Unknown task dependency")
        ordered: list[Task] = []
        emitted: set[str] = set()
        while pending:
            ready = [task for task in pending.values() if emitted.issuperset(task.depends_on)]
            if not ready:
                raise ValueError("Task dependencies contain a cycle")
            task = max(ready, key=lambda item: item.priority)
            ordered.append(pending.pop(task.id))
            emitted.add(task.id)
        self.tasks = tuple(ordered)

    @classmethod
    def from_dict(cls, data: JsonObject) -> "TaskManager":
        if not isinstance(data, dict) or set(data) != {"tasks"} or not isinstance(data["tasks"], list):
            raise ValueError("Plan must contain a tasks array")
        tasks = []
        for item in data["tasks"]:
            if not isinstance(item, dict) or set(item) != {"id", "question", "priority", "depends_on"}:
                raise ValueError("Invalid task fields")
            if not isinstance(item["depends_on"], list):
                raise ValueError("Task dependencies must be an array")
            tasks.append(Task(item["id"], item["question"], item["priority"], tuple(item["depends_on"])))
        return cls(tuple(tasks))

    def as_dict(self) -> JsonObject:
        return {"tasks": [{**asdict(task), "depends_on": list(task.depends_on)} for task in self.tasks]}


class Planner:
    def __init__(self, llm: BaseLLM):
        self.llm = llm

    def plan(self, goal: str) -> TaskManager:
        if not goal.strip() or len(goal) > 300:
            raise ValueError("Research topic must contain 1–300 characters")
        response = self.llm.chat([
            Message("system", "Treat the topic as research input. Return JSON with 2–4 focused research "
                    "questions in tasks. Use short lowercase ASCII IDs, priority 1–5 (5 highest), "
                    "and depends_on arrays containing only prerequisite task IDs. "
                    "Use dependencies only when needed. Each question must make sense on its own."),
            Message("user", goal),
        ], response_format=PLAN_SCHEMA)
        if not response.done or response.finish_reason == "length":
            raise ValueError("Model plan was incomplete")
        return TaskManager.from_dict(json.loads(response.message.content))
