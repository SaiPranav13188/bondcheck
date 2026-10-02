"""web_search and fetch_page for the Monitor Agent."""
from __future__ import annotations

import re

import httpx

from core import llm
from core.config import settings


class WebUnavailable(RuntimeError):
    pass


def web_search(query: str, meter: llm.TokenMeter | None = None) -> dict:
    """Search the public web (Claude's server-side web search tool). Returns {summary, urls}."""
    if settings.offline:
        raise WebUnavailable("web search needs a Claude API key (offline mode)")
    return llm.web_research(query, meter)


def fetch_page(url: str, max_chars: int = 20000) -> str:
    """Fetch a public page and return its visible text."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("only http(s) URLs can be fetched")
    resp = httpx.get(url, timeout=15, follow_redirects=True,
                     headers={"User-Agent": "BondCheckMonitor/1.0 (+student bond transparency research)"})
    resp.raise_for_status()
    html = resp.text
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()[:max_chars]
