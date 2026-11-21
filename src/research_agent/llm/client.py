"""Transport for Ollama's native chat endpoint."""

import json
import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from http.client import HTTPException, HTTPResponse
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from research_agent.config import OllamaSettings
from research_agent.llm.base import LLMProtocolError, LLMTimeoutError, LLMTransportError

logger = logging.getLogger(__name__)


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
        timeout: float | None = None,
    ) -> dict[str, Any]:
        request = self._request(messages, stream=False, response_format=response_format, tools=tools)
        with self._open(request, stream=False, timeout=timeout) as response:
            result = self._decode(response.read())
            if result.get("done") is not True:
                raise LLMProtocolError("Ollama chat response is missing its completion flag")
            return result

    def stream(self, messages: Sequence[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        request = self._request(messages, stream=True, response_format=None, tools=())
        with self._open(request, stream=True) as response:
            for line in response:
                if line.strip():
                    item = self._decode(line)
                    yield item
                    if item.get("done") is True:
                        return
            raise LLMProtocolError("Ollama stream ended before its completion frame")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        request = Request(
            f"{self.settings.url.rstrip('/')}/api/embed",
            data=json.dumps({"model": self.settings.model, "input": list(texts),
                             "truncate": False, "keep_alive": "2m"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._open(request, stream=False) as response:
            vectors = self._decode(response.read()).get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                raise LLMProtocolError("Ollama returned an invalid embedding batch")
            return vectors

    @staticmethod
    def _decode(data: bytes) -> dict[str, Any]:
        try:
            result = json.loads(data.decode("utf-8"))
        except (ValueError, RecursionError) as error:
            raise LLMProtocolError("Ollama returned invalid UTF-8 JSON") from error
        if not isinstance(result, dict):
            raise LLMProtocolError("Ollama returned a non-object JSON response")
        if "error" in result:
            raise LLMProtocolError("Ollama reported an error in its response")
        return result

    @contextmanager
    def _open(self, request: Request, *, stream: bool, timeout: float | None = None) -> Iterator[HTTPResponse]:
        started = perf_counter()
        try:
            limit = self.settings.timeout if timeout is None else min(timeout, self.settings.timeout)
            with urlopen(request, timeout=limit) as response:
                yield response
        except HTTPError as error:
            error.close()
            logger.warning("Ollama HTTP status %s (stream=%s)", error.code, stream)
            raise LLMTransportError(f"Ollama returned HTTP {error.code}") from error
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                logger.warning("Ollama connection timed out")
                raise LLMTimeoutError("Ollama connection timed out") from error
            logger.warning("Ollama connection failed")
            raise LLMTransportError("Could not reach Ollama") from error
        except TimeoutError as error:
            logger.warning("Ollama response timed out")
            raise LLMTimeoutError("Ollama response timed out") from error
        except (OSError, HTTPException) as error:
            logger.warning("Ollama transport failed: %s", type(error).__name__)
            raise LLMTransportError("Ollama connection was interrupted") from error
        except LLMProtocolError:
            logger.warning("Ollama returned an invalid response (stream=%s)", stream)
            raise
        else:
            logger.debug("Ollama request completed (stream=%s, %.3f s)", stream, perf_counter() - started)
