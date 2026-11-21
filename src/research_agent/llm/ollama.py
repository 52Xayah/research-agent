"""Map normalized language model messages to Ollama's native protocol."""

from collections.abc import Iterator, Sequence
from contextlib import closing
from typing import Literal

from research_agent.config import OllamaSettings
from research_agent.llm.base import (
    BaseLLM,
    ChatResponse,
    JsonObject,
    LLMProtocolError,
    Message,
    ToolCall,
    ToolSpec,
)
from research_agent.llm.client import OllamaClient


class OllamaLLM(BaseLLM):
    def __init__(self, settings: OllamaSettings):
        self.settings = settings
        self.client = OllamaClient(settings)

    def chat(
        self,
        messages: Sequence[Message],
        *,
        response_format: JsonObject | Literal["json"] | None = None,
        tools: Sequence[ToolSpec] = (),
        timeout: float | None = None,
    ) -> ChatResponse:
        result = self.client.chat(
            [_encode_message(message) for message in messages],
            response_format=response_format,
            timeout=timeout,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.parameters,
                    },
                }
                for spec in tools
            ],
        )
        return _decode_response(result)

    def stream(self, messages: Sequence[Message]) -> Iterator[ChatResponse]:
        with closing(self.client.stream([_encode_message(message) for message in messages])) as chunks:
            for item in chunks:
                yield _decode_response(item, streaming=True)


def _encode_message(message: Message) -> JsonObject:
    data: JsonObject = {"role": message.role, "content": message.content}
    if message.tool_name is not None:
        data["tool_name"] = message.tool_name
    if message.tool_calls:
        calls = []
        for call in message.tool_calls:
            function = {"name": call.name, "arguments": call.arguments}
            if call.index is not None:
                function["index"] = call.index
            calls.append({"type": "function", "function": function})
        data["tool_calls"] = calls
    return data


def _decode_call(raw: object) -> ToolCall:
    if not isinstance(raw, dict) or not isinstance(raw.get("function"), dict):
        raise LLMProtocolError("Ollama returned a malformed tool call")
    function = raw["function"]
    name = function.get("name")
    arguments = function.get("arguments")
    index = function.get("index")
    if not isinstance(name, str) or not name or not isinstance(arguments, dict):
        raise LLMProtocolError("Ollama tool calls require a name and an arguments object")
    if index is not None and (type(index) is not int or index < 0):
        raise LLMProtocolError("Ollama returned an invalid tool call index")
    return ToolCall(name, arguments, index)


def _decode_response(data: JsonObject, *, streaming: bool = False) -> ChatResponse:
    done = data.get("done")
    raw = data.get("message")
    if raw is None and streaming and done is True:
        raw = {"role": "assistant", "content": ""}
    if type(done) is not bool or not isinstance(raw, dict) or raw.get("role") != "assistant":
        raise LLMProtocolError("Ollama returned an invalid assistant response")
    content = raw.get("content", "")
    tool_calls = raw.get("tool_calls", [])
    if not isinstance(content, str) or not isinstance(tool_calls, list):
        raise LLMProtocolError("Ollama returned invalid assistant content or tool calls")
    if "content" not in raw and not tool_calls:
        raise LLMProtocolError("Ollama assistant response omitted its content")
    finish_reason = data.get("done_reason")
    if finish_reason is not None and not isinstance(finish_reason, str):
        raise LLMProtocolError("Ollama returned an invalid finish reason")
    return ChatResponse(
        message=Message("assistant", content, tuple(_decode_call(item) for item in tool_calls)),
        done=done,
        finish_reason=finish_reason,
        input_tokens=_token_count(data, "prompt_eval_count"),
        output_tokens=_token_count(data, "eval_count"),
    )


def _token_count(data: JsonObject, key: str) -> int | None:
    count = data.get(key)
    if count is not None and (type(count) is not int or count < 0):
        raise LLMProtocolError(f"Ollama returned an invalid {key}")
    return count
