from app.services.ipo_analysis import _score_issue


def test_thin_ipo_evidence_cannot_be_subscribe():
    score = _score_issue({"name":"Example IPO", "subscription_x":100})
    assert score["evidence_completeness_pct"] < 50
    assert score["verdict"] != "SUBSCRIBE"
    assert score["score"] <= 59


def test_richer_strong_demand_can_reach_subscribe():
    issue = {
        "name":"Example IPO", "price_band":"100-110", "open_date":"2026-09-01",
        "issue_size":"500 Cr", "subscription_x":25, "lot_size":100,
    }
    score = _score_issue(issue)
    assert score["evidence_completeness_pct"] >= 65
    assert score["verdict"] in {"SUBSCRIBE", "WATCH"}
