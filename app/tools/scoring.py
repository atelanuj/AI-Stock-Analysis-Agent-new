def clamp(value: float) -> float:
    return max(0.0, min(100.0, value))

def fundamental_score(f: dict) -> float:
    score = 50.0
    roe, rev, earn = f.get("return_on_equity"), f.get("revenue_growth"), f.get("earnings_growth")
    debt, margin, fcf = f.get("debt_to_equity"), f.get("profit_margin"), f.get("free_cashflow")
    if roe is not None: score += 15 if roe >= 0.20 else 8 if roe >= 0.12 else -10 if roe < 0.05 else 0
    if rev is not None: score += 12 if rev >= 0.15 else 6 if rev >= 0.07 else -8 if rev < 0 else 0
    if earn is not None: score += 12 if earn >= 0.15 else 6 if earn >= 0.05 else -10 if earn < 0 else 0
    if debt is not None: score += 8 if debt <= 50 else 2 if debt <= 100 else -10 if debt > 200 else -3
    if margin is not None: score += 8 if margin >= 0.15 else 4 if margin >= 0.08 else -6 if margin < 0 else 0
    if fcf is not None: score += 5 if fcf > 0 else -8
    return round(clamp(score), 1)

def technical_score(t: dict) -> float:
    score = 50.0
    for key, up, down in [("above_sma20", 6, -6), ("above_sma50", 8, -8), ("above_sma200", 12, -12)]:
        if t.get(key) is True: score += up
        elif t.get(key) is False: score += down
    rsi = t.get("rsi14")
    if rsi is not None:
        if 45 <= rsi <= 65: score += 8
        elif rsi >= 75: score -= 8
        elif rsi <= 30: score -= 5
    macd, signal = t.get("macd"), t.get("macd_signal")
    if macd is not None and signal is not None: score += 6 if macd > signal else -6
    if t.get("above_vwap20") is True: score += 4
    elif t.get("above_vwap20") is False: score -= 4
    relative_volume = (t.get("volume") or {}).get("relative_volume")
    one_month = (t.get("timeline_biases") or {}).get("1M", {})
    if relative_volume is not None and relative_volume >= 1.3:
        score += 4 if one_month.get("directional_bias") == "BULLISH" else -4 if one_month.get("directional_bias") == "BEARISH" else 0
    regime = (t.get("market_regime") or {}).get("regime")
    if regime == "TRENDING UP": score += 5
    elif regime == "TRENDING DOWN": score -= 5
    rs = ((t.get("relative_strength") or {}).get("horizons") or {}).get("3M", {}).get("relative_strength_pct")
    if rs is not None: score += 5 if rs >= 3 else -5 if rs <= -3 else 0
    return round(clamp(score), 1)

def valuation_score(f: dict) -> float:
    score = 50.0
    pe, pb, evebitda = f.get("trailing_pe"), f.get("price_to_book"), f.get("enterprise_to_ebitda")
    if pe is not None: score += 15 if 0 < pe <= 15 else 8 if pe <= 25 else -8 if pe >= 45 else 0
    if pb is not None: score += 10 if 0 < pb <= 2 else 5 if pb <= 4 else -6 if pb >= 8 else 0
    if evebitda is not None: score += 10 if 0 < evebitda <= 10 else 5 if evebitda <= 15 else -8 if evebitda >= 30 else 0
    return round(clamp(score), 1)

def risk_score(f: dict, market: dict) -> float:
    score = 65.0
    beta, debt, margin = f.get("beta"), f.get("debt_to_equity"), f.get("profit_margin")
    one_year_return = market.get("one_year_return_pct")
    if beta is not None: score += 8 if beta <= 0.8 else -10 if beta >= 1.5 else 0
    if debt is not None: score += 10 if debt <= 50 else -15 if debt >= 200 else 0
    if margin is not None and margin < 0: score -= 15
    if one_year_return is not None and one_year_return <= -30: score -= 10
    return round(clamp(score), 1)

def composite_score(scores: dict) -> float:
    value = scores["fundamental"]*0.35 + scores["technical"]*0.25 + scores["valuation"]*0.20 + scores["risk"]*0.20
    return round(clamp(value), 1)
