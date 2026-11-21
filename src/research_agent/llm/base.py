"""Provider-neutral language model messages and interface."""

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal

type JsonObject = dict[str, Any]
type Role = Literal["system", "user", "assistant", "tool"]


class LLMError(Exception):
    """A model request failed."""


class LLMTimeoutError(LLMError):
    """The model service exceeded a network operation timeout."""


class LLMTransportError(LLMError):
    """The model service could not complete the HTTP exchange."""


class LLMProtocolError(LLMError):
    """The model service returned invalid or incomplete data."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: JsonObject


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: JsonObject
    index: int | None = None


@dataclass(frozen=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_name: str | None = None


@dataclass(frozen=True)
class ChatResponse:
    message: Message
    done: bool
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class BaseLLM(ABC):
    @abstractmethod
    def chat(
        self,
        messages: Sequence[Message],
        *,
        response_format: JsonObject | Literal["json"] | None = None,
        tools: Sequence[ToolSpec] = (),
        timeout: float | None = None,
    ) -> ChatResponse:
        """Return the next assistant message, with optional tool calls."""

    @abstractmethod
    def stream(self, messages: Sequence[Message]) -> Iterator[ChatResponse]:
        """Yield assistant text fragments and a terminal response."""
