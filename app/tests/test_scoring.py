from app.tools.scoring import composite_score, fundamental_score, technical_score, valuation_score

def test_scores_are_bounded():
    f = {"return_on_equity":0.25,"revenue_growth":0.20,"earnings_growth":0.18,"debt_to_equity":20,"profit_margin":0.20,
         "free_cashflow":100,"trailing_pe":20,"price_to_book":3,"enterprise_to_ebitda":12}
    t = {"above_sma20":True,"above_sma50":True,"above_sma200":True,"rsi14":55,"macd":5,"macd_signal":3}
    fs, ts, vs = fundamental_score(f), technical_score(t), valuation_score(f)
    overall = composite_score({"fundamental":fs,"technical":ts,"valuation":vs,"risk":80})
    assert all(0 <= x <= 100 for x in [fs,ts,vs,overall])
