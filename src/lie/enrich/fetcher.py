from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from importlib import resources
from typing import Protocol
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}


class Fetcher(Protocol):
    async def fetch(self, url: str) -> str | None:
        """Return page HTML, or None if disallowed/unreachable."""

    async def aclose(self) -> None: ...


class HttpFetcher:
    """Polite fetcher: robots.txt, per-domain delay, global concurrency cap, retry+backoff."""

    def __init__(
        self,
        user_agent: str,
        timeout: float = 10.0,
        retries: int = 3,
        concurrency: int = 5,
        domain_delay: float = 2.0,
        backoff: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.ua, self.retries, self.delay, self.backoff = user_agent, retries, domain_delay, backoff
        self.sem = asyncio.Semaphore(concurrency)
        self.sleep = sleep
        self.client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._robots: dict[str, RobotFileParser | None] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}

    async def aclose(self) -> None:
        await self.client.aclose()

    async def allowed(self, url: str) -> bool:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            self._robots[origin] = await self._load_robots(origin)
        rp = self._robots[origin]
        return rp is None or rp.can_fetch(self.ua, url)

    async def _load_robots(self, origin: str) -> RobotFileParser | None:
        """None means no robots.txt (everything allowed). 401/403 means deny all."""
        try:
            r = await self.client.get(f"{origin}/robots.txt")
        except httpx.HTTPError:
            return None
        rp = RobotFileParser()
        if r.status_code in (401, 403):
            rp.disallow_all = True
        elif r.status_code == 200:
            rp.parse(r.text.splitlines())
        else:
            return None
        return rp

    async def _throttle(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._last.get(host, 0) + self.delay - time.monotonic()
            if wait > 0:
                await self.sleep(wait)
            self._last[host] = time.monotonic()

    async def _get_html(self, url: str) -> httpx.Response:
        return await self.client.get(url)

    async def fetch(self, url: str) -> str | None:
        if not await self.allowed(url):
            return None
        host = urlparse(url).netloc
        async with self.sem:
            for attempt in range(self.retries + 1):
                await self._throttle(host)
                try:
                    r = await self._get_html(url)
                    if r.status_code in RETRY_STATUS and attempt < self.retries:
                        raise httpx.HTTPStatusError("retry", request=r.request, response=r)
                    if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
                        return None
                    return r.text
                except httpx.HTTPError:
                    if attempt == self.retries:
                        return None
                    await self.sleep(self.backoff * 2**attempt)
        return None


class Crawl4AIFetcher(HttpFetcher):
    """Renders JS pages via crawl4ai (optional extra). Shares robots/rate-limit logic."""

    async def _get_html(self, url: str) -> httpx.Response:
        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError as e:
            raise RuntimeError("pip install 'lead-intel-engine[crawl4ai]'") from e
        async with AsyncWebCrawler() as crawler:
            res = await crawler.arun(url=url)
        status = res.status_code or (200 if res.success else 502)
        return httpx.Response(
            status,
            text=res.html or "",
            headers={"content-type": "text/html"},
            request=httpx.Request("GET", url),
        )


class FixtureFetcher:
    """Serves recorded HTML packaged in lie.data.sites; no network. Keyed by domain."""

    async def fetch(self, url: str) -> str | None:
        p = urlparse(url)
        slug = (p.hostname or "").removeprefix("www.")
        page = "contact" if "contact" in p.path else "index"
        f = resources.files("lie.data").joinpath("sites", f"{slug}__{page}.html")
        return f.read_text("utf-8") if f.is_file() else None

    async def aclose(self) -> None:  # pragma: no cover
        return None
