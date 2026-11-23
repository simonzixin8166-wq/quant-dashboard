"""Drawdown type check (Owner 2026-11-23, back end only): classification from five FRED signals, first run is a
baseline, riskier type alerts at once, calmer type only after two market dates, failed delivery retried, nothing
published or used in decisions."""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import drawdown_regime as dr  # noqa: E402

tmp = Path(tempfile.mkdtemp())
dr.OUT, dr.HISTORY, dr.TIERS = tmp / "s.json", tmp / "h.jsonl", tmp / "tiers.json"
dr.TIERS.write_text(json.dumps({"symbols": {"QQQM": {"drawdown": -0.2006, "zone": "t2", "as_of": "2026-11-20"}}}))


def macro(as_of, hy=3.5, un=4.1, d3=0.0, d20=0.1, nf=-0.48, ry=2.88, ry20=0.1, vix=28.0):
    def s(v, ch=None):
        return {"latest": {"date": as_of, "value": v}, "changes": ch or {}}
    return {"as_of": as_of, "series": {"BAMLH0A0HYM2": s(hy), "UNRATE": s(un, {"3": d3, "20": d20}), "NFCI": s(nf),
                                       "DFII10": s(ry, {"20": ry20}), "VIXCLS": s(vix)}}


C = lambda **k: dr.classify(dr.checks(macro("2026-11-20", **k)))  # noqa: E731
assert C() == "RATES_VALUATION"                                   # 11/20: calm credit/jobs, real yield 2.88
assert C(ry=1.0) == "ORDINARY"
assert C(hy=5.5) == "TURNING" and C(nf=0.1) == "TURNING" and C(d3=0.3) == "TURNING"
assert C(hy=7.2) == "SYSTEMIC" and C(hy=5.5, d3=0.6) == "SYSTEMIC" and C(nf=0.6, d3=0.6) == "SYSTEMIC"
assert C(vix=45) == "RATES_VALUATION"                             # fear alone never sets the type
assert dr.classify(dr.checks({"series": {}})) == "UNKNOWN"
# FRED VIXCLS lags a session: a newer same-day close from market data wins, an older one never does
f = dr.checks(macro("2026-11-19"), {"vix": {"date": "2026-11-20", "close": 37.06}})["fear"]
assert f["value"] == 37.06 and f["series"] == "yahoo_close" and f["level"] == "watch"
assert dr.checks(macro("2026-11-19"), {"vix": {"date": "2026-11-18", "close": 50}})["fear"]["series"] == "VIXCLS"
print("PASS classify: 2022-type now; turning / systemic / ordinary / unknown")

sent = []


def send(t):
    sent.append(t)
    return "sent"


N = datetime(2026, 11, 23, tzinfo=timezone.utc)
r = dr.run(macro("2026-11-20"), N, send)
assert r["type"] == "RATES_VALUATION" and not sent and r["last_alerted_type"] == "RATES_VALUATION"   # baseline only
r = dr.run(macro("2026-11-23"), N, send)
assert not sent                                                   # same type: silent
r = dr.run(macro("2026-11-24", hy=5.6), N, send)                  # riskier: at once
assert len(sent) == 1 and "升级" in sent[0] and "QQQM -20%" in sent[0] and "不是买卖指令" in sent[0]
r = dr.run(macro("2026-11-25"), N, send)                          # calmer, first day: wait
assert len(sent) == 1 and r["last_alerted_type"] == "TURNING"
r = dr.run(macro("2026-11-26"), N, send)                          # calmer, second day: send
assert len(sent) == 2 and "缓和" in sent[1] and r["last_alerted_type"] == "RATES_VALUATION"
r = dr.run({"series": {}, "as_of": "2026-11-27"}, N, send)        # unknown: no flapping
assert len(sent) == 2 and r["last_alerted_type"] == "RATES_VALUATION"
# a failed delivery is retried on the next run
r = dr.run(macro("2026-11-30", hy=7.5), N, lambda t: "failed:URLError")
assert r["last_alerted_type"] == "RATES_VALUATION"
r = dr.run(macro("2026-12-01", hy=7.5), N, send)
assert len(sent) == 3 and r["last_alerted_type"] == "SYSTEMIC"
hist = [json.loads(x) for x in dr.HISTORY.read_text().splitlines()]
assert [h["macro_as_of"] for h in hist] == ["2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26",
                                             "2026-11-27", "2026-11-30", "2026-12-01"]
assert r["production_use"] is False and r["published"] is False
assert not str(ROOT / "research" / "regime").startswith(str(ROOT / "docs"))
daily = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
assert "python scripts/drawdown_regime.py" in daily and "git add research/regime/" in daily
print("PASS alerts: baseline, riskier at once, calmer after 2 days, unknown silent, failed retried; back end only")
