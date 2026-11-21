"""Transport for Ollama's native chat endpoint."""

import json
from collections.abc import Iterator, Sequence
from typing import Any
from urllib.request import Request, urlopen

from research_agent.config import OllamaSettings


class OllamaClient:
    def __init__(self, settings: OllamaSettings):
        self.settings = settings

    def _request(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        stream: bool,
        response_format: dict[str, Any] | str | None,
        tools: Sequence[dict[str, Any]],
    ) -> Request:
        payload = {
            "model": self.settings.model,
            "messages": list(messages),
            "stream": stream,
            "think": False,
            "options": {
                "num_ctx": self.settings.context,
                "num_predict": self.settings.max_output,
                "temperature": 0,
            },
        }
        if response_format is not None:
            payload["format"] = response_format
        if tools:
            payload["tools"] = list(tools)
        return Request(
            f"{self.settings.url.rstrip('/')}/api/chat",
            data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def chat(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        response_format: dict[str, Any] | str | None = None,
        tools: Sequence[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        request = self._request(messages, stream=False, response_format=response_format, tools=tools)
        with urlopen(request, timeout=self.settings.timeout) as response:
            return json.load(response)

    def stream(self, messages: Sequence[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        request = self._request(messages, stream=True, response_format=None, tools=())
        with urlopen(request, timeout=self.settings.timeout) as response:
            for line in response:
                if line.strip():
                    yield json.loads(line)
