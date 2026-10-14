from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx

from parsers.html_parser import HTMLParser
from parsers.doc_detector import DocDetector


_ADP_SPEC_PATHS = [
    "/marketplace/api/openapi.json",
    "/api/openapi.json",
    "/docs/openapi.json",
    "/api-explorer/openapi.json",
]

# ADP paths typically look like /api/v1/...
_ADP_PATH_RE = re.compile(r"/(?:api|core)/[\w/\-{}]+", re.IGNORECASE)


class ADPParser:
    """
    Phase 12 — Vendor adapter for ADP API documentation.
    ADP has an interactive API explorer with OAuth2 auth.
    """

    def __init__(self) -> None:
        self._html_parser = HTMLParser()
        self._detector = DocDetector()

    async def find_spec(self, base_url: str) -> dict | None:
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, verify=False) as client:
            for path in _ADP_SPEC_PATHS:
                url = origin + path
                try:
                    r = await client.get(url, headers={"Accept": "application/json"})
                    if r.status_code == 200:
                        data = r.json()
                        det = self._detector.from_json(data, url)
                        if det.spec_data:
                            return {"url": url, "spec": data}
                except Exception:
                    continue
        return None

    def parse_html(self, html: str, page_url: str) -> dict:
        result = self._html_parser.parse(html, page_url)
        # Supplement with ADP-specific path extraction
        for m in _ADP_PATH_RE.finditer(html):
            path = m.group(0)
            key = ("GET", path)
            exists = any(ep["path"] == path for ep in result["endpoints"])
            if not exists:
                result["endpoints"].append({
                    "method": "GET", "path": path, "summary": None,
                    "description": None, "tags": ["adp"], "parameters": [],
                    "request_body": None, "responses": {}, "auth_type": "oauth2",
                    "deprecated": False, "source_url": page_url,
                })
        return result

    def normalize_auth(self) -> dict:
        return {
            "auth_type": "oauth2",
            "token_url": "https://accounts.adp.com/auth/oauth/v2/token",
            "scopes": {},
        }
