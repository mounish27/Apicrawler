from __future__ import annotations

import re
from typing import Any


class SwaggerParser:
    """
    Parses OpenAPI 3.x and Swagger 2.x specs into a normalized endpoint list.
    Also handles Postman collections.
    """

    def parse(self, spec: dict, source_url: str = "") -> list[dict]:
        version = spec.get("openapi") or spec.get("swagger", "")
        if str(version).startswith("3"):
            return self._parse_openapi3(spec, source_url)
        elif str(version).startswith("2"):
            return self._parse_swagger2(spec, source_url)
        elif self._is_postman(spec):
            return self._parse_postman(spec, source_url)
        return []

    # ── OpenAPI 3.x ───────────────────────────────────────────────────────

    def _parse_openapi3(self, spec: dict, source_url: str) -> list[dict]:
        endpoints = []
        servers = spec.get("servers", [{}])
        base = servers[0].get("url", "") if servers else ""
        paths = spec.get("paths", {})
        components = spec.get("components", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            common_params = path_item.get("parameters", [])

            for method in ("get", "post", "put", "patch", "delete", "options", "head"):
                op = path_item.get(method)
                if not isinstance(op, dict):
                    continue

                params = self._resolve_params(
                    common_params + op.get("parameters", []), components
                )
                request_body = self._resolve_body(op.get("requestBody"), components)
                responses = self._resolve_responses(op.get("responses", {}), components)
                security = op.get("security") or spec.get("security", [])

                endpoints.append({
                    "method": method.upper(),
                    "path": path,
                    "summary": op.get("summary") or op.get("operationId", ""),
                    "description": op.get("description", ""),
                    "tags": op.get("tags", []),
                    "parameters": params,
                    "request_body": request_body,
                    "responses": responses,
                    "auth_type": self._infer_auth(security, spec),
                    "deprecated": op.get("deprecated", False),
                    "source_url": source_url,
                    "operation_id": op.get("operationId"),
                })
        return endpoints

    # ── Swagger 2.x ───────────────────────────────────────────────────────

    def _parse_swagger2(self, spec: dict, source_url: str) -> list[dict]:
        endpoints = []
        base_path = spec.get("basePath", "")
        paths = spec.get("paths", {})
        definitions = spec.get("definitions", {})
        global_security = spec.get("security", [])

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            common_params = path_item.get("parameters", [])

            for method in ("get", "post", "put", "patch", "delete", "options", "head"):
                op = path_item.get(method)
                if not isinstance(op, dict):
                    continue

                all_params = common_params + op.get("parameters", [])
                params = [p for p in all_params if p.get("in") != "body"]
                body_params = [p for p in all_params if p.get("in") == "body"]
                request_body = None
                if body_params:
                    bp = body_params[0]
                    request_body = {
                        "content_type": "application/json",
                        "description": bp.get("description", ""),
                        "schema": bp.get("schema"),
                        "required": bp.get("required", False),
                    }

                responses = {
                    str(code): {
                        "description": r.get("description", ""),
                        "schema": r.get("schema"),
                    }
                    for code, r in op.get("responses", {}).items()
                }

                security = op.get("security") or global_security
                endpoints.append({
                    "method": method.upper(),
                    "path": base_path + path,
                    "summary": op.get("summary") or op.get("operationId", ""),
                    "description": op.get("description", ""),
                    "tags": op.get("tags", []),
                    "parameters": [self._norm_param(p) for p in params],
                    "request_body": request_body,
                    "responses": responses,
                    "auth_type": self._infer_auth(security, spec),
                    "deprecated": op.get("deprecated", False),
                    "source_url": source_url,
                    "operation_id": op.get("operationId"),
                })
        return endpoints

    # ── Postman ───────────────────────────────────────────────────────────

    def _parse_postman(self, collection: dict, source_url: str) -> list[dict]:
        endpoints: list[dict] = []
        items = collection.get("item") or collection.get("collection", {}).get("item", [])
        self._walk_postman(items, endpoints, source_url, [])
        return endpoints

    def _walk_postman(self, items: list, out: list, source_url: str, tags: list[str]) -> None:
        for item in items:
            if "item" in item:
                self._walk_postman(item["item"], out, source_url, tags + [item.get("name", "")])
                continue
            req = item.get("request", {})
            if not req:
                continue
            method = req.get("method", "GET").upper()
            url_obj = req.get("url", {})
            if isinstance(url_obj, str):
                path = "/" + "/".join(url_obj.split("/")[3:])
            else:
                path = "/" + "/".join(url_obj.get("path", []))

            params = [
                {"name": q.get("key", ""), "location": "query",
                 "description": q.get("description", ""), "required": False}
                for q in (url_obj.get("query") or [] if isinstance(url_obj, dict) else [])
            ]
            out.append({
                "method": method,
                "path": path or "/",
                "summary": item.get("name", ""),
                "description": req.get("description", ""),
                "tags": tags,
                "parameters": params,
                "request_body": None,
                "responses": {},
                "auth_type": "unknown",
                "deprecated": False,
                "source_url": source_url,
            })

    # ── helpers ───────────────────────────────────────────────────────────

    def _resolve_params(self, params: list, components: dict) -> list[dict]:
        resolved = []
        schemas = components.get("parameters", {})
        for p in params:
            if "$ref" in p:
                ref_name = p["$ref"].split("/")[-1]
                p = schemas.get(ref_name, p)
            resolved.append(self._norm_param(p))
        return resolved

    def _norm_param(self, p: dict) -> dict:
        schema = p.get("schema", {}) or {}
        return {
            "name": p.get("name", ""),
            "location": p.get("in", "query"),
            "type": schema.get("type") or p.get("type", "string"),
            "required": p.get("required", p.get("in") == "path"),
            "description": p.get("description", ""),
            "enum": schema.get("enum") or p.get("enum"),
            "example": schema.get("example") or p.get("example"),
            "deprecated": p.get("deprecated", False),
        }

    def _resolve_body(self, body: dict | None, components: dict) -> dict | None:
        if not body:
            return None
        content = body.get("content", {})
        for ct, media in content.items():
            schema = media.get("schema", {})
            # Pick up example from media object or schema
            example = (
                media.get("example")
                or (media.get("examples") or {}).get("default", {}).get("value")
                or schema.get("example")
            )
            result = {
                "content_type": ct,
                "schema": schema,
                "required": body.get("required", False),
                "description": body.get("description", ""),
            }
            if example is not None:
                result["example"] = example
            return result
        return None

    def _resolve_responses(self, responses: dict, components: dict) -> dict:
        out = {}
        for code, resp in responses.items():
            if "$ref" in resp:
                ref_name = resp["$ref"].split("/")[-1]
                resp = components.get("responses", {}).get(ref_name, resp)
            content = resp.get("content", {})
            schema = None
            example = None
            for ct, media in content.items():
                schema = media.get("schema")
                example = (
                    media.get("example")
                    or (media.get("examples") or {}).get("default", {}).get("value")
                    or (schema or {}).get("example")
                )
                break
            entry = {
                "description": resp.get("description", ""),
                "schema": schema,
            }
            if example is not None:
                entry["example"] = example
            out[str(code)] = entry
        return out

    def _infer_auth(self, security: list, spec: dict) -> str:
        if not security:
            return "none"
        schemes = (
            spec.get("components", {}).get("securitySchemes", {})
            or spec.get("securityDefinitions", {})
        )
        for req in security:
            for name in req:
                s = schemes.get(name, {})
                t = s.get("type", "").lower()
                scheme = s.get("scheme", "").lower()
                if t == "http" and scheme == "bearer":
                    return "bearer"
                if t == "oauth2":
                    return "oauth2"
                if t == "apikey":
                    return "api_key"
                if t == "http" and scheme == "basic":
                    return "basic"
        return "unknown"

    def _is_postman(self, data: dict) -> bool:
        info = data.get("info", {})
        return isinstance(info, dict) and "_postman_id" in info
