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
    for key, up, down in [("above_sma20", 8, -8), ("above_sma50", 10, -10), ("above_sma200", 15, -15)]:
        if t.get(key) is True: score += up
        elif t.get(key) is False: score += down
    rsi = t.get("rsi14")
    if rsi is not None:
        if 45 <= rsi <= 65: score += 10
        elif rsi >= 75: score -= 10
        elif rsi <= 30: score -= 5
    macd, signal = t.get("macd"), t.get("macd_signal")
    if macd is not None and signal is not None: score += 7 if macd > signal else -7
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
