import datetime
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("fab", ROOT/"scripts/fetch_and_build.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def rows(end_date, n=240, close=100.0):
    out=[]
    d=end_date
    for i in range(n):
        px=close-(n-1-i)*0.05
        out.append({
            "datetime": d.isoformat()+" 16:00:00",
            "open": px-0.2, "high": px+0.5, "low": px-0.5, "close": px, "volume": 1000000,
        })
        d-=datetime.timedelta(days=1)
    return list(reversed(out))

primary=rows(datetime.date(2026,9,29))
# Primary rows expected newest-first in the production fetch path.
primary=list(reversed(primary))

check=mod.validate_trend_input(
    "TEST", primary,
    secondary={"date":"2026-09-28","close":80.0},
    today=datetime.date(2026,9,30),
)
assert check["status"]=="CHECK", check
assert check["price_mismatch_pct"] is None
assert any("落后主源" in x for x in check["issues"])

fail=mod.validate_trend_input(
    "TEST", primary,
    secondary={"date":"2026-09-29","close":80.0},
    today=datetime.date(2026,9,30),
)
assert fail["status"]=="FAIL", fail
assert fail["price_mismatch_pct"] is not None

agent=(ROOT/"docs/assets/autonomous-agent.js").read_text(encoding="utf-8")
assert "currentCloseCostRatio" in agent
assert "当前买回成本约为原始权利金的" in agent
assert "尚未兑现的原始权利金约" in agent
assert "Math.min(1,1-capture)" in agent

css=(ROOT/"docs/assets/options-v2.css").read_text(encoding="utf-8")
assert "grid-template-columns:1fr 1fr" in css
assert "height:54px" in css

print("PASS V5.6 data integrity + Remaining Edge semantics + UI alignment")
