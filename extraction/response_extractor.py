from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .example_parser import ExampleParser
from .schema_extractor import SchemaExtractor


_STATUS_RE = re.compile(r"\b([1-5]\d{2})\b")
_STATUS_DESC = {
    "200": "OK", "201": "Created", "204": "No Content",
    "400": "Bad Request", "401": "Unauthorized", "403": "Forbidden",
    "404": "Not Found", "409": "Conflict", "422": "Unprocessable Entity",
    "429": "Too Many Requests", "500": "Internal Server Error",
}


class ResponseExtractor:
    """
    Phase 6 — Extracts response examples and status codes from HTML.
    Infers schemas from JSON examples.
    """

    def __init__(self) -> None:
        self._example_parser = ExampleParser()
        self._schema_extractor = SchemaExtractor()

    def extract_from_html(self, html: str) -> dict[str, dict]:
        """Returns dict keyed by HTTP status code."""
        soup = BeautifulSoup(html, "lxml")
        responses: dict[str, dict] = {}

        # Find status-code headings/sections
        for tag in soup.find_all(re.compile(r"^h[1-6]$")):
            text = tag.get_text(strip=True)
            m = _STATUS_RE.search(text)
            if m:
                code = m.group(1)
                desc = text or _STATUS_DESC.get(code, "Response")
                # Look for a nearby code block
                schema = self._find_nearby_schema(tag)
                responses[code] = {
                    "description": desc,
                    "schema": schema,
                }

        # Also scan tables for response code columns
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if not any(h in headers for h in ("status", "code", "response")):
                continue
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if not cells:
                    continue
                first = cells[0].get_text(strip=True)
                m = _STATUS_RE.match(first)
                if m:
                    code = m.group(1)
                    desc = cells[1].get_text(strip=True) if len(cells) > 1 else _STATUS_DESC.get(code, "")
                    if code not in responses:
                        responses[code] = {"description": desc, "schema": None}

        # Ensure at least a 200
        if not responses:
            responses["200"] = {"description": "OK", "schema": None}

        return responses

    def extract_from_spec_responses(self, raw_responses: dict, examples: list[Any]) -> dict[str, dict]:
        """Enrich spec responses with inferred schemas from examples."""
        result = dict(raw_responses)
        if examples and "200" in result and result["200"].get("schema") is None:
            schema = self._schema_extractor.infer_from_examples(examples)
            result["200"]["schema"] = schema
        return result

    # ── private ───────────────────────────────────────────────────────────

    def _find_nearby_schema(self, tag) -> dict | None:
        for sibling in tag.next_siblings:
            if hasattr(sibling, "name") and sibling.name in ("pre", "code", "div"):
                text = sibling.get_text()
                examples = self._example_parser.extract_from_text(text)
                if examples:
                    return self._schema_extractor.infer(examples[0])
        return None
