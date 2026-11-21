"""Search contract for a separately configured provider."""

import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from research_agent.llm.base import JsonObject
from research_agent.parameters import Parameter
from research_agent.tools.base import BaseTool, ToolError


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, *, limit: int, timeout: float) -> Sequence[SearchHit]:
        """Return ranked results within the given budget. Raise ToolError for provider failures."""


class Search(BaseTool):
    name = "search"
    description = "Search an authorized provider for web sources by query."
    parameters = {
        "query": Parameter("string", "Search query", min_length=1, max_length=256),
        "limit": Parameter("integer", "Maximum results, defaults to 5", required=False, minimum=1, maximum=10),
    }

    def __init__(self, provider: SearchProvider | None = None, *, timeout: float = 10):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Search timeout must be positive and finite")
        self.provider = provider
        self.timeout = timeout

    def execute(self, *, query: str, limit: int = 5) -> JsonObject:
        query = query.strip()
        if not query:
            raise ToolError("invalid_arguments", "Search query must not be whitespace only")
        if self.provider is None:
            raise ToolError("search_not_configured", "A search provider has not been configured")
        try:
            hits = self.provider.search(query, limit=limit, timeout=self.timeout)
        except TimeoutError as error:
            raise ToolError("search_timeout", "Search provider timed out") from error
        return {"query": query, "results": [asdict(hit) for hit in hits[:limit]]}
