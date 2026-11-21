"""Bounded, synchronous model/tool interaction."""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from time import monotonic
from typing import Literal

from research_agent.llm.base import BaseLLM, LLMError, LLMTimeoutError, Message, ToolCall
from research_agent.tools.base import ToolResult
from research_agent.tools.registry import ToolRegistry

type StopReason = Literal["completed", "max_steps", "max_tool_calls", "timeout", "model_error"]


@dataclass(frozen=True)
class ToolEvent:
    step: int
    call: ToolCall
    result: ToolResult


@dataclass(frozen=True)
class AgentResult:
    reason: StopReason
    answer: str
    steps: int
    history: tuple[Message, ...]
    events: tuple[ToolEvent, ...]
    error: str | None = None


class AgentEngine:
    def __init__(self, llm: BaseLLM, tools: ToolRegistry, *, max_steps: int = 6,
                 max_tool_calls: int = 12, timeout: float = 120):
        if max_steps < 1 or max_tool_calls < 1 or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Agent budgets must be positive")
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.timeout = timeout

    def run(self, messages: Sequence[Message]) -> AgentResult:
        history = list(messages)
        events: list[ToolEvent] = []
        deadline = monotonic() + self.timeout
        specs = self.tools.specs()
        steps = 0

        def finish(reason: StopReason, answer: str = "", error: str | None = None) -> AgentResult:
            return AgentResult(reason, answer, steps, tuple(history), tuple(events), error)

        while steps < self.max_steps:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return finish("timeout")
            steps += 1
            try:
                response = self.llm.chat(tuple(history), tools=specs, timeout=remaining)
            except LLMTimeoutError as error:
                return finish("timeout", error=str(error))
            except (LLMError, ValueError) as error:
                return finish("model_error", error=str(error))
            if monotonic() >= deadline:
                return finish("timeout")
            message = response.message
            if not response.done or message.role != "assistant" or response.finish_reason == "length":
                return finish("model_error", error="Model response was incomplete")
            history.append(message)
            if not message.tool_calls:
                if message.content.strip():
                    return finish("completed", message.content)
                return finish("model_error", error="Model returned an empty response")
            # Leave a model turn available to consume all results.
            if steps == self.max_steps:
                return finish("max_steps")
            if len(events) + len(message.tool_calls) > self.max_tool_calls:
                return finish("max_tool_calls")
            for call in message.tool_calls:
                if monotonic() >= deadline:
                    return finish("timeout")
                result = self.tools.dispatch(call)
                events.append(ToolEvent(steps, call, result))
                history.append(Message("tool", json.dumps(result.as_dict(), ensure_ascii=False,
                                                          allow_nan=False), tool_name=call.name))
        return finish("max_steps")
