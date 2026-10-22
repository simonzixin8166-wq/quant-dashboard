"""Frontend docs/assets/trading-calendar.js must list exactly the same NYSE full-day closures as
scripts/trading_calendar.py (the source of truth) for 2026-2028."""
import json, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar

YEARS = range(2026, 2029)
py = sorted(d.isoformat() for y in YEARS for d in trading_calendar.holidays(y))
js_src = (
    "const c=require(process.argv[1]);"
    "const out=[];for(let y=2026;y<=2028;y++)out.push(...c.holidays(y));"
    "process.stdout.write(JSON.stringify(out.sort()));"
)
js = json.loads(subprocess.run(
    ["node", "-e", js_src, str(ROOT / "docs" / "assets" / "trading-calendar.js")],
    check=True, capture_output=True, text=True).stdout)
assert js == py, f"JS/Python holiday mismatch: only_py={sorted(set(py)-set(js))} only_js={sorted(set(js)-set(py))}"
assert "2026-11-26" in py and "2026-12-25" in py
subprocess.run(["node", str(ROOT / "tests" / "trading_calendar_parity.test.js")], check=True)
print(f"PASS trading calendar parity ({len(py)} closures 2026-2028)")
