from app.models.api import WatchlistRequest
from app.tools.events import get_corporate_events
from app.tools.technical import get_technical


def check_watchlist(request: WatchlistRequest) -> dict:
    results, errors = [], []
    for item in request.items:
        try:
            tech = get_technical(item.symbol.upper(), item.market, include_pattern_backtest=False)
            alerts = []
            rsi = tech.get("rsi14")
            if rsi is not None and rsi <= item.rsi_low:
                alerts.append({"type":"RSI","severity":"MEDIUM","message":f"RSI {rsi:.1f} is at/below {item.rsi_low:.0f}."})
            if rsi is not None and rsi >= item.rsi_high:
                alerts.append({"type":"RSI","severity":"MEDIUM","message":f"RSI {rsi:.1f} is at/above {item.rsi_high:.0f}."})
            breakout = tech.get("breakout", {})
            if breakout.get("status") and breakout.get("status") != "NO ACTIVE BREAKOUT":
                severity = "HIGH" if "CONFIRMED" in breakout["status"] else "MEDIUM"
                alerts.append({"type":"PRICE LEVEL","severity":severity,"message":breakout["status"]})
            events = get_corporate_events(item.symbol, item.market)
            for event in events.get("events", []):
                if event.get("days_until") is not None and 0 <= event["days_until"] <= 7:
                    alerts.append({"type":"EVENT","severity":event.get("impact","MEDIUM"),"message":f"{event['title']} in {event['days_until']} day(s)."})
            one_day = tech.get("timeline_biases",{}).get("1D",{})
            one_month = tech.get("timeline_biases",{}).get("1M",{})
            results.append({"symbol":item.symbol.upper(),"market":item.market,"price":tech.get("price"),"bias":one_day.get("directional_bias"),"signal_agreement_pct":one_day.get("signal_agreement_pct"),"bias_1d":one_day.get("directional_bias"),"signal_1d":one_day.get("signal_agreement_pct"),"bias_1m":one_month.get("directional_bias"),"signal_1m":one_month.get("signal_agreement_pct"),"alerts":alerts})
        except Exception as exc:
            errors.append({"symbol":item.symbol,"error":str(exc)})
    return {"items":results,"errors":errors,"triggered_count":sum(len(x["alerts"]) for x in results)}
