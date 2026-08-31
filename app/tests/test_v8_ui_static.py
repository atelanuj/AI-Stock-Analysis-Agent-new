from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")


def test_v8_major_workspaces_and_chat_exist():
    for marker in [
        'data-tab="market"', 'data-tab="intraday"', 'data-tab="ipo"',
        'id="chat-panel"', 'id="strategy-run"', 'id="paper-journal"',
        'id="ownership-table"', 'id="stock-export-btn"',
    ]:
        assert marker in HTML


def test_v8_no_duplicate_dom_ids():
    soup = BeautifulSoup(HTML, "html.parser")
    ids = [node.get("id") for node in soup.find_all(id=True)]
    duplicates = sorted({x for x in ids if ids.count(x) > 1})
    assert duplicates == []


def test_v8_screener_navigation_and_1d_preserved():
    assert "activateTab('stocks')" in JS
    assert "activateTab('mutual-funds')" in JS
    assert "order=['1D','1W','1M','3M','6M','1Y']" in JS
    assert "runIntraday" in JS
    assert "loadIPOList" in JS


def test_v8_redesign_has_readability_components():
    css = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    for marker in ["V8 Research Terminal", ".app-header", ".workspace-banner", ".chat-panel", ".market-index-grid"]:
        assert marker in css


def test_v82_support_resistance_table_is_contained():
    css = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    assert ".two-panel-grid>.glass-panel{min-width:0}" in css
    assert ".support-resistance-layout>*{min-width:0}" in css
    assert ".sr-indicators-wrap{min-width:0;max-width:100%;overflow-x:auto}" in css
    assert ".sr-table{min-width:0;table-layout:fixed}" in css


def test_chart_shows_projected_candle_and_ai_trade_levels():
    assert "next_candle_prediction" in JS
    assert "AI-generated" in JS
    assert "historical_pattern_fallback" in JS
    assert "currentTechnicalDecision" in JS
    assert "AI target" in JS
    assert "AI stop" in JS
    assert 'fillcolor:\'rgba(168,85,247,.78)\'' in JS
    assert '/static/app.js?v=8.2.18' in HTML
    assert '/static/styles.css?v=8.2.21' in HTML
    assert "hoverlabel:hoverStyle" in JS
    assert "hovermode:'x'" in JS
    assert "#candlestick-chart .hoverlayer text" in CSS
    assert "bgcolor:'#581c87'" in JS
    assert "setup.level_source==='ai_selected'" in JS


def test_ai_decision_history_csv_export_is_available():
    assert 'id="recommendation-export"' in HTML
    assert 'id="recommendation-import"' in HTML
    assert 'id="recommendation-import-file"' in HTML
    assert "exportRecommendationHistoryCsv" in JS
    assert "importRecommendationHistoryCsv" in JS
    assert "'/recommendations/import'" in JS
    assert "text/csv;charset=utf-8" in JS
    assert "AI Stop-loss" in JS


def test_watchlist_csv_import_and_export_are_available():
    for marker in ['id="watch-export"', 'id="watch-import"', 'id="watch-import-file"']:
        assert marker in HTML
    assert "exportWatchlistCsv" in JS
    assert "importWatchlistCsv" in JS
    assert "Required columns: Symbol and Market" in JS


def test_active_ai_sections_show_availability_labels():
    for marker in [
        'id="stock-ai-state"', 'id="tech-decision-state"', 'id="final-ai-state"',
        'id="intraday-candle-ai-state"', 'id="intraday-ai-state"',
        'id="ipo-ai-state"', 'id="chat-ai-state"',
    ]:
        assert marker in HTML
    assert "AI unavailable · fallback shown" in JS
    assert "setAiAvailability" in JS
    assert 'id="candle-ai-state"' in HTML
    assert "/api/candles/ai/" in JS
    assert 'id="chart-pattern-insight"' in HTML
    assert "AI future trend" in JS
    assert "selectedPattern" in JS
    assert "dash:'dot'" in JS
    assert ".candle-panel{height:auto!important}" in CSS


def test_intraday_ai_candle_and_trade_levels_are_rendered_safely():
    assert 'id="intraday-chart-meta"' in HTML
    assert "AI-selected" in JS
    assert "Fallback" in JS
    assert "ai_next_candle_prediction" in JS
    assert "ai_level_source" in JS
    assert ".intraday-chart-card #intraday-chart{height:440px;min-height:440px}" in CSS
    assert ".intraday-chart-card{min-width:0;height:auto;overflow:hidden}" in CSS
    assert 'id="intraday-pattern-insight"' in HTML
    assert 'id="toggle-intraday-pattern"' in HTML
    assert "renderIntradayPatternInsight" in JS
    assert "pattern_selection_source" in JS


def test_every_chart_has_an_accessible_fullscreen_control():
    soup = BeautifulSoup(HTML, "html.parser")
    chart_ids = ["candlestick-chart", "intraday-chart", "mf-nav-chart", "mf-benchmark-chart", "mf-returns-chart"]
    for chart_id in chart_ids:
        chart = soup.find(id=chart_id)
        assert chart is not None
        container = chart.find_parent(class_="chart-container")
        assert container is not None
        button = container.find(attrs={"data-fullscreen-chart": True})
        assert button is not None
        assert button.get("aria-label")
    assert "toggleChartFullscreen" in JS
    assert "chart-is-fullscreen" in JS
    assert ".chart-container.chart-container.chart-fullscreen" in CSS


def test_stock_chart_uses_dense_tradingview_style_candle_intervals():
    for marker in [
        "'1d':{interval:'2m',fallback:'5m'",
        "'5d':{interval:'15m',fallback:'30m'",
        "'1mo':{interval:'60m',fallback:'1d'",
        "'3mo':{interval:'60m',fallback:'1d'",
        "fetchDenseCandles",
        "type:'category'",
    ]:
        assert marker in JS
    for title in [
        'title="1 day with 2-minute candles"',
        'title="1 week with 15-minute candles"',
        'title="1 month with 1-hour candles"',
        'title="3 months with 1-hour candles"',
    ]:
        assert title in HTML


def test_final_ai_decision_is_prominent_and_waits_for_all_stock_evidence():
    for marker in [
        'id="final-ai-banner"', 'id="final-ai-action"', 'id="final-ai-confidence"',
        'id="final-ai-summary"', 'id="final-ai-drivers"', 'id="final-ai-risks"',
    ]:
        assert marker in HTML
    assert "maybeLoadFinalAIDecision" in JS
    assert "'/analyze/final-decision'" in JS
    assert "next_candle_prediction:projection" in JS
    assert "technical_decision:currentTechnicalDecision" in JS
    assert ".final-ai-banner.buy" in CSS
    assert ".final-ai-banner.sell" in CSS
    assert ".final-ai-banner.hold" in CSS
