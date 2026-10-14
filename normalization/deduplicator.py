from __future__ import annotations

from .endpoint_normalizer import EndpointNormalizer


class Deduplicator:
    """
    Phase 11 — Deduplicates endpoint lists.
    Endpoints with the same (method, normalized_path) are merged,
    preferring the richer record (more params, has description, etc.).
    """

    def __init__(self) -> None:
        self._normalizer = EndpointNormalizer()

    def deduplicate(self, endpoints: list[dict]) -> list[dict]:
        seen: dict[tuple[str, str], dict] = {}

        for ep in endpoints:
            normalized_path = self._normalizer.normalize_path(ep.get("path", "/"))
            key = (ep.get("method", "GET").upper(), normalized_path)

            if key not in seen:
                ep_copy = dict(ep)
                ep_copy["path"] = normalized_path
                seen[key] = ep_copy
            else:
                seen[key] = self._merge(seen[key], ep)

        return list(seen.values())

    # ── private ───────────────────────────────────────────────────────────

    def _merge(self, a: dict, b: dict) -> dict:
        result = dict(a)

        # Prefer the record with more description
        if not result.get("description") and b.get("description"):
            result["description"] = b["description"]
        if not result.get("summary") and b.get("summary"):
            result["summary"] = b["summary"]

        # Merge parameter lists (prefer longer)
        params_a = result.get("parameters") or []
        params_b = b.get("parameters") or []
        if len(params_b) > len(params_a):
            result["parameters"] = params_b
        elif len(params_a) == len(params_b):
            # Merge by name
            by_name = {p["name"]: p for p in params_a}
            for p in params_b:
                name = p.get("name", "")
                if name not in by_name:
                    by_name[name] = p
            result["parameters"] = list(by_name.values())

        # Prefer richer request body (keep the one with an example)
        rb_a = result.get("request_body")
        rb_b = b.get("request_body")
        if not rb_a and rb_b:
            result["request_body"] = rb_b
        elif rb_a and rb_b and not rb_a.get("example") and rb_b.get("example"):
            result["request_body"] = rb_b

        # Merge responses — prefer entries that have examples
        resp_a = result.get("responses") or {}
        resp_b = b.get("responses") or {}
        merged_resp = {**resp_b, **resp_a}
        for code in set(resp_a) & set(resp_b):
            if not resp_a[code].get("example") and resp_b[code].get("example"):
                merged_resp[code] = resp_b[code]
        result["responses"] = merged_resp

        # Merge tags
        tags = list({t for t in (result.get("tags") or []) + (b.get("tags") or [])})
        if tags:
            result["tags"] = tags

        # Auth: prefer known over unknown/none
        auth_a = result.get("auth_type", "unknown")
        auth_b = b.get("auth_type", "unknown")
        if auth_a in ("unknown", "none") and auth_b not in ("unknown", "none"):
            result["auth_type"] = auth_b

        return result
