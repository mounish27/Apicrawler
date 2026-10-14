from __future__ import annotations

import re

from bs4 import BeautifulSoup

_COOKIE_RE = re.compile(
    r"\b(cookie|consent|preference|privacy|gdpr|onetrust)\b", re.IGNORECASE
)

from extraction.endpoint_detector import EndpointDetector
from extraction.parameter_extractor import ParameterExtractor
from extraction.response_extractor import ResponseExtractor
from extraction.example_parser import ExampleParser
from extraction.auth_detector import AuthDetector


class HTMLParser:
    """
    Phase 4/5/6 — Full extraction pipeline for a single HTML page.
    Returns endpoints, params, responses, and auth hints.
    """

    def __init__(self) -> None:
        self._endpoint_detector = EndpointDetector()
        self._param_extractor = ParameterExtractor()
        self._response_extractor = ResponseExtractor()
        self._example_parser = ExampleParser()
        self._auth_detector = AuthDetector()

    def parse(self, html: str, page_url: str) -> dict:
        endpoints = self._endpoint_detector.detect(html, page_url)
        params = self._param_extractor.extract_from_html(html)
        responses = self._response_extractor.extract_from_html(html)
        examples = self._example_parser.extract_from_html(html)
        auth = self._auth_detector.detect_from_html(html, page_url)

        # Page-level title and description as fallbacks
        page_title = self.extract_title(html)
        page_description = self._extract_lead_paragraph(html)

        # Attach extracted params to endpoints that have none
        for ep in endpoints:
            if not ep.get("parameters") and params:
                path_params = self._param_extractor.extract_path_params(ep["path"])
                ep["parameters"] = path_params + params
            if not ep.get("responses") and responses:
                ep["responses"] = responses
            # Fall back to page title/description when per-endpoint values are missing
            if not ep.get("summary") and page_title:
                ep["summary"] = page_title
            if not ep.get("description") and page_description:
                ep["description"] = page_description

        # Attach page-level examples to endpoints (single-page = one endpoint per page)
        raw_examples = [e["data"] for e in examples]
        if raw_examples and endpoints:
            for ep in endpoints:
                if not ep.get("request_body") and raw_examples:
                    ep["request_body"] = {
                        "content_type": "application/json",
                        "schema": {},
                        "example": raw_examples[0],
                        "required": False,
                        "description": "",
                    }
                if len(raw_examples) > 1 and not ep.get("responses"):
                    ep["responses"] = {
                        "200": {"description": "OK", "example": raw_examples[1]}
                    }

        return {
            "endpoints": endpoints,
            "parameters": params,
            "responses": responses,
            "examples": raw_examples,
            "auth": auth,
        }

    def extract_title(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        # Prefer <h1> over <title>; skip cookie/consent headings
        for h1 in soup.find_all("h1"):
            text = h1.get_text(strip=True)
            if text and not _COOKIE_RE.search(text):
                return text
        tag = soup.find("title")
        if tag:
            # Strip common " | SiteName" suffixes
            text = tag.get_text(strip=True)
            for sep in (" | ", " - ", " – ", " :: "):
                if sep in text:
                    text = text.split(sep)[0].strip()
            return text
        return ""

    def extract_lead_paragraph(self, html: str) -> str:
        """Return the first meaningful paragraph after the main heading."""
        soup = BeautifulSoup(html, "lxml")
        # Skip cookie/consent h1s — find first API-relevant h1
        h1 = None
        for candidate in soup.find_all("h1"):
            if not _COOKIE_RE.search(candidate.get_text()):
                h1 = candidate
                break
        start = h1 if h1 else soup.find("body")
        if not start:
            return ""
        for sibling in (start.next_siblings if h1 else start.children):
            if not hasattr(sibling, "get_text"):
                continue
            if sibling.name in ("p", "div", "section"):
                text = sibling.get_text(" ", strip=True)
                if len(text) > 30:
                    return text[:800]
        return ""

    # keep old private name working so nothing else breaks
    _extract_lead_paragraph = extract_lead_paragraph
