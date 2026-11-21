"""Shared tool protocol and results."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from research_agent.llm.base import JsonObject, ToolSpec
from research_agent.parameters import Parameter, parameter_schema


class ToolError(Exception):
    """A tool failure with a code and message safe to return to the caller."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ToolFailure:
    code: str
    message: str


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    data: JsonObject | None = None
    error: ToolFailure | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def as_dict(self) -> JsonObject:
        if self.error is not None:
            return {
                "tool": self.tool_name,
                "ok": False,
                "error": {"code": self.error.code, "message": self.error.message},
            }
        return {"tool": self.tool_name, "ok": True, "data": self.data}


class BaseTool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    parameters: ClassVar[Mapping[str, Parameter]]

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, parameter_schema(self.parameters))

    @abstractmethod
    def execute(self, **arguments) -> JsonObject:
        """Execute with validated arguments and return JSON data."""
