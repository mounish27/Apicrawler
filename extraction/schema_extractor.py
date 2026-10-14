from __future__ import annotations

import re
from typing import Any


class SchemaExtractor:
    """
    Phase 7 — Infers JSON Schema from example data.
    Merges multiple examples into a single schema with nullable/optional fields.
    """

    def infer(self, example: Any) -> dict:
        """Infer an OpenAPI-compatible JSON schema from a Python value."""
        return self._infer_value(example)

    def merge(self, schemas: list[dict]) -> dict:
        """Merge multiple schemas into one, marking optional fields nullable."""
        if not schemas:
            return {"type": "object"}
        if len(schemas) == 1:
            return schemas[0]

        base = schemas[0]
        for other in schemas[1:]:
            base = self._merge_two(base, other)
        return base

    def infer_from_examples(self, examples: list[Any]) -> dict:
        """Infer and merge schemas from a list of example values."""
        schemas = [self.infer(ex) for ex in examples if ex is not None]
        return self.merge(schemas) if schemas else {"type": "object"}

    # ── private ───────────────────────────────────────────────────────────

    def _infer_value(self, value: Any) -> dict:
        if value is None:
            return {"nullable": True, "type": "string"}
        if isinstance(value, bool):
            return {"type": "boolean", "example": value}
        if isinstance(value, int):
            return {"type": "integer", "example": value}
        if isinstance(value, float):
            return {"type": "number", "format": "float", "example": value}
        if isinstance(value, str):
            schema: dict = {"type": "string", "example": value}
            fmt = self._detect_string_format(value)
            if fmt:
                schema["format"] = fmt
            return schema
        if isinstance(value, list):
            return self._infer_array(value)
        if isinstance(value, dict):
            return self._infer_object(value)
        return {"type": "string"}

    def _infer_array(self, arr: list) -> dict:
        if not arr:
            return {"type": "array", "items": {}}
        item_schemas = [self._infer_value(item) for item in arr[:10]]
        merged_items = self.merge(item_schemas)
        return {"type": "array", "items": merged_items}

    def _infer_object(self, obj: dict) -> dict:
        properties: dict = {}
        required: list[str] = []
        for key, val in obj.items():
            properties[key] = self._infer_value(val)
            if val is not None:
                required.append(key)
        schema: dict = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def _merge_two(self, a: dict, b: dict) -> dict:
        if a.get("type") != b.get("type"):
            return {"oneOf": [a, b]}

        if a.get("type") == "object":
            props_a = a.get("properties", {})
            props_b = b.get("properties", {})
            req_a = set(a.get("required", []))
            req_b = set(b.get("required", []))

            merged_props: dict = {}
            all_keys = set(props_a) | set(props_b)
            for key in all_keys:
                if key in props_a and key in props_b:
                    merged_props[key] = self._merge_two(props_a[key], props_b[key])
                elif key in props_a:
                    merged_props[key] = {**props_a[key], "nullable": True}
                else:
                    merged_props[key] = {**props_b[key], "nullable": True}

            required = list(req_a & req_b)
            result: dict = {"type": "object", "properties": merged_props}
            if required:
                result["required"] = required
            return result

        if a.get("type") == "array":
            items_a = a.get("items", {})
            items_b = b.get("items", {})
            return {"type": "array", "items": self._merge_two(items_a, items_b)}

        # Primitive types — keep first, add example if missing
        merged = dict(a)
        if "example" not in merged and "example" in b:
            merged["example"] = b["example"]
        return merged

    def _detect_string_format(self, value: str) -> str | None:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*", value):
            return "date-time"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return "date"
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value, re.IGNORECASE):
            return "uuid"
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            return "email"
        if re.fullmatch(r"https?://\S+", value):
            return "uri"
        return None
