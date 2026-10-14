from __future__ import annotations

import asyncio
from typing import Any


class BrowserManager:
    """Manages a single shared Playwright Chromium browser per crawl session."""

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._playwright = None
        self._pw_cm = None
        self._browser = None

    async def start(self) -> None:
        from playwright.async_api import async_playwright
        self._pw_cm = async_playwright()
        self._playwright = await self._pw_cm.__aenter__()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)

    async def stop(self) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._pw_cm:
            try:
                await self._pw_cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._browser = None
        self._playwright = None
        self._pw_cm = None

    async def new_context(self, headers: dict | None = None):
        return await self._browser.new_context(
            extra_http_headers=headers or {},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()
