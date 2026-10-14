from __future__ import annotations

import json as _json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from parsers.html_parser import HTMLParser


_DF_PATH_RE = re.compile(r"/v\d+/[\w\-/{}]+", re.IGNORECASE)
_DF_BASE = "/api/V1"
_COOKIE_RE = re.compile(
    r"\b(cookie|consent|preference|privacy|gdpr|onetrust|manage consent)\b",
    re.IGNORECASE,
)
_INLINE_METHOD_RE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/[\w\-/{}.:]+)",
    re.IGNORECASE,
)


class DayforceParser:
    """
    Phase 12 — Vendor adapter for Dayforce (Ceridian) API documentation.
    Uses section-based extraction: each <h1> delimits one API endpoint section
    with <h2> sub-headings for Overview, Parameters, Request Body, and Response.
    """

    def __init__(self) -> None:
        self._html_parser = HTMLParser()

    def parse_html(self, html: str, page_url: str) -> dict:
        soup = BeautifulSoup(html, "lxml")

        # Remove OneTrust / cookie-consent overlays before parsing
        for sel in (
            "#onetrust-consent-sdk",
            "#onetrust-banner-sdk",
            ".onetrust-pc-dark-filter",
            "[id*='onetrust']",
        ):
            try:
                for el in soup.select(sel):
                    el.decompose()
            except Exception:
                pass

        endpoints = self._extract_sections(soup, page_url)

        if not endpoints:
            # Strip nav/sidebar/header so heading detection isn't confused by
            # sidebar links that appear before the main h1 in document order
            for sel in ("nav", "header", "aside", "[role='navigation']",
                        "[role='banner']", ".sidebar", "#sidebar",
                        ".navigation", ".toc", "#toc", ".menu", "#menu"):
                try:
                    for el in soup.select(sel):
                        el.decompose()
                except Exception:
                    pass
            cleaned_html = str(soup)

            # Fallback: generic HTML parser on cleaned HTML
            result = self._html_parser.parse(cleaned_html, page_url)

            # Apply page-level title and description to any endpoint that lacks them
            page_title = self._html_parser.extract_title(cleaned_html)
            page_desc = self._html_parser.extract_lead_paragraph(cleaned_html)
            for ep in result["endpoints"]:
                if ep["path"] and not re.match(r"/(?:api|v\d+)", ep["path"], re.IGNORECASE):
                    ep["path"] = _DF_BASE + ep["path"]
                if not ep.get("summary") and page_title:
                    ep["summary"] = page_title
                if not ep.get("description") and page_desc:
                    ep["description"] = page_desc
                ep.setdefault("auth_type", "bearer")

            # Add any paths found by regex that the detector missed
            for m in _DF_PATH_RE.finditer(cleaned_html):
                path = m.group(0)
                if not any(ep["path"] == path for ep in result["endpoints"]):
                    result["endpoints"].append({
                        "method": "GET", "path": path,
                        "summary": page_title or None,
                        "description": page_desc or None,
                        "tags": ["dayforce"], "parameters": [],
                        "request_body": None, "responses": {}, "auth_type": "bearer",
                        "deprecated": False, "source_url": page_url,
                    })
            return result

        return {
            "endpoints": endpoints,
            "parameters": [],
            "responses": {},
            "examples": [],
            "auth": {"auth_type": "bearer"},
            "doc_type": "static_html",
        }

    # ── section extraction ─────────────────────────────────────────────────

    def _extract_sections(self, soup: BeautifulSoup, page_url: str) -> list[dict]:
        # ── MadCap Flare Reader format (help.dayforce.com) ──────────────────
        # The page is structured as nested <article> elements.
        # Depth-2 articles each represent one API endpoint: they have an h2
        # title and a content div containing the path URL, parameters table,
        # and response example.
        all_articles = soup.find_all("article")
        depth2 = [
            a for a in all_articles
            if "readercontent-topic-depth-2" in (a.get("class") or [])
        ]
        if depth2:
            return self._extract_from_articles(depth2, page_url)

        # ── Generic h1-based fallback for other doc platforms ───────────────
        api_h1s = [
            h for h in soup.find_all("h1")
            if not _COOKIE_RE.search(h.get_text())
        ]
        if not api_h1s:
            return []

        results: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for h1 in api_h1s:
            title = h1.get_text(strip=True)
            if not title or len(title) < 4:
                continue

            section_nodes: list[Tag] = []
            for sibling in h1.next_siblings:
                if getattr(sibling, "name", None) == "h1":
                    break
                if isinstance(sibling, Tag):
                    section_nodes.append(sibling)

            # Walk up if content lives in a sibling of the h1's parent
            if not section_nodes:
                parent = h1.parent
                for _ in range(3):
                    if parent is None:
                        break
                    for sibling in parent.next_siblings:
                        if getattr(sibling, "name", None) in ("h1", "h2"):
                            break
                        if isinstance(sibling, Tag):
                            section_nodes.append(sibling)
                    if section_nodes:
                        break
                    parent = parent.parent

            ep = self._parse_section(section_nodes, title, page_url)
            if ep is None:
                continue

            key = (ep["method"], ep["path"])
            if key not in seen:
                seen.add(key)
                results.append(ep)

        return results

    def _extract_from_articles(self, articles: list, page_url: str) -> list[dict]:
        """Extract endpoints from MadCap Flare Reader depth-2 article elements."""
        results: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for article in articles:
            # Title: first heading that isn't cookie-related
            heading = article.find(["h1", "h2", "h3"])
            if not heading:
                continue
            title = heading.get_text(strip=True)
            if not title or len(title) < 4 or _COOKIE_RE.search(title):
                continue

            # Extract HTTP method from title text ("POST Org Unit Data" → POST)
            method_in_title = re.search(
                r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b", title, re.IGNORECASE
            )
            default_method = method_in_title.group(1).upper() if method_in_title else "GET"

            # Real content lives in: section.topic > div.depth-2
            # (the div has meta/link/title tags mixed in, so filter to content tags)
            content_nodes: list[Tag] = []
            topic_sec = article.find("section", class_="topic")
            if topic_sec:
                depth2_div = topic_sec.find("div", class_="depth-2")
                if depth2_div:
                    content_nodes = [
                        c for c in depth2_div.children
                        if isinstance(c, Tag) and c.name not in ("meta", "link", "title", "script", "style")
                    ]

            # Fallback: all article children except the title section
            if not content_nodes:
                for child in article.children:
                    if not isinstance(child, Tag):
                        continue
                    cls = " ".join(child.get("class") or [])
                    if "depth-1" in cls or "title" in cls:
                        continue
                    content_nodes.append(child)

            ep = self._parse_section(content_nodes, title, page_url,
                                     default_method=default_method)
            if ep is None:
                continue

            key = (ep["method"], ep["path"])
            if key not in seen:
                seen.add(key)
                results.append(ep)

        return results

    def _parse_section(
        self, nodes: list[Tag], title: str, page_url: str,
        default_method: str = "GET",
    ) -> dict | None:
        current_h2: str | None = None
        description: str | None = None
        parameters: list[dict] = []
        request_example: Any = None
        response_example: Any = None
        method = default_method
        paths: list[str] = []

        for node in nodes:
            # Standard h2 section header OR Dayforce's <p class="SectionTitle">
            is_section_header = node.name == "h2" or (
                node.name == "p"
                and "SectionTitle" in " ".join(node.get("class") or [])
            )
            if is_section_header:
                current_h2 = node.get_text(strip=True).lower()
                continue

            node_text = node.get_text(" ", strip=True)

            # Collect API paths from anywhere in the section
            for m in _DF_PATH_RE.finditer(node_text):
                p = m.group(0)
                if p not in paths:
                    paths.append(p)

            inline = _INLINE_METHOD_RE.search(node_text)
            if inline:
                method = inline.group(1).upper()
                p = inline.group(2)
                if p not in paths:
                    paths.insert(0, p)

            h2 = current_h2 or ""

            if "overview" in h2 or not h2:
                if node.name == "p" and description is None and len(node_text) > 20:
                    description = node_text[:800]

            elif "parameter" in h2:
                if node.name == "table" and not parameters:
                    parameters = self._parse_params_table(node)

            elif "request" in h2 or "body" in h2:
                if request_example is None:
                    request_example = self._find_json(node)

            elif "response" in h2:
                if response_example is None:
                    response_example = self._find_json(node)

        if not paths:
            return None

        path = paths[0]
        if not re.match(r"/(?:api|v\d+)", path, re.IGNORECASE):
            path = _DF_BASE + path

        ep: dict = {
            "method": method,
            "path": path,
            "summary": title,
            "description": description,
            "tags": ["dayforce"],
            "parameters": parameters,
            "request_body": None,
            "responses": {},
            "auth_type": "bearer",
            "deprecated": False,
            "source_url": page_url,
        }

        if request_example is not None:
            ep["request_body"] = {
                "content_type": "application/json",
                "schema": {},
                "example": request_example,
                "required": False,
                "description": "",
            }

        if response_example is not None:
            ep["responses"] = {"200": {"description": "OK", "example": response_example}}

        return ep

    # ── helpers ────────────────────────────────────────────────────────────

    def _parse_params_table(self, table: Tag) -> list[dict]:
        rows = table.find_all("tr")
        params: list[dict] = []
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            name = cells[0].get_text(strip=True)
            if not name:
                continue
            type_text = cells[1].get_text(strip=True) if len(cells) > 1 else "string"
            # Try col index 3 for description (common: Name | Type | Required | Desc)
            if len(cells) > 3:
                desc = cells[3].get_text(strip=True)
                req_text = cells[2].get_text(strip=True).lower()
            elif len(cells) > 2:
                desc = cells[2].get_text(strip=True)
                req_text = ""
            else:
                desc = ""
                req_text = ""

            required = req_text in ("yes", "true", "required") or "required" in desc.lower()
            params.append({
                "name": name,
                "location": "query",
                "type": type_text.lower() if type_text else "string",
                "required": required,
                "description": desc[:300],
                "enum": None,
                "example": None,
                "deprecated": False,
            })
        return params

    def _find_json(self, node: Tag) -> Any:
        """Extract and parse the first valid JSON object/array from a node."""
        candidates: list[str] = []
        if node.name in ("pre", "code"):
            candidates.append(node.get_text())
        else:
            for code_el in node.find_all(["pre", "code"]):
                candidates.append(code_el.get_text())
            if not candidates:
                text = node.get_text()
                if text.strip().startswith(("{", "[")):
                    candidates.append(text)

        for txt in candidates:
            txt = txt.strip()
            if not txt or txt[0] not in ("{", "["):
                continue
            try:
                return _json.loads(txt)
            except Exception:
                cleaned = re.sub(r",\s*([\}\]])", r"\1", txt)
                try:
                    return _json.loads(cleaned)
                except Exception:
                    continue
        return None

    def normalize_auth(self) -> dict:
        return {
            "auth_type": "bearer",
            "notes": "Dayforce uses session-based or OAuth2 bearer tokens",
        }
