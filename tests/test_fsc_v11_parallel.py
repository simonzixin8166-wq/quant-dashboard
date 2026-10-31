"""fsc-1.1 parallel view (Owner 10/30; GPT 6513028156 §1.5, 6537701769 §4.4): QQQ/QQQM leave hit/miss; same rules
otherwise; derived from fsc-1.0 rows (never writes outcome rows, never rescores); fsc-1.0 stays official."""
import copy, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward_outcome_ledger as fol

c10, d10 = fol.load_contract()
c11, d11 = fol.load_contract_v11()
assert d10 == "3eb0efc58e3eba8b" and d11 == fol.PINNED_V11[1] and c11["based_on"]["hash"] == d10
# only the benchmark-identical keys differ from fsc-1.0
extra = set(c11["rules"]) - set(c10["rules"])
assert extra == {"benchmark_identical_symbols", "benchmark_identical_policy"}
assert all(c11["rules"][k] == c10["rules"][k] for k in c10["rules"])
assert c11["rules"]["benchmark_identical_symbols"] == ["QQQ", "QQQM"] and c11["status"] == "parallel_view"
# a changed v1.1 rule is refused (no silent edits)
bad = copy.deepcopy(c11); bad["rules"]["benchmark_identical_symbols"] = ["QQQ"]
p = ROOT / "tests" / "_tmp_v11.json"; p.write_text(json.dumps(bad))
try:
    fol.load_contract_v11(p); raise AssertionError("mismatch accepted")
except fol.ContractError:
    pass
finally:
    p.unlink()

def row(sym, hit, status="matured", dec="等待修复"):
    return {"outcome_id": sym + str(hit), "event_id": sym, "group": "promoted", "h": 20, "symbol": sym, "decision": dec,
            "eligible": False, "session": "2026-09-29", "status": status, "hit": hit, "market_mode": "normal"}
cur = [row("QQQ", False), row("QQQM", True), row("SMH", True), row("TSLA", False), row("AMD", "abstain", dec="继续观察"),
       row("IREN", None, status="unavailable")]
before = json.dumps(cur, sort_keys=True)
v = fol.view_v11(cur, c11)
assert json.dumps(cur, sort_keys=True) == before                    # originals untouched
sc10 = fol.scorecard(cur, {}, "2026-10-30", c10, d10, "t")
sc11 = fol.scorecard(v, {}, "2026-10-30", c10, d10, "t")
cell = lambda sc: next(c for c in sc["cells"] if c["decision"] == "等待修复")
assert (cell(sc10)["scored"], cell(sc10)["hits"], cell(sc10)["benchmark_identical"]) == (4, 2, 0)
assert (cell(sc11)["scored"], cell(sc11)["hits"], cell(sc11)["benchmark_identical"]) == (2, 1, 2)
# real committed data: v1.1 removes exactly the QQQ/QQQM scored rows and nothing else
outs = fol.read_jsonl(fol.OUTCOMES)
n_bi = sum(1 for o in outs if o["symbol"] in ("QQQ", "QQQM") and o["status"] == "matured" and o["hit"] in (True, False))
s10 = sum(c["scored"] for c in fol.scorecard(outs, {}, "x", c10, d10, "t")["cells"])
s11 = sum(c["scored"] for c in fol.scorecard(fol.view_v11(outs, c11), {}, "x", c10, d10, "t")["cells"])
assert s10 - s11 == n_bi, (s10, s11, n_bi)
src = (ROOT / "scripts" / "forward_outcome_ledger.py").read_text(encoding="utf-8")
assert '"official": False' in src and "parallel_views" in src
print(f"PASS fsc-1.1 parallel view: QQQ/QQQM out of hit/miss ({n_bi} committed rows), fsc-1.0 unchanged and official")
