import httpx
from conftest import FIX

from lie.enrich.fetcher import HttpFetcher

ROBOTS = (FIX / "robots_blocking.txt").read_text()


def make(handler, **kw) -> tuple[HttpFetcher, list[float]]:
    sleeps: list[float] = []

    async def fake_sleep(t):
        sleeps.append(t)

    f = HttpFetcher("TestBot/1.0", transport=httpx.MockTransport(handler), sleep=fake_sleep, **kw)
    return f, sleeps


def ok(text="<html>hi</html>"):
    return httpx.Response(200, text=text, headers={"content-type": "text/html"})


async def test_robots_disallow_blocks_fetch_without_requesting_page():
    seen = []

    def h(req):
        seen.append(req.url.path)
        return httpx.Response(200, text=ROBOTS) if req.url.path == "/robots.txt" else ok()

    f, _ = make(h, domain_delay=0)
    assert await f.fetch("https://a.test/contact") is None
    assert await f.fetch("https://a.test/private/x") is None
    assert await f.fetch("https://a.test/") == "<html>hi</html>"
    assert "/contact" not in seen and "/private/x" not in seen
    assert seen.count("/robots.txt") == 1  # cached per origin


async def test_robots_403_means_deny_all_and_404_means_allow():
    f, _ = make(lambda r: httpx.Response(403) if r.url.path == "/robots.txt" else ok())
    assert await f.fetch("https://a.test/") is None
    g, _ = make(
        lambda r: httpx.Response(404) if r.url.path == "/robots.txt" else ok(), domain_delay=0
    )
    assert await g.fetch("https://a.test/") is not None


async def test_retries_with_exponential_backoff_then_succeeds():
    calls = {"n": 0}

    def h(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else ok()

    f, sleeps = make(h, domain_delay=0, backoff=1.0)
    assert await f.fetch("https://a.test/") is not None
    assert calls["n"] == 3
    assert [s for s in sleeps if s >= 1] == [1.0, 2.0]


async def test_gives_up_after_retries():
    def h(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectTimeout("slow")

    f, _ = make(h, retries=2, domain_delay=0)
    assert await f.fetch("https://a.test/") is None


async def test_per_domain_delay_applied():
    f, sleeps = make(
        lambda r: httpx.Response(404) if r.url.path == "/robots.txt" else ok(), domain_delay=5
    )
    await f.fetch("https://a.test/1")
    await f.fetch("https://a.test/2")
    assert any(0 < s <= 5 for s in sleeps)


async def test_non_html_ignored():
    def h(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})

    f, _ = make(h, domain_delay=0)
    assert await f.fetch("https://a.test/x.pdf") is None
