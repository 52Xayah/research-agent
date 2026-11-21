"""Project settings supplied through the process environment."""

import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class OllamaSettings:
    url: str = "http://localhost:11434"
    model: str = "qwen3.5:4b"
    timeout: float = 90
    context: int = 4096
    max_output: int = 512

    def __post_init__(self) -> None:
        address = urlsplit(self.url)
        if (
            address.scheme not in {"http", "https"}
            or not address.hostname
            or address.username is not None
            or address.query
            or address.fragment
        ):
            raise ValueError("RESEARCH_OLLAMA_URL must be an HTTP(S) base URL")
        # Accessing the port validates both its value and its range.
        _ = address.port
        if not self.model.strip():
            raise ValueError("RESEARCH_OLLAMA_MODEL must not be empty")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("RESEARCH_OLLAMA_TIMEOUT must be positive and finite")
        if not 0 < self.max_output < self.context:
            raise ValueError("Ollama output budget must be positive and smaller than its context")

    @classmethod
    def from_env(cls) -> "OllamaSettings":
        defaults = cls()
        return cls(
            url=os.getenv("RESEARCH_OLLAMA_URL", defaults.url).rstrip("/"),
            model=os.getenv("RESEARCH_OLLAMA_MODEL", defaults.model),
            timeout=float(os.getenv("RESEARCH_OLLAMA_TIMEOUT", str(defaults.timeout))),
            context=int(os.getenv("RESEARCH_OLLAMA_CONTEXT", str(defaults.context))),
            max_output=int(os.getenv("RESEARCH_OLLAMA_MAX_OUTPUT", str(defaults.max_output))),
        )
