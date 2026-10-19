from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable
from importlib import resources
from typing import Protocol
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_REDIRECTS = 5
Resolver = Callable[[str], Awaitable[list[str]]]


async def _resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [i[4][0] for i in infos]


async def is_public_url(url: str, resolve: Resolver = _resolve) -> bool:
    """SSRF guard: http(s) only, and every resolved address must be globally routable."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        addrs = [ipaddress.ip_address(p.hostname)]
    except ValueError:
        try:
            addrs = [ipaddress.ip_address(a.split("%")[0]) for a in await resolve(p.hostname)]
        except (OSError, ValueError):
            return False
    return bool(addrs) and all(a.is_global and not a.is_multicast for a in addrs)


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
        resolve: Resolver = _resolve,
    ):
        self.ua, self.retries, self.delay, self.backoff = user_agent, retries, domain_delay, backoff
        self.sem = asyncio.Semaphore(concurrency)
        self.sleep, self.resolve = sleep, resolve
        self.client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=False,  # followed manually so each hop is SSRF-checked
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

    def _delay(self, url: str) -> float:
        p = urlparse(url)
        rp = self._robots.get(f"{p.scheme}://{p.netloc}")
        cd = rp.crawl_delay(self.ua) if rp else None
        return max(self.delay, float(cd or 0))

    async def _load_robots(self, origin: str) -> RobotFileParser | None:
        """None means no robots.txt (everything allowed). 401/403/5xx means deny all."""
        try:
            r = await self._get(f"{origin}/robots.txt")
        except httpx.HTTPError:
            return None
        if r is None:
            return None
        rp = RobotFileParser()
        if r.status_code in (401, 403) or r.status_code >= 500:
            rp.disallow_all = True
        elif r.status_code == 200:
            rp.parse(r.text.splitlines())
        else:
            return None
        return rp

    async def _throttle(self, host: str, delay: float) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._last.get(host, 0) + delay - time.monotonic()
            if wait > 0:
                await self.sleep(wait)
            self._last[host] = time.monotonic()

    async def _get(self, url: str) -> httpx.Response | None:
        """GET following redirects manually; None if any hop targets a non-public host."""
        for _ in range(MAX_REDIRECTS + 1):
            if not await is_public_url(url, self.resolve):
                return None
            r = await self.client.get(url)
            if not r.is_redirect or "location" not in r.headers:
                return r
            url = str(r.url.join(r.headers["location"]))
        return None

    async def _get_html(self, url: str) -> httpx.Response | None:
        return await self._get(url)

    async def fetch(self, url: str) -> str | None:
        if not await is_public_url(url, self.resolve) or not await self.allowed(url):
            return None
        host = urlparse(url).netloc
        delay = self._delay(url)
        async with self.sem:
            for attempt in range(self.retries + 1):
                await self._throttle(host, delay)
                try:
                    r = await self._get_html(url)
                    if r is None:
                        return None
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

    async def _get_html(self, url: str) -> httpx.Response | None:
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
