from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


class SwaggerGenerator:
    """
    Phase 9 — Generates a Swagger 2.0 specification.
    Useful for tools that don't yet support OpenAPI 3.x.
    """

    def generate(
        self,
        endpoints: list[dict],
        title: str = "API Documentation",
        version: str = "1.0.0",
        host: str = "api.example.com",
        base_path: str = "/",
        schemes: list[str] | None = None,
        auth_config: dict | None = None,
    ) -> dict:
        paths: dict[str, dict] = {}
        definitions: dict[str, dict] = {}

        for ep in endpoints:
            path = ep.get("path", "/")
            method = ep.get("method", "GET").lower()
            if path not in paths:
                paths[path] = {}
            op, defs = self._build_operation(ep)
            paths[path][method] = op
            definitions.update(defs)

        spec: dict[str, Any] = {
            "swagger": "2.0",
            "info": {"title": title, "version": version},
            "host": host,
            "basePath": base_path,
            "schemes": schemes or ["https"],
            "consumes": ["application/json"],
            "produces": ["application/json"],
            "paths": paths,
        }

        if definitions:
            spec["definitions"] = definitions

        if auth_config:
            sec_defs = self._build_security_definitions(auth_config)
            if sec_defs:
                spec["securityDefinitions"] = sec_defs
                scheme_name = next(iter(sec_defs))
                spec["security"] = [{scheme_name: []}]

        return spec

    # ── private ───────────────────────────────────────────────────────────

    def _build_operation(self, ep: dict) -> tuple[dict, dict]:
        definitions: dict = {}
        op: dict[str, Any] = {
            "responses": {"200": {"description": "OK"}},
        }
        if ep.get("summary"):
            op["summary"] = ep["summary"]
        if ep.get("description"):
            op["description"] = ep["description"]
        if ep.get("tags"):
            op["tags"] = ep["tags"]
        if ep.get("operation_id"):
            op["operationId"] = ep["operation_id"]
        if ep.get("deprecated"):
            op["deprecated"] = True

        params: list[dict] = []
        # Path params
        for m in re.findall(r"\{(\w+)\}", ep.get("path", "")):
            params.append({"name": m, "in": "path", "required": True, "type": "string"})

        for p in ep.get("parameters") or []:
            sw_p: dict = {
                "name": p.get("name", "param"),
                "in": p.get("location", "query"),
                "required": p.get("required", False),
                "type": p.get("type", "string"),
            }
            if p.get("description"):
                sw_p["description"] = p["description"]
            if p.get("enum"):
                sw_p["enum"] = p["enum"]
            params.append(sw_p)

        rb = ep.get("request_body")
        if rb:
            schema = rb.get("schema") or {"type": "object"}
            def_name = self._op_name(ep) + "Body"
            if rb.get("example") is not None:
                schema = dict(schema)
                schema["example"] = rb["example"]
            definitions[def_name] = schema
            params.append({
                "name": "body",
                "in": "body",
                "required": rb.get("required", True),
                "schema": {"$ref": f"#/definitions/{def_name}"},
            })

        if params:
            op["parameters"] = params

        responses: dict = {}
        for code, resp in (ep.get("responses") or {}).items():
            r: dict = {"description": resp.get("description", "Response") if isinstance(resp, dict) else "Response"}
            schema = resp.get("schema") if isinstance(resp, dict) else None
            example = resp.get("example") if isinstance(resp, dict) else None
            if schema or example:
                def_name = self._op_name(ep) + f"Response{code}"
                final_schema = dict(schema) if schema else {"type": "object"}
                if example is not None:
                    final_schema["example"] = example
                definitions[def_name] = final_schema
                r["schema"] = {"$ref": f"#/definitions/{def_name}"}
            responses[code] = r

        op["responses"] = responses or {"200": {"description": "OK"}}
        return op, definitions

    def _build_security_definitions(self, auth_config: dict) -> dict:
        auth_type = auth_config.get("auth_type", "none")
        if auth_type == "bearer":
            return {"bearerAuth": {"type": "apiKey", "in": "header", "name": "Authorization"}}
        if auth_type == "oauth2":
            return {
                "oauth2": {
                    "type": "oauth2",
                    "flow": "application",
                    "tokenUrl": auth_config.get("token_url", "https://auth.example.com/token"),
                    "scopes": auth_config.get("scopes", {}),
                }
            }
        if auth_type == "api_key":
            return {"apiKey": {"type": "apiKey", "in": "header", "name": auth_config.get("header_name", "X-API-Key")}}
        if auth_type == "basic":
            return {"basicAuth": {"type": "basic"}}
        return {}

    def _op_name(self, ep: dict) -> str:
        if ep.get("operation_id"):
            return ep["operation_id"]
        path = ep.get("path", "/").strip("/").replace("/", "_").replace("{", "").replace("}", "")
        return f"{ep.get('method', 'get').capitalize()}_{path}" if path else "Root"
