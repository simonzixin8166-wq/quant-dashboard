import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import autonomous_research_executor as rx

def t(i,kind,priority):
    return {"task_id":f"t{i}","kind":kind,"key":f"k{i}","title":f"T{i}","priority":priority,
            "questions":[],"evidence_sources":[],"run_count":1}

# Saturated live queue: one method-rule candidate must still get a bounded slot.
today=[t(i,"market_anomaly",p) for i,p in enumerate([98,95,92,90,88,86,84,82],start=1)]
candidate=t(20,"method_rule_candidate",68)
planner={"today":today,"queue":today+[candidate]}
sel=rx.select_tasks(planner,8)
assert len(sel)==8
assert any(x["kind"]=="method_rule_candidate" for x in sel)
# Highest-risk tasks remain; only the lowest selected live slot is displaced.
assert {98,95,92,90,88,86,84}.issubset({x["priority"] for x in sel})
assert 82 not in {x["priority"] for x in sel}

# With spare capacity, candidate is appended naturally.
planner2={"today":today[:5],"queue":today[:5]+[candidate,t(30,"failure_review",66)]}
sel2=rx.select_tasks(planner2,8)
assert len(sel2)==7
assert any(x["kind"]=="method_rule_candidate" for x in sel2)
assert any(x["kind"]=="failure_review" for x in sel2)

# Only one fairness slot is reserved even if multiple candidates exist.
c2=t(21,"method_rule_candidate",67)
sel3=rx.select_tasks({"today":today,"queue":today+[candidate,c2]},8)
assert sum(x["kind"]=="method_rule_candidate" for x in sel3)==1
assert next(x for x in sel3 if x["kind"]=="method_rule_candidate")["priority"]==68

# No candidate => original top live set is unchanged.
sel4=rx.select_tasks({"today":today,"queue":today},8)
assert [x["task_id"] for x in sel4]==[x["task_id"] for x in today]

print("PASS V6.14.4 bounded research fairness slot / no starvation / live-risk priority preserved")
