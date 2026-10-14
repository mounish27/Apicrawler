from __future__ import annotations

from typing import Any


class DOMSnapshot:
    """
    Captures and stores a lightweight DOM snapshot from a Playwright page.
    Useful for detecting dynamic UI elements after JS renders.
    """

    def __init__(self) -> None:
        self.url: str = ""
        self.title: str = ""
        self.html: str = ""
        self.links: list[str] = []
        self.json_objects: list[dict] = []

    @classmethod
    async def capture(cls, page) -> "DOMSnapshot":
        snap = cls()
        snap.url = page.url
        try:
            snap.title = await page.title()
        except Exception:
            snap.title = ""
        try:
            snap.html = await page.content()
        except Exception:
            snap.html = ""

        # Collect all hrefs
        try:
            snap.links = await page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href)"
            )
        except Exception:
            snap.links = []

        # Extract any JSON data attributes or embedded JS objects
        try:
            snap.json_objects = await page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('[data-spec],[data-swagger],[data-openapi]').forEach(el => {
                    try { results.push(JSON.parse(el.textContent || el.getAttribute('data-spec') || '{}')); }
                    catch(e) {}
                });
                return results;
            }""")
        except Exception:
            snap.json_objects = []

        return snap

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "html_length": len(self.html),
            "links_count": len(self.links),
        }
