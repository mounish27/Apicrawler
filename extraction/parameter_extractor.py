from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup


_TYPE_HINTS = {
    "string": "string", "str": "string", "text": "string",
    "integer": "integer", "int": "integer", "number": "number",
    "float": "number", "double": "number", "decimal": "number",
    "boolean": "boolean", "bool": "boolean",
    "array": "array", "list": "array",
    "object": "object", "dict": "object",
    "uuid": "string", "date": "string", "datetime": "string",
    "timestamp": "integer",
}

_REQUIRED_HINTS = re.compile(r"\brequired\b", re.IGNORECASE)
_OPTIONAL_HINTS = re.compile(r"\boptional\b", re.IGNORECASE)


class ParameterExtractor:
    """
    Phase 5 — Extracts parameters from HTML tables, definition lists, and code blocks.
    """

    def extract_from_html(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        params: list[dict] = []
        seen: set[str] = set()

        # Tables: Name | Type | Required | Description
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower()
                       for th in table.find_all("th")]
            if not any(h in headers for h in ("name", "parameter", "field", "param")):
                continue
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                p = self._parse_table_row(cells, headers)
                if p and p["name"] and p["name"] not in seen:
                    seen.add(p["name"])
                    params.append(p)

        # Definition lists: <dt>param</dt><dd>description</dd>
        for dl in soup.find_all("dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                name = dt.get_text(strip=True)
                if not name or name in seen:
                    continue
                seen.add(name)
                desc = dd.get_text(strip=True)
                params.append({
                    "name": name,
                    "location": "query",
                    "type": self._infer_type(desc),
                    "required": bool(_REQUIRED_HINTS.search(desc)),
                    "description": desc[:300],
                    "enum": None,
                    "example": None,
                    "deprecated": False,
                })

        return params

    def extract_path_params(self, path: str) -> list[dict]:
        """Extract {param} placeholders from a path string."""
        return [
            {
                "name": m,
                "location": "path",
                "type": "string",
                "required": True,
                "description": "",
                "enum": None,
                "example": None,
                "deprecated": False,
            }
            for m in re.findall(r"\{(\w+)\}", path)
        ]

    # ── helpers ───────────────────────────────────────────────────────────

    def _parse_table_row(self, cells: list, headers: list) -> dict | None:
        def cell(idx: int) -> str:
            return cells[idx].get_text(strip=True) if idx < len(cells) else ""

        # Try to map by header position
        col = {h: i for i, h in enumerate(headers)}
        name_idx = col.get("name") or col.get("parameter") or col.get("field") or col.get("param") or 0
        type_idx = col.get("type") or col.get("data type") or 1
        req_idx = col.get("required") or col.get("mandatory")
        desc_idx = col.get("description") or col.get("desc") or (2 if len(cells) > 2 else None)

        name = cell(name_idx)
        if not name:
            return None

        type_text = cell(type_idx) if type_idx is not None else ""
        desc = cell(desc_idx) if desc_idx is not None else ""
        req_text = cell(req_idx) if req_idx is not None else ""

        required = (
            bool(_REQUIRED_HINTS.search(req_text or desc))
            and not bool(_OPTIONAL_HINTS.search(req_text))
        )

        # Infer location from name or description
        location = "query"
        if re.search(r"header|x-\w+", name, re.IGNORECASE):
            location = "header"

        return {
            "name": name,
            "location": location,
            "type": self._infer_type(type_text or desc),
            "required": required,
            "description": desc[:300],
            "enum": self._extract_enum(desc),
            "example": None,
            "deprecated": "deprecated" in (desc + name).lower(),
        }

    def _infer_type(self, text: str) -> str:
        t = text.lower().split()[0] if text else "string"
        return _TYPE_HINTS.get(t, "string")

    def _extract_enum(self, text: str) -> list | None:
        m = re.search(r"\bvalues?\s*[:=]\s*([^\n.]+)", text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            items = [s.strip().strip('"\'') for s in re.split(r"[,|/]", raw) if s.strip()]
            if 2 <= len(items) <= 20:
                return items
        return None
