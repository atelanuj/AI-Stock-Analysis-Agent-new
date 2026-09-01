from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")


def test_v7_has_clickable_1d_technical_horizon_and_decision_panel():
    assert "order=['1D','1W','1M','3M','6M','1Y','3Y','5Y']" in JS
    assert 'id="tech-decision-action"' in HTML
    assert 'id="tech-target"' in HTML
    assert 'id="tech-stop"' in HTML
    assert "loadTechnicalDecision" in JS


def test_screener_rows_open_full_detail_tabs():
    assert "clickable-row" in JS
    assert "activateTab('stocks')" in JS
    assert "activateTab('mutual-funds')" in JS


def test_fund_dashboard_has_deep_profile_and_benchmark_sections():
    for marker in [
        'id="mf-return-timeframes"',
        'id="mf-benchmark-chart"',
        'id="mf-risk-band"',
        'id="mf-fund-cagr"',
        'id="mf-correlation"',
        'id="mf-rolling-range"',
    ]:
        assert marker in HTML
