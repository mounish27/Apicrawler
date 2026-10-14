from __future__ import annotations

import asyncio
import re
import time
from typing import Callable
from urllib.parse import urlparse

import httpx

from .browser_manager import BrowserManager
from .link_extractor import LinkExtractor
from .network_interceptor import NetworkInterceptor
from parsers.doc_detector import DocDetector, DocType


class PageResult:
    __slots__ = ("url", "html", "json_data", "status", "intercepted_specs", "error")

    def __init__(self, url: str, html: str = "", json_data: dict | None = None,
                 status: int = 200, intercepted_specs: list | None = None, error: str = ""):
        self.url = url
        self.html = html
        self.json_data = json_data
        self.status = status
        self.intercepted_specs = intercepted_specs or []
        self.error = error


# Safety ceiling for auto mode
_AUTO_MAX_PAGES = 2000
_AUTO_TIMEOUT_SECONDS = 1800  # 30 minutes

# Minimum HTML that counts as a "real" page (not a login wall / empty shell)
_STATIC_MIN_LENGTH = 500
_STATIC_MIN_LINKS = 3
_LINK_RE = re.compile(r'<a\s+[^>]*href=', re.IGNORECASE)


class RecursiveCrawler:
    """
    BFS crawler with parallel worker pool.

    Optimizations vs the old sequential crawler:
      1. Up to `concurrency` pages fetched simultaneously.
      2. Static (httpx) fetch attempted before Playwright — skips browser for
         plain-HTML pages, which is ~10-20x faster.
      3. wait_until="domcontentloaded" instead of "networkidle" — fires as soon
         as the DOM is parsed, not after all trackers/fonts load.
    """

    def __init__(
        self,
        max_depth: int | None = None,
        max_pages: int | None = None,
        auto: bool = False,
        concurrency: int = 10,
        requests_per_second: float = 4.0,
        on_page: Callable[[PageResult], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self._auto = auto
        if auto:
            self._max_depth = _AUTO_MAX_PAGES
            self._max_pages = _AUTO_MAX_PAGES
        else:
            self._max_depth = max_depth if max_depth is not None else 3
            self._max_pages = max_pages if max_pages is not None else 100

        self._concurrency = max(1, concurrency)
        self._min_delay = 1.0 / requests_per_second  # per-worker minimum gap
        self._on_page = on_page or (lambda _: None)
        self._on_status = on_status or (lambda _: None)
        self._detector = DocDetector()
        self._link_extractor = LinkExtractor()
        self._visited: set[str] = set()
        self._queued: set[str] = set()
        self._pages_visited = 0
        self._start_time: float = 0.0
        self._path_prefix: str | None = None

    # ── public ────────────────────────────────────────────────────────────

    async def crawl(self, start_url: str) -> list[PageResult]:
        self._visited.clear()
        self._queued.clear()
        self._pages_visited = 0
        self._start_time = time.monotonic()
        results: list[PageResult] = []

        # Derive path prefix to scope crawl within the starting section
        parsed_start = urlparse(start_url)
        path = parsed_start.path.rstrip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            self._path_prefix = "/" + "/".join(parts[:2]) + "/"
        elif len(parts) == 1:
            self._path_prefix = "/" + parts[0] + "/"
        else:
            self._path_prefix = None

        # Step 1: probe common spec URLs (fast, no browser)
        self._on_status("Probing for OpenAPI/Swagger spec...")
        spec_result = await self._probe_spec_urls(start_url)
        if spec_result:
            results.append(spec_result)
            self._on_status(f"Spec found at {spec_result.url}")
            return results

        if self._path_prefix:
            self._on_status(f"Scoping crawl to path prefix: {self._path_prefix}")

        # Step 2: check entry page statically
        self._on_status("Fetching entry page...")
        entry = await self._fetch_static(start_url)
        if entry.json_data:
            det = self._detector.from_json(entry.json_data, start_url)
            if det.spec_data:
                entry.intercepted_specs = [{"url": start_url, "data": det.spec_data}]
                results.append(entry)
                return results

        if entry.html:
            det = self._detector.from_html(entry.html, start_url)
            if det.doc_type in (DocType.SWAGGER_UI, DocType.REDOC, DocType.STOPLIGHT):
                candidates = []
                if det.spec_url:
                    candidates.append(det.spec_url)
                candidates.extend(det.extra_spec_urls)
                spec = await self._probe_urls(candidates)
                if spec:
                    results.append(spec)
                    return results

        # Step 3: parallel BFS crawl
        mode = "auto" if self._auto else f"max_depth={self._max_depth}, max_pages={self._max_pages}"
        self._on_status(
            f"Starting crawl [{mode}, concurrency={self._concurrency}]..."
        )
        playwright_results = await self._parallel_crawl(start_url)
        results.extend(playwright_results)
        return results

    @property
    def pages_visited(self) -> int:
        return self._pages_visited

    # ── spec probing ──────────────────────────────────────────────────────

    async def _probe_spec_urls(self, page_url: str) -> PageResult | None:
        candidates = self._detector.candidate_spec_urls(page_url)
        return await self._probe_urls(candidates)

    async def _probe_urls(self, urls: list[str]) -> PageResult | None:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
            for url in urls:
                try:
                    r = await client.get(url, headers={"Accept": "application/json"})
                    if r.status_code == 200:
                        try:
                            data = r.json()
                            det = self._detector.from_json(data, url)
                            if det.spec_data:
                                pr = PageResult(url=url, json_data=data, status=200)
                                pr.intercepted_specs = [{"url": url, "data": data}]
                                return pr
                        except Exception:
                            pass
                except Exception:
                    pass
        return None

    # ── static fetch ──────────────────────────────────────────────────────

    async def _fetch_static(self, url: str) -> PageResult:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
                r = await client.get(url, headers={
                    "Accept": "text/html,application/json,*/*",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                })
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        return PageResult(url=url, json_data=r.json(), status=r.status_code)
                    except Exception:
                        pass
                return PageResult(url=url, html=r.text, status=r.status_code)
        except Exception as e:
            return PageResult(url=url, error=str(e), status=0)

    def _is_sufficient_static(self, html: str, path_prefix: str | None = None) -> bool:
        """
        True when static HTML has real navigable content — not a JS/SPA loading shell.
        If path_prefix is given, requires at least 2 links within that prefix.
        This prevents treating SPA shells (which have CDN/nav links but no doc links)
        as sufficient.
        """
        if not html or len(html) < _STATIC_MIN_LENGTH:
            return False
        if len(_LINK_RE.findall(html)) < _STATIC_MIN_LINKS:
            return False
        if path_prefix:
            # Require actual in-section links — not just CDN/nav/login links
            escaped = re.escape(path_prefix)
            prefix_link_re = re.compile(
                rf'href=["\'][^"\']*{escaped}', re.IGNORECASE
            )
            return len(prefix_link_re.findall(html)) >= 2
        return True

    # ── parallel BFS ──────────────────────────────────────────────────────

    async def _parallel_crawl(self, start_url: str) -> list[PageResult]:
        results: list[PageResult] = []
        lock = asyncio.Lock()
        sem = asyncio.Semaphore(self._concurrency)
        stop_event = asyncio.Event()

        # Shared queue — workers both consume and produce
        url_queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        clean_start = start_url.split("#")[0].rstrip("/") or start_url
        url_queue.put_nowait((start_url, 0))
        self._queued.add(clean_start)
        active_workers = [0]  # mutable counter tracked under lock

        async with BrowserManager() as browser:

            async def worker() -> None:
                while not stop_event.is_set():
                    # Check timeout
                    if self._auto and (time.monotonic() - self._start_time) > _AUTO_TIMEOUT_SECONDS:
                        elapsed = int(time.monotonic() - self._start_time)
                        self._on_status(f"Timeout after {elapsed}s. Stopping.")
                        stop_event.set()
                        break

                    try:
                        url, depth = url_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    clean = url.split("#")[0].rstrip("/") or url

                    async with lock:
                        if clean in self._visited:
                            url_queue.task_done()
                            continue
                        if self._pages_visited >= self._max_pages:
                            self._on_status(
                                f"Page limit reached ({self._max_pages}). Stopping."
                            )
                            stop_event.set()
                            url_queue.task_done()
                            break
                        self._visited.add(clean)
                        page_num = self._pages_visited + 1
                        self._pages_visited += 1
                        queue_size = url_queue.qsize()

                    self._on_status(
                        f"Crawling ({page_num}) {url[:70]}..."
                        + (f" [{queue_size} in queue]" if self._auto else "")
                    )

                    # Optimization 3: try static first, fall back to Playwright
                    async with sem:
                        pr = await self._fetch_static(url)
                        if not self._is_sufficient_static(pr.html, self._path_prefix):
                            pr = await self._render_page(browser, url)

                    async with lock:
                        results.append(pr)
                        self._on_page(pr)

                        # Spec intercepted — stop entire crawl
                        if pr.intercepted_specs:
                            self._on_status("OpenAPI spec intercepted - stopping crawl.")
                            stop_event.set()
                            url_queue.task_done()
                            return

                        # Enqueue child links
                        should_enqueue = self._auto or (depth < self._max_depth)
                        if should_enqueue and pr.html:
                            links = self._link_extractor.extract(
                                pr.html, url, self._path_prefix
                            )
                            added = 0
                            for link in links:
                                lclean = link.split("#")[0].rstrip("/") or link
                                if lclean not in self._queued and lclean not in self._visited:
                                    self._queued.add(lclean)
                                    url_queue.put_nowait((link, depth + 1))
                                    added += 1
                            if self._auto and added:
                                self._on_status(
                                    f"  +{added} new links (queue: {url_queue.qsize()})"
                                )

                    url_queue.task_done()

            # Keep launching worker batches until queue is drained or stopped
            while not stop_event.is_set():
                pending = url_queue.qsize()
                if pending == 0:
                    # Wait briefly for in-flight workers to enqueue more links
                    try:
                        await asyncio.wait_for(url_queue.join(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                    if url_queue.qsize() == 0:
                        break

                batch = min(url_queue.qsize(), self._concurrency)
                if batch == 0:
                    break
                await asyncio.gather(*[worker() for _ in range(batch)])

        elapsed = int(time.monotonic() - self._start_time)
        self._on_status(
            f"Crawl complete. {self._pages_visited} pages in {elapsed}s."
        )
        return results

    async def _render_page(self, browser: BrowserManager, url: str) -> PageResult:
        """Render a page with Playwright. Uses domcontentloaded (fast) not networkidle."""
        interceptor = NetworkInterceptor()
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            interceptor.attach(page)
            # networkidle ensures async sidebar/TOC data is loaded before we read links
            await page.goto(url, timeout=30_000, wait_until="networkidle")
            html = await page.content()
            await ctx.close()
            return PageResult(
                url=url,
                html=html,
                status=200,
                intercepted_specs=interceptor.get_specs(),
            )
        except Exception as e:
            return PageResult(url=url, error=str(e), status=0)
