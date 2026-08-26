from app.models.api import StockScreenRequest, FundScreenRequest

def test_stock_screener_allows_50_results():
    r=StockScreenRequest(scan_count=50,result_count=50)
    assert r.scan_count == 50 and r.result_count == 50

def test_stock_screener_allows_500_scan():
    r=StockScreenRequest(scan_count=500,result_count=100)
    assert r.scan_count == 500

def test_fund_screener_separates_scan_and_result_counts():
    r=FundScreenRequest(scan_count=100,result_count=50)
    assert r.scan_count == 100 and r.result_count == 50


def test_stock_screener_supports_1d_horizon():
    r=StockScreenRequest(trend_horizon="1D")
    assert r.trend_horizon == "1D"
