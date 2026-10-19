from sqlmodel import select

from lie.db import Lead, upsert_business
from lie.dedupe import dedupe, normalize_domain, normalize_phone
from lie.models import Business


def test_normalizers():
    assert normalize_domain("https://www.Example.com/path?x=1") == "example.com"
    assert normalize_domain("example.com") == "example.com"
    assert normalize_domain(None) is None
    assert normalize_phone("(214) 555-0142") == normalize_phone("+1 214 555 0142") == "+12145550142"
    assert normalize_phone("nope") is None


def test_dedupe_by_domain_then_phone():
    items = [
        Business(name="A", website="https://www.a.test", phone="214-555-0142", reviews=10),
        Business(name="A2", website="a.test", reviews=50, rating=4.5),
        Business(name="A3", phone="+1 214 555 0142", address="1 Main"),
        Business(name="B", website="b.test"),
    ]
    out = dedupe(items)
    assert [b.name for b in out] == ["A", "B"]
    assert out[0].reviews == 50 and out[0].address == "1 Main"


def test_db_upsert_merges(db):
    assert upsert_business(db, Business(name="A", website="https://a.test", phone="214-555-0142"))
    assert not upsert_business(db, Business(name="A", website="www.a.test", address="x"))
    assert not upsert_business(db, Business(name="A", phone="(214) 555 0142", rating=4.0))
    rows = db.exec(select(Lead)).all()
    assert len(rows) == 1
    assert rows[0].biz.address == "x" and rows[0].biz.rating == 4.0
