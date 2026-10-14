from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx

from parsers.html_parser import HTMLParser
from parsers.doc_detector import DocDetector


# UKG (Kronos/UltiPro) API explorer patterns
_UKG_SPEC_PATHS = [
    "/api/v1/openapi.json",
    "/api/v1/swagger.json",
    "/api/openapi.json",
    "/developer/api/openapi.json",
    "/api-docs",
]


class UKGParser:
    """
    Phase 12 — Vendor adapter for UKG (Kronos/UltiPro) API documentation.
    Handles their API explorer and attempts to locate hidden spec files.
    """

    def __init__(self) -> None:
        self._html_parser = HTMLParser()
        self._detector = DocDetector()

    async def find_spec(self, base_url: str) -> dict | None:
        """Probe UKG-specific spec paths."""
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        async with httpx.AsyncClient(timeout=20, follow_redirects=True, verify=False) as client:
            for path in _UKG_SPEC_PATHS:
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
        """Parse UKG API explorer HTML."""
        result = self._html_parser.parse(html, page_url)
        # UKG often prefixes paths with /api/v1
        for ep in result.get("endpoints", []):
            if not ep["path"].startswith("/api"):
                ep["path"] = "/api/v1" + ep["path"]
        return result

    def normalize_auth(self, html: str) -> dict:
        """UKG typically uses OAuth2 with client credentials."""
        if re.search(r"client_credentials|OAuth", html, re.IGNORECASE):
            return {
                "auth_type": "oauth2",
                "token_url": "https://auth.ultipro.com/oauth/token",
                "scopes": {},
            }
        return {"auth_type": "bearer"}
