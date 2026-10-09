"""Server forward observation ledger: idempotent, append-only, attested only before next open, explicit gaps."""
import importlib.util, json, sys
from datetime import date, datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("foe", ROOT / "scripts" / "forward_observation_engine.py")
foe = importlib.util.module_from_spec(spec); spec.loader.exec_module(foe)

def data(session="2026-10-08", ixic=-0.0125, vix=15.4):
    tp = {"QQQ": {"available": True, "date": session, "state": "趋势延续", "score": 60},
          "LITE": {"available": True, "date": session, "state": "二次启动", "score": 80},
          "SOFI": {"available": True, "date": session, "state": "趋势恶化", "score": -88},
          "OLD": {"available": True, "date": "2026-10-01", "state": "修复中", "score": 10}}
    px = {k: {"date": session, "close": 100.0} for k in ("QQQ", "LITE", "SOFI")}
    return {"trend_pulse": tp, "stocks": px, "index": {},
            "market_indicators": {"spx": {"day_chg": -0.004}, "ixic": {"day_chg": ixic}, "vix": {"day_chg": 0.02, "close": vix}}}

before_open = datetime(2026, 10, 9, 4, 0, tzinfo=timezone.utc)     # 00:00 ET 10/09
after_open = datetime(2026, 10, 9, 14, 0, tzinfo=timezone.utc)      # 10:00 ET 10/09
rows, why = foe.build_observations(data(), before_open)
assert why == "ok" and {r["symbol"] for r in rows} == {"QQQ", "LITE", "SOFI"}, (why, rows)  # stale symbol skipped
assert all(r["attested_forward"] for r in rows)
lite = next(r for r in rows if r["symbol"] == "LITE")
assert lite["payload"]["decision"] == "修复候选" and lite["payload"]["eligible"] is True
assert next(r for r in rows if r["symbol"] == "SOFI")["payload"]["decision"] == "等待修复"
assert lite["matures"] == {"20": "2026-11-05", "60": "2027-01-05", "120": "2027-04-02"}  # NYSE sessions
assert lite["rule_hash"] == foe.RULE_HASH and lite["market_as_of"] == "2026-10-08"
# deterministic id → idempotent
rows2, _ = foe.build_observations(data(), before_open)
assert [r["event_id"] for r in rows] == [r["event_id"] for r in rows2]
# captured after the next session opened → never attested
late, _ = foe.build_observations(data(), after_open)
assert not any(r["attested_forward"] for r in late)
# session not completed yet (10/09 at 15:00 ET) → nothing recorded
none, why = foe.build_observations(data("2026-10-09"), datetime(2026, 10, 9, 19, 0, tzinfo=timezone.utc))
assert none == [] and why == "session_not_completed"
# fear mode changes eligibility and decision
fear, _ = foe.build_observations(data(ixic=-0.03), before_open)
q = next(r for r in fear if r["symbol"] == "QQQ")
assert q["market"]["mode"] == "fear" and q["payload"]["decision"] == "大跌机会候选" and q["payload"]["eligible"]
# append-only check
a = ['{"a":1}', '{"b":2}']
assert foe.check_append_only(a, a + ['{"c":3}'])[0]
assert foe.check_append_only(a, a[:1])[1] == "ledger_shrank"
assert foe.check_append_only(a, ['{"a":9}', '{"b":2}', '{"c":3}'])[1] == "prior_line_changed"
# outcomes come from the ledger's own later closes, with QQQ excess
r0 = {"event_id": "e1", "session": "2026-10-08", "symbol": "LITE", "payload": {"close": 100.0}, "attested_forward": True,
      "matures": {"20": "2026-11-05", "60": "2027-01-05", "120": "2027-04-02"}}
b0 = {**r0, "event_id": "b0", "symbol": "QQQ", "payload": {"close": 200.0}}
r20 = {**r0, "event_id": "e2", "session": "2026-11-05", "payload": {"close": 110.0}, "matures": {"20": "x", "60": "x", "120": "x"}}
b20 = {**r20, "event_id": "b2", "symbol": "QQQ", "payload": {"close": 204.0}}
oc = [o for o in foe.outcomes([r0, b0, r20, b20]) if o["event_id"] == "e1"]
assert len(oc) == 1 and oc[0]["h"] == 20 and abs(oc[0]["ret"] - 0.10) < 1e-9 and abs(oc[0]["excess_vs_qqq"] - 0.08) < 1e-9
# public fields only
txt = json.dumps(rows, ensure_ascii=False)
for k in ("user_id", "hasThesis", "position", "account", "strike"):
    assert k not in txt
print("PASS forward observation engine")
