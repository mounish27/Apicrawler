from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from normalization.component_builder import ComponentBuilder


_METHOD_ORDER = ["get", "post", "put", "patch", "delete", "options", "head"]


class OpenAPIGenerator:
    """
    Phase 9 — Generates an OpenAPI 3.1.0 specification from a list of endpoints.
    """

    def generate(
        self,
        endpoints: list[dict],
        title: str = "API Documentation",
        version: str = "1.0.0",
        servers: list[str] | None = None,
        auth_config: dict | None = None,
        description: str = "",
        security_schemes: dict | None = None,
    ) -> dict:
        builder = ComponentBuilder(min_reuse=2)
        endpoints = builder.extract_endpoint_schemas(endpoints)
        component_schemas = builder.build_components()

        paths: dict[str, dict] = {}
        for ep in endpoints:
            path = ep.get("path", "/")
            method = ep.get("method", "GET").lower()
            if path not in paths:
                paths[path] = {}
            paths[path][method] = self._build_operation(ep)

        spec: dict[str, Any] = {
            "openapi": "3.1.0",
            "info": {
                "title": title,
                "version": version,
                "description": description,
            },
            "servers": [{"url": s} for s in (servers or ["/"])],
            "paths": paths,
        }

        # Build components
        components: dict[str, Any] = {}
        if component_schemas:
            components["schemas"] = component_schemas

        # Security schemes
        schemes = security_schemes or {}
        if not schemes and auth_config:
            from extraction.auth_detector import AuthDetector
            schemes = AuthDetector().build_security_schemes(auth_config)
        if schemes:
            components["securitySchemes"] = schemes

        if components:
            spec["components"] = components

        # Global security
        if schemes:
            scheme_name = next(iter(schemes))
            spec["security"] = [{scheme_name: []}]

        # Collect tags
        tags: dict[str, str] = {}
        for ep in endpoints:
            for tag in ep.get("tags") or []:
                tags[tag] = tag
        if tags:
            spec["tags"] = [{"name": t} for t in tags]

        return spec

    # ── private ───────────────────────────────────────────────────────────

    def _build_operation(self, ep: dict) -> dict:
        op: dict[str, Any] = {}

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

        # Parameters
        params = ep.get("parameters") or []
        # Add path params from the path template
        path_params = self._path_params_from_path(ep.get("path", ""))
        existing_names = {p.get("name") for p in params}
        for pp in path_params:
            if pp["name"] not in existing_names:
                params = [pp] + params

        if params:
            op["parameters"] = [self._build_parameter(p) for p in params]

        # Request body
        rb = ep.get("request_body")
        if rb:
            op["requestBody"] = self._build_request_body(rb)

        # Responses
        responses = ep.get("responses") or {}
        if not responses:
            responses = {"200": {"description": "OK"}}
        op["responses"] = {
            code: self._build_response(resp)
            for code, resp in responses.items()
        }

        return op

    def _build_parameter(self, p: dict) -> dict:
        param: dict[str, Any] = {
            "name": p.get("name", "param"),
            "in": p.get("location", "query"),
            "required": p.get("required", p.get("location") == "path"),
        }
        if p.get("description"):
            param["description"] = p["description"]
        if p.get("deprecated"):
            param["deprecated"] = True

        schema: dict[str, Any] = {"type": p.get("type", "string")}
        if p.get("enum"):
            schema["enum"] = p["enum"]
        if p.get("example") is not None:
            schema["example"] = p["example"]
        param["schema"] = schema
        return param

    def _build_request_body(self, rb: dict) -> dict:
        ct = rb.get("content_type", "application/json")
        schema = rb.get("schema") or {}
        media: dict[str, Any] = {"schema": schema}
        if rb.get("example") is not None:
            media["example"] = rb["example"]
        body: dict[str, Any] = {
            "required": rb.get("required", True),
            "content": {ct: media},
        }
        if rb.get("description"):
            body["description"] = rb["description"]
        return body

    def _build_response(self, resp: dict | str) -> dict:
        if isinstance(resp, str):
            return {"description": resp}
        r: dict[str, Any] = {"description": resp.get("description") or "Response"}
        schema = resp.get("schema")
        example = resp.get("example")
        if schema or example:
            media: dict[str, Any] = {}
            if schema:
                media["schema"] = schema
            if example is not None:
                media["example"] = example
            r["content"] = {"application/json": media}
        return r

    def _path_params_from_path(self, path: str) -> list[dict]:
        return [
            {
                "name": m,
                "location": "path",
                "type": "string",
                "required": True,
                "description": "",
            }
            for m in re.findall(r"\{(\w+)\}", path)
        ]
