import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import method_memory_engine as mm

def ev(actions=None,op=None,title="",alignment20=None,out20=True):
    e={
      "actions":actions or [],
      "operation":op or {},
      "title":title,
      "outcomes":{"5":{"return":0.01},"20":{"return":0.02} if out20 else None,"60":None},
      "alignment":{"5":"aligned","20":alignment20,"60":None},
    }
    return e

# Explicit position actions must create direct position-management evidence
# even when article topics are absent.
assert "仓位与加减仓" in mm.direct_methods({},ev(actions=["buy"]))
assert "仓位与加减仓" in mm.direct_methods({},ev(actions=["add"]))
assert "仓位与加减仓" in mm.direct_methods({},ev(actions=["planned_buy"],op={"entry_1":100}))

# Sell Put requires explicit option semantics.
assert "Sell Put" in mm.direct_methods({},ev(actions=["sell_put"]))
assert "Sell Put" in mm.direct_methods({},ev(op={"sell_put_strike":90}))
assert "Sell Put" not in mm.direct_methods({"topics":["Sell Put"]},ev(actions=["buy"]))

# LEAPS requires explicit structure text/field, not topic alone.
assert "LEAPS" in mm.direct_methods({},ev(op={"strategy":"QQQ LEAPS call"}))
assert "LEAPS" not in mm.direct_methods({"topics":["LEAPS"]},ev(actions=["buy"]))

# Trend confirmation requires explicit technical condition.
assert "趋势确认" in mm.direct_methods({},ev(op={"conditions":["breakout above ma20"]}))
assert "趋势确认" not in mm.direct_methods({"topics":["趋势确认"]},ev(actions=["buy"]))

# Broad concepts remain context-only; no inference from ordinary actions.
for forbidden in ("估值与价格","风险管理","长期持有纪律","失败复盘","AI研究方法"):
    assert forbidden not in mm.direct_methods({"topics":[forbidden]},ev(actions=["buy"]))

# Evidence maturity gates.
assert mm.evidence_state([])["state"]=="context_only"
early=[ev(actions=["buy"],alignment20="aligned",out20=False) for _ in range(2)]
assert mm.evidence_state(early)["state"]=="direct_early"

dev=[ev(actions=["buy"],alignment20="aligned") for _ in range(5)]
assert mm.evidence_state(dev)["state"]=="direct_developing"

support=[ev(actions=["buy"],alignment20="aligned") for _ in range(8)]
s=mm.evidence_state(support)
assert s["state"]=="outcome_supportive" and s["mature_n"]==8 and s["alignment_rate"]==1.0

mixed=[ev(actions=["buy"],alignment20=("aligned" if i<4 else "not_aligned")) for i in range(8)]
assert mm.evidence_state(mixed)["state"]=="outcome_mixed"

challenge=[ev(actions=["buy"],alignment20=("aligned" if i<2 else "not_aligned")) for i in range(8)]
assert mm.evidence_state(challenge)["state"]=="outcome_challenging"

# Build must admit direct-only events even when article topics are absent.
source={
 "counts":{"records":1},
 "records":[{"url":"u1","author":"tester","topics":[],"title":"explicit add"}]
}
validation={
 "events":[{
   "event_id":"e1","url":"u1","author":"tester","symbol":"QQQ","title":"explicit add",
   "attribution":"author_action","triggered":True,
   "actions":["add"],"operation":{"actions":["add"]},"baseline_date":"2026-09-01",
   "outcomes":{"5":{"return":0.01,"mae":-0.01,"mfe":0.02},"20":{"return":0.03,"mae":-0.02,"mfe":0.05},"60":None},
   "alignment":{"5":"aligned","20":"aligned","60":None},
 }]
}
out=mm.build(source,validation,histories={},evidence={})
pos=next(x for x in out["methods"] if x["method"]=="仓位与加减仓")
assert pos["direct_validated_events"]==1
assert pos["performance_basis"]=="direct_event_attribution"
assert pos["status"]=="direct_early"
assert out["counts"]["direct_method_links"]==1

print("PASS V6.13.1 method direct attribution / conservative gates / evidence maturity")
