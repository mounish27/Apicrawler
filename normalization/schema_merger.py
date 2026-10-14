from __future__ import annotations

from typing import Any

from extraction.schema_extractor import SchemaExtractor


class SchemaMerger:
    """
    Phase 7/11 — Merges multiple partial schemas collected from different pages
    into a unified schema set.
    """

    def __init__(self) -> None:
        self._extractor = SchemaExtractor()

    def merge_response_schemas(self, schemas: list[dict | None]) -> dict | None:
        valid = [s for s in schemas if s]
        if not valid:
            return None
        return self._extractor.merge(valid)

    def merge_examples_to_schema(self, examples: list[Any]) -> dict:
        return self._extractor.infer_from_examples(examples)

    def enrich_endpoint_schemas(self, endpoints: list[dict], page_examples: list[Any]) -> list[dict]:
        """
        Attach inferred schema to endpoints that have no request_body schema,
        using page-level examples as a heuristic for POST/PUT/PATCH bodies.
        """
        if not page_examples:
            return endpoints

        inferred = self._extractor.infer_from_examples(page_examples)
        result = []
        for ep in endpoints:
            ep = dict(ep)
            method = ep.get("method", "GET").upper()
            if method in ("POST", "PUT", "PATCH"):
                if not ep.get("request_body"):
                    ep["request_body"] = {
                        "content_type": "application/json",
                        "schema": inferred,
                        "required": True,
                        "description": "",
                    }
            result.append(ep)
        return result
