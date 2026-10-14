from __future__ import annotations

import uuid
from typing import Any


class GraphQLGenerator:
    """
    Phase 13 — Generates schema.graphql and Postman GraphQL requests
    from a GraphQL introspection result.
    """

    def generate_schema(self, introspection: dict) -> str:
        """Convert a GraphQL introspection result into SDL schema text."""
        schema = introspection.get("__schema") or introspection.get("data", {}).get("__schema", {})
        if not schema:
            return ""

        types = schema.get("types", [])
        lines: list[str] = []

        for t in types:
            name = t.get("name", "")
            kind = t.get("kind", "")

            if name.startswith("__") or kind == "SCALAR":
                continue

            if kind == "OBJECT":
                lines.append(self._render_object(t))
            elif kind == "INTERFACE":
                lines.append(self._render_interface(t))
            elif kind == "UNION":
                lines.append(self._render_union(t))
            elif kind == "ENUM":
                lines.append(self._render_enum(t))
            elif kind == "INPUT_OBJECT":
                lines.append(self._render_input(t))

        return "\n\n".join(l for l in lines if l)

    def generate_postman_requests(
        self,
        introspection: dict,
        endpoint_url: str = "{{graphqlUrl}}",
    ) -> dict:
        """Generate a Postman collection with GraphQL query/mutation requests."""
        schema = introspection.get("__schema") or introspection.get("data", {}).get("__schema", {})
        types = schema.get("types", [])

        query_type = schema.get("queryType", {}).get("name", "Query")
        mutation_type = (schema.get("mutationType") or {}).get("name", "Mutation")

        items: list[dict] = []
        for t in types:
            name = t.get("name", "")
            if name not in (query_type, mutation_type):
                continue
            op_type = "query" if name == query_type else "mutation"
            folder_items = []
            for field in t.get("fields") or []:
                req = self._build_gql_request(field, op_type, endpoint_url)
                folder_items.append(req)
            if folder_items:
                items.append({"name": name, "item": folder_items})

        return {
            "info": {
                "_postman_id": str(uuid.uuid4()),
                "name": "GraphQL API",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": items,
            "variable": [{"key": "graphqlUrl", "value": endpoint_url, "type": "string"}],
        }

    # ── private ───────────────────────────────────────────────────────────

    def _type_ref(self, ref: dict) -> str:
        kind = ref.get("kind", "")
        name = ref.get("name")
        of_type = ref.get("ofType")
        if kind == "NON_NULL":
            return self._type_ref(of_type) + "!" if of_type else "String!"
        if kind == "LIST":
            return f"[{self._type_ref(of_type)}]" if of_type else "[String]"
        return name or "String"

    def _render_object(self, t: dict) -> str:
        name = t.get("name", "")
        interfaces = t.get("interfaces") or []
        iface_str = f" implements {' & '.join(i['name'] for i in interfaces)}" if interfaces else ""
        fields = self._render_fields(t.get("fields") or [])
        return f"type {name}{iface_str} {{\n{fields}\n}}"

    def _render_interface(self, t: dict) -> str:
        name = t.get("name", "")
        fields = self._render_fields(t.get("fields") or [])
        return f"interface {name} {{\n{fields}\n}}"

    def _render_union(self, t: dict) -> str:
        name = t.get("name", "")
        types = " | ".join(p["name"] for p in (t.get("possibleTypes") or []))
        return f"union {name} = {types}"

    def _render_enum(self, t: dict) -> str:
        name = t.get("name", "")
        values = "\n  ".join(v["name"] for v in (t.get("enumValues") or []))
        return f"enum {name} {{\n  {values}\n}}"

    def _render_input(self, t: dict) -> str:
        name = t.get("name", "")
        fields = self._render_input_fields(t.get("inputFields") or [])
        return f"input {name} {{\n{fields}\n}}"

    def _render_fields(self, fields: list) -> str:
        lines = []
        for f in fields:
            type_str = self._type_ref(f.get("type", {}))
            args = self._render_args(f.get("args") or [])
            desc = f"  \"\"\"{f['description']}\"\"\"\n" if f.get("description") else ""
            lines.append(f"{desc}  {f['name']}{args}: {type_str}")
        return "\n".join(lines)

    def _render_input_fields(self, fields: list) -> str:
        return "\n".join(
            f"  {f['name']}: {self._type_ref(f.get('type', {}))}"
            for f in fields
        )

    def _render_args(self, args: list) -> str:
        if not args:
            return ""
        parts = ", ".join(f"{a['name']}: {self._type_ref(a.get('type', {}))}" for a in args)
        return f"({parts})"

    def _build_gql_request(self, field: dict, op_type: str, url: str) -> dict:
        name = field.get("name", "")
        args = field.get("args") or []
        arg_defs = ", ".join(f"${a['name']}: {self._type_ref(a.get('type', {}))}" for a in args)
        arg_use = ", ".join(f"{a['name']}: ${a['name']}" for a in args)
        arg_defs_str = f"({arg_defs})" if arg_defs else ""
        arg_use_str = f"({arg_use})" if arg_use else ""

        query = f"{op_type} {name}{arg_defs_str} {{\n  {name}{arg_use_str}\n}}"

        variables: dict = {}
        for a in args:
            variables[a["name"]] = None

        return {
            "name": name,
            "request": {
                "method": "POST",
                "header": [{"key": "Content-Type", "value": "application/json"}],
                "url": {"raw": url, "host": [url]},
                "body": {
                    "mode": "graphql",
                    "graphql": {
                        "query": query,
                        "variables": str(variables),
                    },
                },
            },
            "response": [],
        }
