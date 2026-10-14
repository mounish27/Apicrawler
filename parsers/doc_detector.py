from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urljoin, urlparse


class DocType(str, Enum):
    OPENAPI_SPEC   = "openapi_spec"
    SWAGGER_UI     = "swagger_ui"
    REDOC          = "redoc"
    STOPLIGHT      = "stoplight"
    POSTMAN        = "postman"
    GRAPHQL        = "graphql"
    STATIC_HTML    = "static_html"
    UNKNOWN        = "unknown"


@dataclass
class DetectionResult:
    doc_type: DocType
    spec_url: str | None = None
    spec_data: dict[str, Any] | None = None
    confidence: float = 1.0
    notes: str = ""
    extra_spec_urls: list[str] = field(default_factory=list)


# Common OpenAPI spec paths to probe
COMMON_SPEC_PATHS = [
    "/openapi.json", "/openapi.yaml",
    "/swagger.json", "/swagger.yaml",
    "/api-docs", "/api-docs.json",
    "/v2/api-docs", "/v3/api-docs",
    "/swagger/v1/swagger.json",
    "/swagger/v2/swagger.json",
    "/.well-known/openapi.json",
    "/api/openapi.json",
    "/api/swagger.json",
    "/docs/openapi.json",
    "/api/v1/openapi.json",
    "/api/v2/openapi.json",
    "/api/v3/openapi.json",
]


class DocDetector:
    """
    Phase 1 — Classifies API documentation into its type.
    Detects Swagger UI, ReDoc, Stoplight, raw spec, GraphQL, or static HTML.
    """

    def from_json(self, data: dict, url: str = "") -> DetectionResult:
        """Detect from a parsed JSON body."""
        # OpenAPI 3.x
        if "openapi" in data and "paths" in data:
            return DetectionResult(DocType.OPENAPI_SPEC, spec_data=data, spec_url=url,
                                   notes=f"OpenAPI {data.get('openapi')}")
        # Swagger 2.x
        if "swagger" in data and "paths" in data:
            return DetectionResult(DocType.OPENAPI_SPEC, spec_data=data, spec_url=url,
                                   notes=f"Swagger {data.get('swagger')}")
        # Postman collection
        if self._is_postman(data):
            return DetectionResult(DocType.POSTMAN, spec_data=data, spec_url=url,
                                   notes="Postman collection")
        # GraphQL introspection
        if "__schema" in data or ("data" in data and "__schema" in data.get("data", {})):
            return DetectionResult(DocType.GRAPHQL, spec_data=data, spec_url=url,
                                   notes="GraphQL introspection")
        return DetectionResult(DocType.UNKNOWN, confidence=0.0)

    def from_html(self, html: str, page_url: str) -> DetectionResult:
        """Detect from rendered HTML content."""
        # ReDoc
        result = self._detect_redoc(html, page_url)
        if result:
            return result
        # Swagger UI
        result = self._detect_swagger_ui(html, page_url)
        if result:
            return result
        # Stoplight
        if re.search(r"stoplight|elements-api|@stoplight", html, re.IGNORECASE):
            spec_url = self._extract_stoplight_spec(html, page_url)
            return DetectionResult(DocType.STOPLIGHT, spec_url=spec_url, confidence=0.9,
                                   notes="Stoplight Elements detected")
        # GraphQL
        if re.search(r"GraphiQL|graphql-playground|/graphql", html, re.IGNORECASE):
            return DetectionResult(DocType.GRAPHQL, confidence=0.85, notes="GraphQL playground")

        return DetectionResult(DocType.STATIC_HTML, confidence=0.9,
                               notes="Static HTML documentation",
                               extra_spec_urls=self.candidate_spec_urls(page_url))

    def candidate_spec_urls(self, page_url: str) -> list[str]:
        """Return ordered list of spec URLs to probe for a given page URL."""
        parsed = urlparse(page_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        return [base + p for p in COMMON_SPEC_PATHS]

    # ── private ───────────────────────────────────────────────────────────

    def _detect_swagger_ui(self, html: str, page_url: str) -> DetectionResult | None:
        patterns = [
            r'SwaggerUIBundle\s*\(',
            r'swagger-ui(?:\.min)?\.js',
            r'swagger-ui-bundle',
            r'id=["\']swagger-ui["\']',
        ]
        if not any(re.search(p, html, re.IGNORECASE) for p in patterns):
            return None

        spec_url = None
        # Try to extract embedded spec URL
        for pattern in [
            r'url\s*:\s*["\']([^"\']+\.(?:json|yaml))["\']',
            r'url\s*:\s*["\']([^"\']+/api-docs[^"\']*)["\']',
            r'configUrl\s*:\s*["\']([^"\']+)["\']',
        ]:
            m = re.search(pattern, html)
            if m:
                spec_url = urljoin(page_url, m.group(1))
                break

        extra = self.candidate_spec_urls(page_url)
        return DetectionResult(DocType.SWAGGER_UI, spec_url=spec_url, confidence=0.95,
                               notes="Swagger UI detected", extra_spec_urls=extra)

    def _detect_redoc(self, html: str, page_url: str) -> DetectionResult | None:
        patterns = [
            r'<redoc\s+spec-url=["\']([^"\']+)["\']',
            r'Redoc\.init\s*\(\s*["\']([^"\']+)["\']',
            r'redoc(?:\.min)?\.js',
            r'id=["\']redoc-container["\']',
        ]
        for p in patterns:
            m = re.search(p, html, re.IGNORECASE)
            if m:
                spec_url = urljoin(page_url, m.group(1)) if m.lastindex else None
                extra = self.candidate_spec_urls(page_url)
                return DetectionResult(DocType.REDOC, spec_url=spec_url, confidence=0.95,
                                       notes="ReDoc renderer", extra_spec_urls=extra)
        return None

    def _extract_stoplight_spec(self, html: str, page_url: str) -> str | None:
        m = re.search(r'apiDescriptionUrl=["\']([^"\']+)["\']', html)
        if m:
            return urljoin(page_url, m.group(1))
        return None

    def _is_postman(self, data: dict) -> bool:
        info = data.get("info", {})
        return isinstance(info, dict) and "_postman_id" in info or "collection" in data
