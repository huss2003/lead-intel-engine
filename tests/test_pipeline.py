import csv
import json

import httpx
from fastapi.testclient import TestClient
from sqlmodel import select
from typer.testing import CliRunner

from lie import pipeline
from lie.api import create_app
from lie.cli import app
from lie.config import Settings
from lie.db import Lead
from lie.discover.csv_source import CsvSource
from lie.discover.places import PlacesSource
from lie.export import export
from lie.models import Query
from lie.opener import AnthropicOpener, MockOpener

DEMO = Settings(demo_mode=True, db_path=":memory:")


async def test_full_demo_run_dedupes_enriches_and_scores(db):
    stats = await pipeline.run(
        db, DEMO, "fixture", Query(niche="hvac", city="Dallas"), MockOpener()
    )
    assert stats == {"discovered": 4, "enriched": 3, "scored": 4}  # dup merged, no-site skipped
    leads = {r.biz.name: r for r in db.exec(select(Lead)).all()}
    assert len(leads) == 4
    cool, lone = leads["Dallas Cool HVAC"], leads["Lone Star Air & Heat"]
    assert cool.score > lone.score
    assert cool.enr.emails == ["service@dallas-cool-hvac.test"]
    assert cool.opener and "Dallas Cool HVAC" in cool.opener
    no_site = leads["Pop-up AC Repair"]
    assert no_site.enrichment is None and no_site.score == 0


async def test_csv_source(tmp_path):
    p = tmp_path / "in.csv"
    p.write_text(
        "Business,URL,Phone,Stars,Review_Count\nAcme,acme.test,214-555-0100,4.5,80\n,x,,,\n"
    )
    out = await CsvSource().discover(Query(path=str(p), niche="hvac"))
    assert (
        len(out) == 1 and out[0].rating == 4.5 and out[0].reviews == 80 and out[0].niche == "hvac"
    )


async def test_places_source_parses_response():
    def h(req):
        assert req.headers["X-Goog-Api-Key"] == "k"
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "displayName": {"text": "P1"},
                        "websiteUri": "https://p1.test",
                        "nationalPhoneNumber": "(214) 555-0101",
                        "rating": 4.4,
                        "userRatingCount": 33,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(h))
    out = await PlacesSource("k", client).discover(Query(niche="hvac", city="Dallas"))
    assert out[0].name == "P1" and out[0].reviews == 33


async def test_places_requires_key():
    import pytest

    with pytest.raises(RuntimeError):
        await PlacesSource(None).discover(Query())


async def test_anthropic_opener_calls_api():
    def h(req):
        assert req.headers["x-api-key"] == "sk"
        return httpx.Response(200, json={"content": [{"text": " Hello there. "}]})

    from lie.models import Business, Score

    o = AnthropicOpener("sk", "m", httpx.AsyncClient(transport=httpx.MockTransport(h)))
    assert (
        await o.generate(Business(name="A"), None, Score(score=1, reasons=["r"])) == "Hello there."
    )


async def test_export_csv_and_json(db, tmp_path):
    await pipeline.run(db, DEMO, "fixture", Query(niche="hvac"), MockOpener())
    assert export(db, tmp_path / "o.csv", "csv", min_score=50) >= 1
    rows = list(csv.DictReader((tmp_path / "o.csv").open()))
    assert all(int(r["score"]) >= 50 for r in rows) and rows[0]["reasons"]
    export(db, tmp_path / "o.json", "json")
    assert json.loads((tmp_path / "o.json").read_text())[0]["score"] >= 0


def test_cli_run(tmp_path):
    out = tmp_path / "l.csv"
    r = CliRunner().invoke(
        app,
        [
            "run",
            "--niche",
            "hvac",
            "--city",
            "Dallas",
            "--source",
            "fixture",
            "--demo",
            "--db",
            str(tmp_path / "t.db"),
            "-o",
            str(out),
        ],
    )
    assert r.exit_code == 0, r.output
    assert out.exists() and "Dallas Cool HVAC" in out.read_text()


def test_api_runs_and_leads():
    c = TestClient(create_app(DEMO))
    assert c.post("/runs", json={"niche": "hvac", "city": "Dallas"}).json()["scored"] == 4
    hi = c.get("/leads", params={"min_score": 60}).json()
    assert hi and all(d["score"] >= 60 for d in hi)
    assert c.post("/runs", json={"niche": "x", "city": "y", "source": "csv"}).status_code == 422
