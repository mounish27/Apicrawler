from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup


_BEARER_RE = re.compile(r"bearer\s+token|authorization:\s*bearer|jwt", re.IGNORECASE)
_OAUTH2_RE = re.compile(r"oauth2?|access_token|refresh_token|client_id|client_secret|token_url|authorize", re.IGNORECASE)
_BASIC_RE = re.compile(r"basic\s+auth|base64.*username|username.*password", re.IGNORECASE)
_APIKEY_RE = re.compile(r"api[_-]?key|x-api-key|apikey", re.IGNORECASE)
_SESSION_RE = re.compile(r"session|cookie|csrf", re.IGNORECASE)

_AUTH_URL_RE = re.compile(r"https?://[^\s\"'>]+(?:oauth|token|authorize|auth)[^\s\"'>]*", re.IGNORECASE)
_SCOPE_RE = re.compile(r"scope[s]?\s*[:=]\s*([^\n\"'<>]+)", re.IGNORECASE)
_TOKEN_HEADER_RE = re.compile(r"(x-[\w-]+|authorization)\s*[:=]\s*[\"']?(\S+)[\"']?", re.IGNORECASE)


class AuthDetector:
    """
    Phase 8 — Detects authentication schemes from HTML pages and spec data.
    Returns auth config + OpenAPI securitySchemes.
    """

    def detect_from_html(self, html: str, page_url: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)
        return self._classify(text, page_url)

    def detect_from_spec(self, spec: dict) -> dict:
        schemes = (
            spec.get("components", {}).get("securitySchemes", {})
            or spec.get("securityDefinitions", {})
        )
        if not schemes:
            return {"auth_type": "none", "security_schemes": {}}

        auth_type = "unknown"
        for name, s in schemes.items():
            t = s.get("type", "").lower()
            scheme = s.get("scheme", "").lower()
            if t == "http" and scheme == "bearer":
                auth_type = "bearer"
                break
            elif t == "oauth2":
                auth_type = "oauth2"
                break
            elif t == "apikey":
                auth_type = "api_key"
                break
            elif t == "http" and scheme == "basic":
                auth_type = "basic"
                break

        return {
            "auth_type": auth_type,
            "security_schemes": schemes,
        }

    def build_security_schemes(self, auth_config: dict) -> dict:
        """Convert detected auth config into OpenAPI 3.x securitySchemes."""
        auth_type = auth_config.get("auth_type", "none")
        # If already have raw schemes from a spec, return them
        if auth_config.get("security_schemes"):
            return auth_config["security_schemes"]

        if auth_type == "bearer":
            return {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                }
            }
        elif auth_type == "oauth2":
            token_url = auth_config.get("token_url", "https://auth.example.com/token")
            scopes = auth_config.get("scopes", {})
            return {
                "oauth2": {
                    "type": "oauth2",
                    "flows": {
                        "clientCredentials": {
                            "tokenUrl": token_url,
                            "scopes": scopes,
                        }
                    },
                }
            }
        elif auth_type == "api_key":
            header_name = auth_config.get("header_name", "X-API-Key")
            return {
                "apiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": header_name,
                }
            }
        elif auth_type == "basic":
            return {
                "basicAuth": {
                    "type": "http",
                    "scheme": "basic",
                }
            }
        return {}

    # ── private ───────────────────────────────────────────────────────────

    def _classify(self, text: str, page_url: str) -> dict:
        auth_type = "none"
        token_url = None
        scopes = {}
        header_name = "Authorization"

        if _OAUTH2_RE.search(text):
            auth_type = "oauth2"
            m = _AUTH_URL_RE.search(text)
            if m:
                token_url = m.group(0)
            scope_m = _SCOPE_RE.findall(text)
            for s in scope_m:
                for scope in re.split(r"[,\s]+", s.strip()):
                    if scope:
                        scopes[scope] = scope
        elif _BEARER_RE.search(text):
            auth_type = "bearer"
        elif _BASIC_RE.search(text):
            auth_type = "basic"
        elif _APIKEY_RE.search(text):
            auth_type = "api_key"
            m = _TOKEN_HEADER_RE.search(text)
            if m:
                header_name = m.group(1)
        elif _SESSION_RE.search(text):
            auth_type = "session"

        result = {"auth_type": auth_type}
        if token_url:
            result["token_url"] = token_url
        if scopes:
            result["scopes"] = scopes
        if auth_type == "api_key":
            result["header_name"] = header_name
        return result
