from __future__ import annotations

from typing import Any

from parsers.doc_detector import DocDetector, DocType
from parsers.swagger_parser import SwaggerParser
from parsers.html_parser import HTMLParser
from parsers.graphql_parser import GraphQLParser
from parsers.js_parser import JSParser
from extraction.auth_detector import AuthDetector


class GenericParser:
    """
    Phase 1/4 — Unified entry point that dispatches to the right parser
    based on detected document type.
    """

    def __init__(self) -> None:
        self._detector = DocDetector()
        self._swagger = SwaggerParser()
        self._html = HTMLParser()
        self._gql = GraphQLParser()
        self._js = JSParser()
        self._auth = AuthDetector()

    def parse_page(self, html: str, page_url: str) -> dict:
        """Parse a page's HTML. Returns normalized extraction result."""
        det = self._detector.from_html(html, page_url)
        return {
            "doc_type": det.doc_type,
            "spec_url": det.spec_url,
            **self._html.parse(html, page_url),
        }

    def parse_spec(self, spec: dict, source_url: str = "") -> dict:
        """Parse a raw OpenAPI/Swagger/Postman spec."""
        det = self._detector.from_json(spec, source_url)
        endpoints = self._swagger.parse(spec, source_url)
        auth = self._auth.detect_from_spec(spec)
        title = spec.get("info", {}).get("title", "")
        version = spec.get("info", {}).get("version", "1.0.0")
        servers = [s.get("url", "") for s in spec.get("servers", [])]

        return {
            "doc_type": det.doc_type,
            "endpoints": endpoints,
            "auth": auth,
            "title": title,
            "version": version,
            "servers": servers,
            "raw_spec": spec,
        }

    def parse_js(self, js_text: str, page_url: str) -> dict:
        endpoints = self._js.extract_from_js(js_text, page_url)
        return {"doc_type": DocType.STATIC_HTML, "endpoints": endpoints, "auth": {"auth_type": "unknown"}}
