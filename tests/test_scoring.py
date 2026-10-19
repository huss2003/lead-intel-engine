from lie.models import Business, Enrichment
from lie.score import WEIGHTS, score_lead


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_max_prospect_scores_100():
    b = Business(name="A", rating=4.8, reviews=300)
    e = Enrichment(hours_text="Mon-Fri 8am-5pm", has_ads=True)
    s = score_lead(b, e)
    assert s.score == 100
    assert len(s.reasons) == 6


def test_already_covered_business_scores_low():
    b = Business(name="B", rating=4.8, reviews=300)
    e = Enrichment(has_chat=True, has_booking=True, open_24_7=True)
    assert score_lead(b, e).score == 35  # only rating + reviews


def test_unenriched_lead_scores_on_public_data_only():
    s = score_lead(Business(name="C", rating=4.0, reviews=40), None)
    assert s.score == 10 + 14
    assert any("not enriched" in r for r in s.reasons)


def test_weak_rating_and_no_data():
    assert score_lead(Business(name="D", rating=3.0, reviews=2), None).score == 0
    assert score_lead(Business(name="E"), None).score == 0
