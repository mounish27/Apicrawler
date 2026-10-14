from __future__ import annotations

import json
from typing import Any


# URL keywords that suggest a spec file
_SPEC_KEYWORDS = (
    "swagger", "openapi", "api-docs", "api_docs", "spec",
    "postman", "readme", "graphql", "/v2/", "/v3/",
)

# Content-type patterns for JSON specs
_JSON_CONTENT = ("application/json", "text/json")


class NetworkInterceptor:
    """
    Attaches to a Playwright page and captures XHR / fetch responses
    that look like API spec files.
    """

    def __init__(self) -> None:
        self.captured: list[dict[str, Any]] = []

    def attach(self, page) -> None:
        page.on("response", self._on_response)

    async def _on_response(self, response) -> None:
        try:
            content_type = response.headers.get("content-type", "")
            url = response.url

            is_json = any(ct in content_type for ct in _JSON_CONTENT)
            is_spec_url = any(kw in url.lower() for kw in _SPEC_KEYWORDS)

            if not is_json:
                return

            # Always capture spec-looking URLs; also capture large JSON from doc domains
            if is_spec_url:
                body = await response.json()
                self.captured.append({"url": url, "data": body})
        except Exception:
            pass

    def get_specs(self) -> list[dict[str, Any]]:
        """Return only captured payloads that look like real OpenAPI/Swagger specs."""
        specs = []
        for item in self.captured:
            data = item["data"]
            if isinstance(data, dict):
                if ("openapi" in data or "swagger" in data) and "paths" in data:
                    specs.append(item)
                elif isinstance(data.get("info"), dict) and "_postman_id" in data.get("info", {}):
                    specs.append(item)
        return specs
