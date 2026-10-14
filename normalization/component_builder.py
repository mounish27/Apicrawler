from __future__ import annotations

import hashlib
import re
from typing import Any


def _schema_hash(schema: dict) -> str:
    import json
    return hashlib.md5(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:8]


def _to_pascal(name: str) -> str:
    """Convert snake_case or camelCase to PascalCase."""
    parts = re.split(r"[_\-\s]+", name)
    return "".join(p.capitalize() for p in parts if p)


class ComponentBuilder:
    """
    Phase 9/11 — Extracts reusable schemas into OpenAPI components/schemas.
    Replaces inline schemas with $ref where appropriate.
    """

    def __init__(self, min_reuse: int = 2) -> None:
        self._min_reuse = min_reuse
        self._schema_counts: dict[str, int] = {}
        self._schema_map: dict[str, dict] = {}
        self._name_map: dict[str, str] = {}

    def collect(self, name: str, schema: dict) -> None:
        """Register a schema candidate under a suggested name."""
        h = _schema_hash(schema)
        self._schema_counts[h] = self._schema_counts.get(h, 0) + 1
        if h not in self._schema_map:
            self._schema_map[h] = schema
            self._name_map[h] = _to_pascal(name)

    def build_components(self) -> dict[str, dict]:
        """Return schemas/{Name} dict for schemas used >= min_reuse times."""
        components: dict[str, dict] = {}
        used_names: set[str] = set()
        for h, schema in self._schema_map.items():
            if self._schema_counts[h] >= self._min_reuse:
                name = self._name_map[h]
                # Ensure unique names
                if name in used_names:
                    name = f"{name}{h[:4]}"
                used_names.add(name)
                components[name] = schema
        return components

    def ref_or_inline(self, name: str, schema: dict) -> dict:
        """Return $ref if reusable, else the schema inline."""
        h = _schema_hash(schema)
        if self._schema_counts.get(h, 0) >= self._min_reuse:
            ref_name = self._name_map.get(h, _to_pascal(name))
            return {"$ref": f"#/components/schemas/{ref_name}"}
        return schema

    def extract_endpoint_schemas(self, endpoints: list[dict]) -> list[dict]:
        """
        First pass: collect all schemas from endpoints.
        Returns updated endpoints with $ref where reusable.
        """
        # Pass 1: collect
        for ep in endpoints:
            rb = ep.get("request_body")
            if rb and rb.get("schema"):
                op_name = ep.get("operation_id") or ep.get("path", "").strip("/").replace("/", "_")
                self.collect(f"{op_name}Request", rb["schema"])
            for code, resp in (ep.get("responses") or {}).items():
                if resp and resp.get("schema"):
                    op_name = ep.get("operation_id") or ep.get("path", "").strip("/").replace("/", "_")
                    self.collect(f"{op_name}Response{code}", resp["schema"])

        # Pass 2: replace with $refs
        result = []
        for ep in endpoints:
            ep = dict(ep)
            rb = ep.get("request_body")
            if rb and rb.get("schema"):
                op_name = ep.get("operation_id") or ep.get("path", "").strip("/").replace("/", "_")
                rb = dict(rb)
                rb["schema"] = self.ref_or_inline(f"{op_name}Request", rb["schema"])
                ep["request_body"] = rb
            responses = {}
            for code, resp in (ep.get("responses") or {}).items():
                if resp and resp.get("schema"):
                    op_name = ep.get("operation_id") or ep.get("path", "").strip("/").replace("/", "_")
                    resp = dict(resp)
                    resp["schema"] = self.ref_or_inline(f"{op_name}Response{code}", resp["schema"])
                responses[code] = resp
            ep["responses"] = responses
            result.append(ep)
        return result
