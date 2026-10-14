from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from parsers.html_parser import HTMLParser


# Workday REST API path patterns
_WD_PATH_RE = re.compile(r"/api/[\w]+/v[\d]+/[\w\-/{}]+", re.IGNORECASE)
_WD_VERSION_RE = re.compile(r"v(\d+)\b")


class WorkdayParser:
    """
    Phase 12 — Vendor adapter for Workday API documentation.
    Workday docs are heavily JS-rendered with dynamic navigation.
    """

    def __init__(self) -> None:
        self._html_parser = HTMLParser()

    def parse_html(self, html: str, page_url: str) -> dict:
        result = self._html_parser.parse(html, page_url)

        # Extract Workday-specific path patterns from the full HTML text
        extra_paths = _WD_PATH_RE.findall(html)
        seen = {(ep["method"], ep["path"]) for ep in result["endpoints"]}
        for path in extra_paths:
            # Without a method signal, assume GET
            key = ("GET", path)
            if key not in seen:
                seen.add(key)
                result["endpoints"].append({
                    "method": "GET",
                    "path": path,
                    "summary": None,
                    "description": None,
                    "tags": ["workday"],
                    "parameters": [],
                    "request_body": None,
                    "responses": {},
                    "auth_type": "bearer",
                    "deprecated": False,
                    "source_url": page_url,
                })

        return result

    def extract_sidebar_links(self, html: str, base_url: str) -> list[str]:
        """Extract nav links from Workday's sidebar."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"/api|/reference|/rest", href, re.IGNORECASE):
                full = urljoin(base_url, href)
                links.append(full)
        return links

    def infer_version(self, page_url: str) -> str:
        m = _WD_VERSION_RE.search(page_url)
        return m.group(1) if m else "1"
