from app.models.api import WatchlistRequest
from app.tools.events import get_corporate_events
from app.tools.technical import get_technical


def check_watchlist(request: WatchlistRequest) -> dict:
    results, errors = [], []
    for item in request.items:
        try:
            tech = get_technical(item.symbol.upper(), item.market, include_pattern_backtest=False)
            alerts = [];price=tech.get("price")
            rsi = tech.get("rsi14")
            if rsi is not None and rsi <= item.rsi_low:
                alerts.append({"type":"RSI","severity":"MEDIUM","message":f"RSI {rsi:.1f} is at/below {item.rsi_low:.0f}."})
            if rsi is not None and rsi >= item.rsi_high:
                alerts.append({"type":"RSI","severity":"MEDIUM","message":f"RSI {rsi:.1f} is at/above {item.rsi_high:.0f}."})
            if item.price_above is not None and price is not None and price >= item.price_above:
                alerts.append({"type":"PRICE","severity":"HIGH","message":f"Price {price:.2f} is at/above configured level {item.price_above:.2f}."})
            if item.price_below is not None and price is not None and price <= item.price_below:
                alerts.append({"type":"PRICE","severity":"HIGH","message":f"Price {price:.2f} is at/below configured level {item.price_below:.2f}."})
            volume=tech.get("volume",{}) or {};rv=volume.get("relative_volume")
            if item.min_relative_volume is not None and rv is not None and rv>=item.min_relative_volume:
                alerts.append({"type":"VOLUME","severity":"MEDIUM","message":f"Relative volume is elevated at {rv:.2f}× the 20D average."})
            breakout = tech.get("breakout", {})
            if item.watch_breakouts and breakout.get("status") and breakout.get("status") != "NO ACTIVE BREAKOUT":
                severity = "HIGH" if "CONFIRMED" in breakout["status"] else "MEDIUM"
                alerts.append({"type":"PRICE LEVEL","severity":severity,"message":breakout["status"]})
            events = get_corporate_events(item.symbol, item.market)
            for event in events.get("events", []):
                if event.get("days_until") is not None and 0 <= event["days_until"] <= item.event_days:
                    alerts.append({"type":"EVENT","severity":event.get("impact","MEDIUM"),"message":f"{event['title']} in {event['days_until']} day(s)."})
            one_day = tech.get("timeline_biases",{}).get("1D",{});one_month=tech.get("timeline_biases",{}).get("1M",{})
            results.append({"symbol":item.symbol.upper(),"market":item.market,"price":price,"relative_volume":rv,"bias":one_day.get("directional_bias"),"signal_agreement_pct":one_day.get("signal_agreement_pct"),"bias_1d":one_day.get("directional_bias"),"signal_1d":one_day.get("signal_agreement_pct"),"bias_1m":one_month.get("directional_bias"),"signal_1m":one_month.get("signal_agreement_pct"),"alerts":alerts})
        except Exception as exc:
            errors.append({"symbol":item.symbol,"error":str(exc)})
    return {"items":results,"errors":errors,"triggered_count":sum(len(x["alerts"]) for x in results),"note":"V8 smart alerts are evaluated when /watchlist/check runs. Continuous notifications require scheduling this endpoint externally or adding a task runner."}
