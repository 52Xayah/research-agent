"""Run ordered tasks with bounded retries and checkpoint notifications."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from research_agent.agent.planning import Task, TaskManager
from research_agent.llm.base import JsonObject

type TaskStatus = Literal["running", "succeeded", "failed", "blocked"]


class TaskFailure(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class TaskState:
    status: TaskStatus
    attempts: int = 0
    data: JsonObject | None = None
    error: str | None = None


type TaskHandler = Callable[[Task, Mapping[str, JsonObject]], JsonObject]
type Checkpoint = Callable[[str, TaskState], None]


class Executor:
    def __init__(self, max_attempts: int = 2):
        if not 1 <= max_attempts <= 3:
            raise ValueError("Task attempts must be between 1 and 3")
        self.max_attempts = max_attempts

    def run(
        self,
        plan: TaskManager,
        handler: TaskHandler,
        *,
        previous: Mapping[str, TaskState] | None = None,
        checkpoint: Checkpoint | None = None,
    ) -> dict[str, TaskState]:
        states = dict(previous or {})

        def save(task_id: str, state: TaskState) -> None:
            if checkpoint is not None:
                checkpoint(task_id, state)
            states[task_id] = state

        for task in plan.tasks:
            prior = states.get(task.id)
            if prior and prior.status != "running":
                continue
            attempts = prior.attempts if prior else 0
            if any(states[dependency].status != "succeeded" for dependency in task.depends_on):
                save(task.id, TaskState("blocked", attempts, error="A prerequisite did not succeed"))
                continue
            if attempts >= self.max_attempts:
                save(task.id, TaskState("failed", attempts, error="Interrupted after using all attempts"))
                continue
            inputs = {dependency: states[dependency].data for dependency in task.depends_on}
            for attempt in range(attempts + 1, self.max_attempts + 1):
                save(task.id, TaskState("running", attempt))
                try:
                    output = handler(task, inputs)
                except TaskFailure as error:
                    if error.retryable and attempt < self.max_attempts:
                        continue
                    save(task.id, TaskState("failed", attempt, error=str(error)))
                else:
                    save(task.id, TaskState("succeeded", attempt, data=output))
                break
        return states
