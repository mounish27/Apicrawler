from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx

from parsers.html_parser import HTMLParser
from parsers.doc_detector import DocDetector


_TOAST_SPEC_PATHS = [
    "/openapi.json",
    "/api-reference/openapi.json",
    "/docs/openapi.json",
    "/swagger.json",
]


class ToastParser:
    """
    Phase 12 — Vendor adapter for Toast POS API documentation.
    Toast uses static HTML docs and sometimes a Swagger/ReDoc portal.
    """

    def __init__(self) -> None:
        self._html_parser = HTMLParser()
        self._detector = DocDetector()

    async def find_spec(self, base_url: str) -> dict | None:
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, verify=False) as client:
            for path in _TOAST_SPEC_PATHS:
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
        # Toast API paths typically start with /v1 or /partner
        for ep in result["endpoints"]:
            path = ep["path"]
            if not re.match(r"/(?:v\d+|partner|restaurants)", path, re.IGNORECASE):
                ep["path"] = "/v1" + path
        return result

    def normalize_auth(self) -> dict:
        return {
            "auth_type": "oauth2",
            "token_url": "https://ws-api.toasttab.com/authentication/v1/authentication/login",
            "scopes": {},
        }
