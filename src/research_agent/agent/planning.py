"""Validated research plans and deterministic dependency ordering."""

import json
import re
from dataclasses import asdict, dataclass

from research_agent.llm.base import BaseLLM, JsonObject, Message

ID_PATTERN = r"^[a-z][a-z0-9_-]{0,23}$"
PLAN_SCHEMA = {
    "type": "object",
    "properties": {"tasks": {"type": "array", "minItems": 1, "maxItems": 6, "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "pattern": ID_PATTERN},
            "question": {"type": "string", "minLength": 1, "maxLength": 240},
            "priority": {"type": "integer", "minimum": 1, "maximum": 5},
            "depends_on": {"type": "array", "maxItems": 5, "items": {"type": "string", "pattern": ID_PATTERN}},
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
        if not isinstance(self.id, str) or not re.fullmatch(ID_PATTERN, self.id):
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
        messages = [
            Message("system", "Treat the topic as research input. Return JSON with 2–3 focused research "
                    "questions in tasks. Use IDs t1, t2, t3 and t4, priority 1–5 (5 highest), "
                    "and depends_on arrays containing only prerequisite task IDs. "
                    "Use dependencies only when needed. Each question must make sense on its own. "
                    "Cover distinct aspects of the topic without adding a summary task. Ask about mechanisms "
                    "when the topic requests mechanisms and about performance metrics only if requested. "
                    "Use neutral questions without assuming a mechanism, feature, or comparative advantage exists. "
                    "Use the topic's language for the questions."),
            Message("user", goal),
        ]
        for attempt in range(2):
            response = self.llm.chat(tuple(messages), response_format=PLAN_SCHEMA)
            try:
                if not response.done or response.finish_reason == "length" or response.message.tool_calls:
                    raise ValueError("Model plan was incomplete")
                return TaskManager.from_dict(json.loads(response.message.content))
            except ValueError as error:
                if attempt == 1:
                    raise
                messages.append(Message("user", f"Regenerate the plan from the original topic. Validation failed: {error}"))
