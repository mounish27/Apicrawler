from __future__ import annotations

import re
from urllib.parse import urlparse


# Patterns that look like concrete IDs — replace with {param}
# Rules:
#   - pure numeric:  123, 4567890
#   - UUID:          8-4-4-4-12 hex
#   - hex hash:      24-32 hex chars (MongoDB ObjectId, SHA prefix)
#   - mixed token:   16+ chars that contain BOTH letters AND digits (e.g. Ab1Cd2Ef3Gh4)
#   - kebab with digit: at least one part contains a digit (abc-123, 99-items)
# Intentionally NOT matched: plain words like Employees, Jobs, Reports, xRefCode
_ID_SEGMENT_RE = re.compile(
    r"^(?:"
    r"\d+"                                                                    # pure numeric
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"        # UUID
    r"|[0-9a-f]{24,32}"                                                       # hex hash/ObjectId
    r"|(?=[a-zA-Z0-9]*[0-9])(?=[a-zA-Z0-9]*[a-zA-Z])[a-zA-Z0-9]{16,}"       # mixed alphanum token 16+ chars
    r"|[a-z0-9]*[0-9]+[a-z0-9]*-[a-z0-9]+"                                   # kebab with digit: 123-abc, abc123-def
    r"|[a-z0-9]+-[a-z0-9]*[0-9]+[a-z0-9]*"                                   # kebab with digit: abc-123, abc-def456
    r")$",
    re.IGNORECASE,
)


class EndpointNormalizer:
    """
    Phase 11 — Normalizes raw endpoint paths.

    Converts concrete ID segments into path parameters:
      /users/123          → /users/{id}
      /orders/abc-123/items → /orders/{id}/items
    """

    def normalize_path(self, path: str) -> str:
        if not path:
            return path
        parts = path.strip("/").split("/")
        normalized: list[str] = []
        param_counter: dict[str, int] = {}

        for i, part in enumerate(parts):
            if part.startswith("{") and part.endswith("}"):
                normalized.append(part)
                continue

            if _ID_SEGMENT_RE.match(part):
                # Infer param name from preceding segment
                prev = normalized[-1].strip("{}") if normalized else "resource"
                # Singularize simple plurals
                param_name = self._singularize(prev) + "Id"
                # Avoid duplicate names
                count = param_counter.get(param_name, 0)
                param_counter[param_name] = count + 1
                if count:
                    param_name = f"{param_name}{count}"
                normalized.append("{" + param_name + "}")
            else:
                normalized.append(part)

        return "/" + "/".join(normalized)

    def normalize_endpoint(self, ep: dict) -> dict:
        ep = dict(ep)
        ep["path"] = self.normalize_path(ep.get("path", "/"))
        return ep

    def normalize_all(self, endpoints: list[dict]) -> list[dict]:
        return [self.normalize_endpoint(ep) for ep in endpoints]

    # ── private ───────────────────────────────────────────────────────────

    def _singularize(self, word: str) -> str:
        """Simple English singularizer for common plural path segments."""
        if word.endswith("ies"):
            return word[:-3] + "y"
        if word.endswith("ses") or word.endswith("xes") or word.endswith("zes"):
            return word[:-2]
        if word.endswith("s") and len(word) > 3:
            return word[:-1]
        return word
