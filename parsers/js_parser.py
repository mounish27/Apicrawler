from __future__ import annotations

import re
from typing import Any


# Patterns for extracting API info from JS bundles
_URL_RE = re.compile(r'["\`](/api/[\w\-/{}]+)["\`]', re.IGNORECASE)
_METHOD_URL_RE = re.compile(
    r'(?:method|type)\s*[:=]\s*["\']?(GET|POST|PUT|PATCH|DELETE)["\']?[^;{]*'
    r'(?:url|path|endpoint)\s*[:=]\s*["\`]([^"\`]+)["\`]',
    re.IGNORECASE | re.DOTALL,
)
_FETCH_RE = re.compile(
    r'fetch\s*\(\s*["\`]([^"\`]+)["\`]\s*(?:,\s*\{[^}]*method\s*:\s*["\']?(GET|POST|PUT|PATCH|DELETE)["\']?)?',
    re.IGNORECASE,
)
_AXIOS_RE = re.compile(
    r'axios\.(get|post|put|patch|delete)\s*\(\s*["\`]([^"\`]+)["\`]',
    re.IGNORECASE,
)


class JSParser:
    """
    Phase 17 — Extracts API endpoint hints from JavaScript source / bundles.
    Used as a fallback when HTML extraction yields nothing.
    """

    def extract_from_js(self, js_text: str, base_url: str = "") -> list[dict]:
        endpoints: list[dict] = []
        seen: set[tuple[str, str]] = set()

        def add(method: str, path: str) -> None:
            key = (method.upper(), path)
            if key not in seen and path.startswith("/"):
                seen.add(key)
                endpoints.append({
                    "method": method.upper(),
                    "path": path,
                    "summary": None,
                    "description": None,
                    "tags": [],
                    "parameters": [],
                    "request_body": None,
                    "responses": {},
                    "auth_type": "unknown",
                    "deprecated": False,
                    "source_url": base_url,
                })

        # axios.get('/path')
        for m in _AXIOS_RE.finditer(js_text):
            method, path = m.group(1), m.group(2)
            if path.startswith("/") or path.startswith("http"):
                path = self._extract_path(path)
                if path:
                    add(method, path)

        # fetch('/path', {method: 'POST'})
        for m in _FETCH_RE.finditer(js_text):
            path = self._extract_path(m.group(1))
            method = m.group(2) or "GET"
            if path:
                add(method, path)

        # method: 'POST', url: '/path'
        for m in _METHOD_URL_RE.finditer(js_text):
            method, path = m.group(1), m.group(2)
            path = self._extract_path(path)
            if path:
                add(method, path)

        return endpoints

    def extract_urls_from_js(self, js_text: str) -> list[str]:
        """Extract all API-looking URL strings from JS."""
        return [m.group(1) for m in _URL_RE.finditer(js_text)]

    # ── private ───────────────────────────────────────────────────────────

    def _extract_path(self, raw: str) -> str | None:
        raw = raw.strip()
        if raw.startswith("http"):
            from urllib.parse import urlparse
            parsed = urlparse(raw)
            return parsed.path or None
        if raw.startswith("/"):
            return raw.split("?")[0]
        return None
