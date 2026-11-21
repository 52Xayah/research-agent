"""Bounded Wikipedia search and article extract retrieval."""

import html
import json
import re
from dataclasses import dataclass
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from research_agent.llm.base import JsonObject
from research_agent.tools.base import ToolError
from research_agent.tools.search import SearchHit, SearchProvider

API = "https://en.wikipedia.org/w/api.php"
PAGE_ID = re.compile(r"https://en\.wikipedia\.org/\?curid=([1-9][0-9]{0,12})")


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    text: str


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Wikipedia(SearchProvider):
    def __init__(self, contact: str):
        contact = contact.strip()
        if (not contact or len(contact) > 160 or not contact.isascii()
                or any(ord(character) < 32 or ord(character) == 127 for character in contact)):
            raise ValueError("Set RESEARCH_WIKI_CONTACT to an operator contact URL, email or wiki username")
        self.user_agent = f"ResearchAgent/0.1 ({contact})"
        self.opener = build_opener(_NoRedirect())

    def _get(self, params: dict[str, str | int], timeout: float) -> JsonObject:
        query = urlencode({"action": "query", "format": "json", "formatversion": 2, **params})
        request = Request(f"{API}?{query}", headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(64 * 1024 + 1)
            if len(raw) > 64 * 1024:
                raise ToolError("web_response_too_large", "Wikipedia response exceeds 64 KiB")
            data = json.loads(raw)
        except HTTPError as error:
            error.close()
            code = "web_rate_limited" if error.code == 429 else "web_http_error"
            raise ToolError(code, f"Wikipedia returned HTTP {error.code}") from error
        except TimeoutError as error:
            raise ToolError("web_timeout", "Wikipedia timed out") from error
        except (URLError, OSError, HTTPException) as error:
            raise ToolError("web_unavailable", "Could not reach Wikipedia") from error
        except (ValueError, RecursionError) as error:
            raise ToolError("web_protocol_error", "Wikipedia returned invalid JSON") from error
        if not isinstance(data, dict) or not isinstance(data.get("query"), dict):
            code = data.get("error", {}) if isinstance(data, dict) else {}
            if isinstance(code, dict) and code.get("code") in {"ratelimited", "maxlag"}:
                raise ToolError("web_rate_limited", "Wikipedia requested a slower request rate")
            raise ToolError("web_protocol_error", "Wikipedia did not return query data")
        return data["query"]

    def search(self, query: str, *, limit: int, timeout: float) -> tuple[SearchHit, ...]:
        data = self._get({"list": "search", "srsearch": query, "srlimit": limit, "srnamespace": 0}, timeout)
        rows = data.get("search")
        if not isinstance(rows, list):
            raise ToolError("web_protocol_error", "Wikipedia did not return search results")
        hits = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            page_id, title = row.get("pageid"), row.get("title")
            if type(page_id) is int and 0 < page_id < 10**13 and isinstance(title, str):
                snippet = row.get("snippet", "")
                text = html.unescape(re.sub(r"<[^>]+>", "", snippet)) if isinstance(snippet, str) else ""
                hits.append(SearchHit(title[:160], f"https://en.wikipedia.org/?curid={page_id}", text[:400]))
        return tuple(hits)

    def fetch(self, url: str, *, timeout: float = 8) -> Article:
        match = PAGE_ID.fullmatch(url)
        if not match:
            raise ToolError("web_url_not_allowed", "Only Wikipedia search result URLs are accepted")
        data = self._get({"pageids": match.group(1), "prop": "extracts|info",
                          "exintro": 1, "explaintext": 1, "exchars": 1200}, timeout)
        pages = data.get("pages")
        if not isinstance(pages, list) or not pages or not isinstance(pages[0], dict):
            raise ToolError("web_protocol_error", "Wikipedia did not return page data")
        page = pages[0]
        title, text, revision = page.get("title"), page.get("extract"), page.get("lastrevid")
        if not isinstance(title, str) or not isinstance(text, str) or not text.strip():
            raise ToolError("web_empty_page", "Wikipedia returned no article text")
        if type(revision) is int and revision > 0:
            url = f"https://en.wikipedia.org/?oldid={revision}"
        return Article(title[:160], url, " ".join(text.split())[:1200])
