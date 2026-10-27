"""FWD-01 L1/L2 forward outcome ledger: contract-pinned, append-only, deterministic, split- and coverage-aware.
Synthetic ledgers only (never the live ones), no network, no PyYAML, no wall-clock dates."""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward_outcome_ledger as fol
import trading_calendar as tc

contract, digest = fol.load_contract()
assert digest == "3eb0efc58e3eba8b" and contract["contract_id"] == "fsc-1.0"

S0 = date(2026, 1, 5)
SESS = [tc.add_sessions(S0, i).isoformat() for i in range(0, 30)]   # S0 .. S0+29 sessions
M20 = SESS[20]


def obs(sym, i, close, decision="修复候选", eligible=True, mode="normal", eid=None, group_tag="g"):
    s = SESS[i]
    return {"event_id": eid or f"{group_tag}-{sym}-{i}", "symbol": sym, "session": s, "rule_hash": "ff28762ad7a5ed6f",
            "matures": {str(h): tc.add_sessions(date.fromisoformat(s), h).isoformat() for h in (20, 60, 120)},
            "payload": {"close": close, "decision": decision, "eligible": eligible}, "market": {"mode": mode}}


def series(sym, closes, upto, **kw):
    return [obs(sym, i, closes(i), **kw) for i in range(upto + 1)]


def run(genuine, promoted=(), actions=(), existing=(), hold=()):
    return fol.plan(list(genuine), list(promoted), list(actions), list(existing), contract, digest, "T", "sha", hold=set(hold))


def one(add, sym="X", h=20, i=0, group=None):
    xs = [o for o in add if o["symbol"] == sym and o["h"] == h and o["session"] == SESS[i] and (group is None or o["group"] == group)]
    assert len(xs) == 1, xs
    return xs[0]


flat_q = lambda i: 100.0
# 1) normal maturity: X +10%, QQQ +5% -> excess +5%, 修复候选 hit; MAE from daily closes with full coverage
x = lambda i: 100.0 if i < 20 else 110.0
dip = lambda i: 95.0 if i == 7 else x(i)
g = series("X", dip, 20) + series("QQQ", lambda i: 100.0 if i < 20 else 105.0, 20)
add, cur, pend, as_of = run(g)
o = one(add)
assert as_of == M20 and o["status"] == "matured" and o["matures_on"] == M20
assert o["ret"] == 0.1 and o["bench_ret"] == 0.05 and o["excess_vs_qqq"] == 0.05 and o["hit"] is True
assert o["mae"] == -0.05 and o["mae_status"] == "ok" and o["mae_coverage"]["covered"] == 20
assert o["contract_hash"] == digest and o["scorer_version"] == "fol-1.0" and o["supersedes"] is None
assert o["start_ref"] == "g-X-0" and o["end_ref"] == "g-X-20" and o["bench_end_ref"] == "g-QQQ-20"
# later sessions are not matured yet -> pending, never written
assert not [a for a in add if a["session"] != SESS[0]] and pend[("genuine_forward", 20)] > 0
# idempotent: same inputs + existing -> nothing appended
add2, cur2, _, _ = run(g, existing=add)
assert add2 == [] and len(cur2) == len(add)

# 2) decision classes follow fsc-1.0
for dec, exp in (("等待修复", False), ("高位观察", False), ("继续观察", "abstain"), ("新标签", "unscored_unmapped")):
    gg = [obs("X", 0, 100.0, decision=dec)] + series("X", x, 20)[1:] + series("QQQ", lambda i: 100.0 if i < 20 else 105.0, 20)
    assert one(run(gg)[0])["hit"] == exp, dec

# 3) missing maturity close: pending inside the 3-session grace, unavailable after; late price -> supersedes
miss = [r for r in series("X", x, 23) if r["session"] != M20] + series("QQQ", flat_q, 23)
for upto, expect in ((20, None), (21, None), (22, None), (23, "unavailable")):
    gg = [r for r in miss if r["session"] <= SESS[upto]]
    a = [o for o in run(gg)[0] if o["symbol"] == "X" and o["session"] == SESS[0] and o["h"] == 20]
    assert (a[0]["status"] if a else None) == expect, (upto, a)
all_first = run(miss)[0]
first = one(all_first)
assert first["reason"] == "missing_end_close"
late = miss + [obs("X", 20, 110.0, eid="late-X-20")]
add3, cur3, _, _ = run(late, existing=all_first)
o3 = one(add3)
assert o3["status"] == "matured" and o3["supersedes"] == first["outcome_id"] and o3["outcome_id"] != first["outcome_id"]
assert first in all_first and run(late, existing=all_first + add3)[0] == []   # stable; original row kept

# 4) benchmark missing at maturity -> unavailable(missing_benchmark) after grace
nb = series("X", x, 23) + [r for r in series("QQQ", flat_q, 23) if r["session"] != M20]
assert one(run(nb)[0])["reason"] == "missing_benchmark"

# 5) splits: forward 2:1 on S10, reverse 1:10 on S12, two splits, split on start / on maturity date
def act(sym, i, ratio):
    return {"type": "split", "symbol": sym, "ex_date": SESS[i], "ratio": ratio, "action_id": f"{sym}-{i}-{ratio}"}
fwd = series("X", lambda i: 100.0 if i < 10 else 55.0, 20) + series("QQQ", flat_q, 20)
o = one(run(fwd, actions=[act("X", 10, 2.0)])[0])
assert o["split_factor"] == 2.0 and o["ret"] == 0.1 and o["split_refs"] == ["X-10-2.0"] and o["mae"] == 0.0
rev = series("X", lambda i: 10.0 if i < 12 else 90.0, 20) + series("QQQ", flat_q, 20)
o = one(run(rev, actions=[act("X", 12, 0.1)])[0])
assert abs(o["split_factor"] - 0.1) < 1e-12 and o["ret"] == -0.1
two = series("X", lambda i: 100.0 if i < 5 else (50.0 if i < 15 else 26.0), 20) + series("QQQ", flat_q, 20)
o = one(run(two, actions=[act("X", 5, 2.0), act("X", 15, 2.0)])[0])
assert o["split_factor"] == 4.0 and o["ret"] == 0.04
on_start = series("X", lambda i: 50.0 if i < 20 else 55.0, 20) + series("QQQ", flat_q, 20)
assert one(run(on_start, actions=[act("X", 0, 2.0)])[0])["split_factor"] == 1.0          # start close already post-split
on_end = series("X", lambda i: 100.0 if i < 20 else 52.0, 20) + series("QQQ", flat_q, 20)
o = one(run(on_end, actions=[act("X", 20, 2.0)])[0])
assert o["split_factor"] == 2.0 and o["ret"] == 0.04
# 6) a >40% day-over-day move with no recorded split -> split_unverified (never inferred)
assert one(run(fwd)[0])["reason"] == "split_unverified"
assert one(run(fwd)[0])["status"] == "unavailable"
# a genuine 35% move is not a gap
big = series("X", lambda i: 100.0 if i < 10 else 65.0, 20) + series("QQQ", flat_q, 20)
assert one(run(big)[0])["status"] == "matured"

# 7) MAE coverage: one missing session inside the window -> ret scored, MAE null with the missing date listed
hole = [r for r in series("X", dip, 20) if r["session"] != SESS[9]] + series("QQQ", flat_q, 20)
o = one(run(hole)[0])
assert o["status"] == "matured" and o["mae"] is None and o["mae_status"] == "unavailable(coverage_incomplete)"
assert o["mae_coverage"]["missing_sessions"] == [SESS[9]] and o["mae_coverage"]["covered"] == 19
bhole = series("X", dip, 20) + [r for r in series("QQQ", flat_q, 20) if r["session"] != SESS[3]]
assert one(run(bhole)[0])["mae"] is None                           # benchmark coverage is required too

# 8) recorded maturity date disagrees with the NYSE calendar -> invalid, never scored
bad = series("X", x, 20) + series("QQQ", flat_q, 20)
bad[0] = dict(bad[0], matures=dict(bad[0]["matures"], **{"20": "2099-01-01"}))
o = one(run(bad)[0])
assert o["status"] == "invalid" and o["reason"].startswith("matures_mismatch")

# 9) duplicate event_id across ledgers -> fail closed
try:
    run(series("X", x, 20), promoted=[obs("X", 0, 100.0, eid="g-X-0")])
    raise AssertionError("duplicate accepted")
except fol.ContractError as e:
    assert "duplicate_event_id" in str(e)

# 10) split lookup failed -> symbol held (pending), nothing written for it; existing results kept in view
add_h, cur_h, pend_h, _ = run(g, hold={"X"})
assert not [o for o in add_h if o["symbol"] == "X"]
add_k, cur_k, _, _ = run(g, existing=add, hold={"X"})
assert add_k == [] and any(o["symbol"] == "X" for o in cur_k)

# 11) scorecard: groups never pooled, n<20 INSUFFICIENT, independence view, pending derived, UNPROVEN
promo = [obs("X", 0, 100.0, eid="p-X-0", group_tag="p", decision="等待修复")]
add_s, cur_s, pend_s, as_of_s = run(g, promoted=promo)
sc = fol.scorecard(cur_s, pend_s, as_of_s, contract, digest, "T")
groups = {(c["group"], c["decision"]) for c in sc["cells"]}
assert ("genuine_forward", "修复候选") in groups and ("promoted", "等待修复") in groups
assert all(c["status"] == "INSUFFICIENT" and c["hit_rate"] is None for c in sc["cells"])
assert sc["learning_state"] == "UNPROVEN" and sc["contract_hash"] == digest and sc["pending"]
many = []
for k in range(25):                                                   # 25 rows, one consecutive run -> 1 episode
    many.append({"outcome_id": f"o{k}", "group": "genuine_forward", "h": 20, "symbol": "Y", "session": SESS[k],
                 "decision": "修复候选", "eligible": True, "status": "matured", "hit": True, "market_mode": "normal"})
sc2 = fol.scorecard(many, {}, SESS[25], contract, digest, "T")
c = sc2["cells"][0]
assert c["scored"] == 25 and c["hit_rate"] == 1.0 and c["status"] == "reportable_minimum_only"
assert c["independent_episodes"] == 1 and c["episode_hit_rate"] is None
assert sc2["regime_coverage"][0]["modes"] == {"normal": 25}

# 12) contract pin: an edited rule fails closed
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "c.json"
    doc = json.loads(fol.CONTRACT.read_text(encoding="utf-8"))
    doc["rules"]["min_n_for_rate"] = 10
    p.write_text(json.dumps(doc, ensure_ascii=False))
    try:
        fol.load_contract(p)
        raise AssertionError("edited contract accepted")
    except fol.ContractError:
        pass

# 13) split refresh: dedupes, records failures (never "no split"), action ids stable
calls = []
def fake(sym):
    calls.append(sym)
    if sym == "BAD":
        raise TimeoutError()
    return [{"type": "split", "symbol": sym, "ex_date": "2026-01-20", "ratio": 2.0, "numerator": 2, "denominator": 1,
             "source": "yahoo_chart_events_splits"}]
new, failed = fol.refresh_actions({"X", "BAD"}, [], "T", fetch=fake)
assert failed == ["BAD:TimeoutError"] and len(new) == 1 and new[0]["first_seen"] == "T"
again, _ = fol.refresh_actions({"X"}, new, "T2", fetch=fake)
assert again == []

# 14) end to end on temp files: append-only file writes, scorecard written, second run appends nothing
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    saved = (fol.GENUINE, fol.PROMOTED, fol.OUTCOMES, fol.ACTIONS, fol.OUT, fol.committed_lines)
    try:
        fol.GENUINE, fol.PROMOTED, fol.OUTCOMES, fol.ACTIONS, fol.OUT = (d / "g.jsonl", d / "p.jsonl", d / "o.jsonl",
                                                                          d / "a.jsonl", d / "sc.json")
        fol.committed_lines = lambda path: fol.lines_of(path)
        fol.GENUINE.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in g) + "\n", encoding="utf-8")
        assert fol.main(["--offline"]) == 0
        n1 = len(fol.lines_of(fol.OUTCOMES))
        assert n1 >= 1 and json.loads(fol.OUT.read_text())["as_of_session"] == M20
        assert fol.main(["--offline"]) == 0 and len(fol.lines_of(fol.OUTCOMES)) == n1
        # tampering with a committed outcome line is refused
        fol.committed_lines = lambda path: ["{\"tampered\": true}"] if path == fol.OUTCOMES else []
        assert fol.main(["--offline"]) == 1
    finally:
        fol.GENUINE, fol.PROMOTED, fol.OUTCOMES, fol.ACTIONS, fol.OUT, fol.committed_lines = saved

# 15) live ledgers are only read: the scorer imports nothing that writes them
src = (ROOT / "scripts" / "forward_outcome_ledger.py").read_text(encoding="utf-8")
assert "GENUINE.write" not in src and "PROMOTED.write" not in src
print("PASS FWD-01 L1 forward outcome ledger: fsc-1.0 pinned, append-only + supersedes, late-data grace, "
      "splits (2:1, 1:10, multiple, start/end day), split_unverified, MAE coverage, idempotent, scorecard UNPROVEN")
