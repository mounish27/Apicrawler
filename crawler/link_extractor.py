from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


# URL segments that are almost never API docs
_SKIP_PATTERNS = re.compile(
    r"/(logout|signin|signup|login|register|blog|pricing|careers|"
    r"status|tos|privacy|cookie|support|community|forum|jobs|about"
    r"|twitter|github|linkedin|facebook|youtube|changelog)(/|$)",
    re.IGNORECASE,
)

# File extensions to skip
_SKIP_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
              ".pdf", ".zip", ".tar", ".gz", ".mp4", ".webm",
              ".woff", ".woff2", ".ttf", ".eot", ".css"}


class LinkExtractor:
    """Extracts and filters links from rendered HTML, staying on the same domain."""

    def extract(self, html: str, base_url: str,
                path_prefix: str | None = None) -> list[str]:
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc
        soup = BeautifulSoup(html, "lxml")
        seen: set[str] = set()
        links: list[str] = []

        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            full = urljoin(base_url, href)
            parsed = urlparse(full)

            # same domain only
            if parsed.netloc != base_domain:
                continue

            # scope to starting path prefix when provided
            if path_prefix and not parsed.path.startswith(path_prefix):
                continue

            # strip fragment
            clean = full.split("#")[0].rstrip("/") or full
            if clean in seen:
                continue

            # skip unwanted extensions
            path = parsed.path.lower()
            if any(path.endswith(ext) for ext in _SKIP_EXTS):
                continue

            # skip social/marketing pages
            if _SKIP_PATTERNS.search(path):
                continue

            seen.add(clean)
            links.append(clean)

        return links
