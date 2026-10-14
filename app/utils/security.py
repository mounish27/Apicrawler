from __future__ import annotations

import re
from urllib.parse import urlparse

from app.config import settings


_PRIVATE_RANGES = re.compile(
    r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|::1|localhost)",
    re.IGNORECASE,
)


def validate_url(url: str) -> str:
    """
    Phase 21 — Validate a crawl URL against SSRF and domain allowlist rules.
    Raises ValueError for blocked URLs.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only HTTP/HTTPS URLs are allowed")

    host = parsed.hostname or ""
    if _PRIVATE_RANGES.match(host):
        raise ValueError(f"Private/local addresses are not allowed: {host}")

    if settings.allowed_domains:
        if not any(host == d or host.endswith("." + d) for d in settings.allowed_domains):
            raise ValueError(f"Domain '{host}' is not in the allowlist")

    return url
