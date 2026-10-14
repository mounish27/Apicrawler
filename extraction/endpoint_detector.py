from __future__ import annotations

import hashlib
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

# Matches: GET /v1/employees/{id}
_INLINE_RE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/[\w\-/{}.:]+)",
    re.IGNORECASE,
)

_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}

# Tags that are never HTTP methods
_SKIP_TAGS = {"head", "title", "script", "style", "meta", "link", "noscript"}

_COOKIE_HEADING_RE = re.compile(
    r"\b(cookie|consent|preference|privacy|gdpr|onetrust|manage consent)\b",
    re.IGNORECASE,
)


def _ep_id(method: str, path: str, source: str) -> str:
    raw = f"{source}:{method.upper()}:{path}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _valid_path(path: str) -> bool:
    if path.startswith("//"):
        return False
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return False
    return any(re.search(r"[a-zA-Z]", p) for p in parts)


class EndpointDetector:
    """
    Phase 4 — Extracts API endpoints from rendered HTML using multiple strategies.

    Strategy A: Inline patterns  — "GET /v1/path" in headings, code, td
    Strategy B: Method badge     — <span class="get">GET</span> near <code>/path</code>
    Strategy C: Table rows       — rows with method + path columns
    """

    def detect(self, html: str, page_url: str, source: str = "") -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        seen: set[tuple[str, str]] = set()
        endpoints: list[dict] = []

        def add(method: str, path: str, summary: str | None = None,
                params: list | None = None, anchor_el=None) -> None:
            key = (method.upper(), path)
            if key in seen or not _valid_path(path):
                return
            seen.add(key)
            desc = self._nearby_description(anchor_el, soup) if anchor_el else None
            endpoints.append({
                "method": method.upper(),
                "path": path,
                "summary": summary,
                "description": desc,
                "tags": [],
                "parameters": params or [],
                "request_body": None,
                "responses": {},
                "auth_type": "unknown",
                "deprecated": False,
                "source_url": page_url,
                "id": _ep_id(method, path, source or page_url),
            })

        # Strategy A — inline "METHOD /path" in text nodes
        for tag_name in ("h1", "h2", "h3", "h4", "h5", "h6",
                         "p", "li", "td", "th", "code", "pre", "span", "div"):
            for tag in soup.find_all(tag_name):
                text = tag.get_text(" ", strip=True)
                for m in _INLINE_RE.finditer(text):
                    method, path = m.group(1).upper(), m.group(2)
                    summary = self._nearby_summary(tag, soup)
                    add(method, path, summary, anchor_el=tag)

        # Strategy B — method badge element adjacent to path element
        for el in soup.find_all(string=re.compile(
            r"^\s*(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s*$", re.IGNORECASE
        )):
            parent = el.parent
            if parent is None or parent.name in _SKIP_TAGS:
                continue
            method = el.strip().upper()
            if method not in _METHODS:
                continue
            path = self._find_nearby_path(parent)
            if path:
                add(method, path, self._nearby_summary(parent, soup), anchor_el=parent)

        # Strategy C — table rows with method + path columns
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            first = cells[0].get_text(strip=True).upper()
            if first in _METHODS:
                path_text = cells[1].get_text(strip=True)
                path_match = re.search(r"(/[\w\-/{}.:]+)", path_text)
                if path_match:
                    summary = cells[2].get_text(strip=True) if len(cells) > 2 else None
                    add(first, path_match.group(1), summary, anchor_el=row)

        return endpoints

    def _find_nearby_path(self, el: Tag) -> str | None:
        for sibling in el.next_siblings:
            if isinstance(sibling, Tag):
                text = sibling.get_text(strip=True)
                m = re.search(r"(/[\w\-/{}.:]+)", text)
                if m and _valid_path(m.group(1)):
                    return m.group(1)
        parent_text = el.parent.get_text(" ", strip=True) if el.parent else ""
        m = re.search(r"(/[\w\-/{}.:]+)", parent_text)
        if m and _valid_path(m.group(1)):
            return m.group(1)
        return None

    def _nearby_summary(self, el: Tag, soup: BeautifulSoup) -> str | None:
        # Look backwards first (normal case: endpoint appears after its heading)
        for h in ("h1", "h2", "h3", "h4"):
            prev = el.find_previous(h)
            if prev:
                text = prev.get_text(strip=True)
                if text and len(text) < 200 and not _COOKIE_HEADING_RE.search(text):
                    return text
        # Fallback: look forward — handles nav/sidebar links that appear before
        # the main content heading in document order
        for h in ("h1", "h2", "h3", "h4"):
            nxt = el.find_next(h)
            if nxt:
                text = nxt.get_text(strip=True)
                if text and len(text) < 200 and not _COOKIE_HEADING_RE.search(text):
                    return text
        return None

    def _nearby_description(self, el: Tag, soup: BeautifulSoup) -> str | None:
        """Extract descriptive paragraphs near an endpoint element."""
        parts: list[str] = []

        # Look for <p> tags after the element (or its parent section)
        target = el
        for _ in range(3):
            if target.parent:
                target = target.parent

        for sibling in target.next_siblings:
            if not isinstance(sibling, Tag):
                continue
            name = sibling.name
            # Stop at next method/path heading or another endpoint
            if name in ("h1", "h2", "h3", "h4") and _INLINE_RE.search(sibling.get_text()):
                break
            if name in ("p", "div", "section"):
                text = sibling.get_text(" ", strip=True)
                if text and len(text) > 10 and not _INLINE_RE.match(text):
                    parts.append(text)
                if len(parts) >= 3:
                    break

        # Also look immediately before for a description <p> after the heading
        prev = el.find_previous("p")
        if prev:
            text = prev.get_text(" ", strip=True)
            if text and len(text) > 20 and text not in parts:
                parts.insert(0, text)

        desc = " ".join(parts)[:1000].strip()
        return desc if desc else None
