from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag


_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n([\s\S]*?)\n```", re.IGNORECASE
)
_BARE_JSON_RE = re.compile(r"(\{[\s\S]*?\}|\[[\s\S]*?\])")

# Labels that suggest a block is a request body example
_REQUEST_HINTS = re.compile(
    r"\brequest\b|\bbody\b|\bpayload\b|\binput\b|\bsend\b", re.IGNORECASE
)
# Labels that suggest a block is a response example
_RESPONSE_HINTS = re.compile(
    r"\bresponse\b|\bresponse body\b|\breturn\b|\boutput\b|\bsample response\b|\bexample response\b",
    re.IGNORECASE,
)


class ExampleParser:
    """
    Phase 6/7 — Extracts JSON/XML example payloads from HTML content.
    Finds code blocks, <pre> tags, and inline JSON.
    Each example is labelled as 'request', 'response', or None.
    """

    def extract_from_html(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        examples: list[dict] = []
        seen: set[str] = set()

        # <pre><code> blocks
        for pre in soup.find_all("pre"):
            text = pre.get_text()
            parsed = self._try_json(text)
            if parsed is not None:
                key = json.dumps(parsed, sort_keys=True)[:200]
                if key not in seen:
                    seen.add(key)
                    label = self._label_from_context(pre)
                    kind = self._classify(label, pre)
                    examples.append({
                        "label": label,
                        "kind": kind,
                        "data": parsed,
                        "source": "pre",
                    })

        # Markdown-style fenced code blocks in raw text
        raw = soup.get_text()
        for m in _JSON_FENCE_RE.finditer(raw):
            parsed = self._try_json(m.group(1))
            if parsed is not None:
                key = json.dumps(parsed, sort_keys=True)[:200]
                if key not in seen:
                    seen.add(key)
                    examples.append({
                        "label": None,
                        "kind": None,
                        "data": parsed,
                        "source": "fence",
                    })

        return examples

    def attach_to_endpoints(self, endpoints: list[dict], examples: list[dict]) -> list[dict]:
        """
        Attach page examples to endpoints.
        - Single endpoint on page: all examples go to it.
        - Multiple endpoints: match by label similarity to summary/path.
        """
        if not examples or not endpoints:
            return endpoints

        if len(endpoints) == 1:
            ep = endpoints[0]
            req_ex = [e["data"] for e in examples if e.get("kind") == "request"]
            res_ex = [e["data"] for e in examples if e.get("kind") == "response"]
            # Fallback: first example is request, second is response
            if not req_ex and not res_ex:
                all_data = [e["data"] for e in examples]
                req_ex = [all_data[0]] if all_data else []
                res_ex = [all_data[1]] if len(all_data) > 1 else []
            if req_ex:
                if not ep.get("request_body"):
                    ep["request_body"] = {"content_type": "application/json",
                                          "schema": {}, "required": False, "description": ""}
                ep["request_body"]["example"] = req_ex[0]
            if res_ex:
                if "200" not in ep.get("responses", {}):
                    ep.setdefault("responses", {})["200"] = {"description": "OK", "schema": None}
                ep["responses"]["200"]["example"] = res_ex[0]
        else:
            # Multi-endpoint: best-effort matching by label
            for ex in examples:
                label = (ex.get("label") or "").lower()
                if not label:
                    continue
                best_ep = None
                best_score = 0
                for ep in endpoints:
                    summary = (ep.get("summary") or "").lower()
                    path = (ep.get("path") or "").lower()
                    score = sum(1 for word in label.split() if word in summary or word in path)
                    if score > best_score:
                        best_score = score
                        best_ep = ep
                if best_ep and best_score > 0:
                    kind = ex.get("kind")
                    if kind == "request":
                        best_ep.setdefault("request_body", {
                            "content_type": "application/json",
                            "schema": {}, "required": False, "description": ""
                        })["example"] = ex["data"]
                    elif kind == "response":
                        best_ep.setdefault("responses", {}).setdefault(
                            "200", {"description": "OK", "schema": None}
                        )["example"] = ex["data"]

        return endpoints

    def extract_from_text(self, text: str) -> list[Any]:
        results = []
        for m in _BARE_JSON_RE.finditer(text):
            parsed = self._try_json(m.group(1))
            if parsed is not None:
                results.append(parsed)
        return results

    # ── private ───────────────────────────────────────────────────────────

    def _try_json(self, text: str) -> Any:
        text = text.strip()
        if not text or text[0] not in ("{", "["):
            return None
        try:
            return json.loads(text)
        except Exception:
            cleaned = re.sub(r",\s*([\}\]])", r"\1", text)
            try:
                return json.loads(cleaned)
            except Exception:
                return None

    def _label_from_context(self, tag: Tag) -> str | None:
        # Nearest preceding heading or paragraph
        for el_name in ("h1", "h2", "h3", "h4", "h5", "p"):
            prev = tag.find_previous(el_name)
            if prev:
                text = prev.get_text(strip=True)
                if text and len(text) < 200:
                    return text
        return None

    def _classify(self, label: str | None, tag: Tag) -> str | None:
        """Classify example as 'request', 'response', or None."""
        # Check label text
        if label:
            if _RESPONSE_HINTS.search(label):
                return "response"
            if _REQUEST_HINTS.search(label):
                return "request"

        # Check surrounding element text (tab label, caption, etc.)
        for ancestor in tag.parents:
            if ancestor is None:
                break
            cls = " ".join(ancestor.get("class", []))
            text = ancestor.get_text(" ", strip=True)[:200]
            if _RESPONSE_HINTS.search(cls) or _RESPONSE_HINTS.search(text):
                return "response"
            if _REQUEST_HINTS.search(cls) or _REQUEST_HINTS.search(text):
                return "request"
            if ancestor.name in ("section", "article", "main"):
                break

        return None
