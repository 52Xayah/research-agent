"""Register tools, validate requests and dispatch calls."""

import json
import logging
import re

from research_agent.llm.base import ToolCall, ToolSpec
from research_agent.parameters import InvalidArguments, validate_arguments
from research_agent.tools.base import BaseTool, ToolError, ToolFailure, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", tool.name):
            raise ValueError("Tool names must be lowercase identifiers of up to 64 characters")
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.spec() for tool in self._tools.values())

    def dispatch(self, call: ToolCall) -> ToolResult:
        tool = self.get(call.name)
        if tool is None:
            return ToolResult(call.name, error=ToolFailure("unknown_tool", "Tool is not registered"))
        try:
            validate_arguments(tool.parameters, call.arguments)
        except InvalidArguments as error:
            return ToolResult(tool.name, error=ToolFailure("invalid_arguments", str(error)))
        try:
            data = tool.execute(**call.arguments)
            if not isinstance(data, dict):
                raise TypeError("Tool results must be JSON objects")
            json.dumps(data, allow_nan=False)
        except ToolError as error:
            return ToolResult(tool.name, error=ToolFailure(error.code, str(error)))
        except Exception as error:
            logger.warning("Tool %s failed: %s", tool.name, type(error).__name__)
            return ToolResult(tool.name, error=ToolFailure("execution_error", "Tool execution failed"))
        return ToolResult(tool.name, data=data)
