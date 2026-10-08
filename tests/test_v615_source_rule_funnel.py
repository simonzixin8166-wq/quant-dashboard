import copy, json, tempfile, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import v615_source_rule_funnel as funnel

def srow(key,cls="genuine_forward",ingest="live_ingest",ops=None,symbols=None,topics=None,sid=None,confidence="high"):
    sid=sid or key
    return {
      "source_key":key,"admission_class":cls,"ingest_type":ingest,
      "timestamp_confidence":confidence,
      "effective_forward_eligible":cls=="genuine_forward" and ingest=="live_ingest" and confidence=="high",
      "record":{"id":sid,"operations":ops or [],"symbols":symbols or [],"topics":topics or []},
    }

def mem(sid,testable=False,props=None):
    ps=list(props or [])
    if testable:
        ps.append({"kind":"testable_rule","evidence":{"rule":{"fields":{},"conditions":[],"actions":["buy"]}}})
    return {"source_id":sid,"propositions":ps,"testable_rule_count":sum(1 for p in ps if p.get("kind")=="testable_rule")}

def rule(sid,rid="r1",author="a",eligible=True):
    # Downstream Forward consumers read only effective_forward_eligible; the funnel
    # additionally requires the source to be genuine_forward in the store.
    return {"source_id":sid,"rule_id":rid,"author":author,"active":True,"forward_eligible":eligible,"effective_forward_eligible":eligible}

# 1. First run is baseline only, never backfills the current store into "new".
store={"records":[srow("old",cls="initial_migration",ingest="initial_migration")]}
report,state,hist=funnel.compute(store,{"records":[]},{"rules":[]},None,{"records":[]},"2026-10-05T00:00:00Z")
assert report["status"]=="baseline_established"
assert report["new_sources_total"]==0
assert state["source_keys"]==["old"]
assert len(hist["records"])==1

# 2/3. Key-set window sees a rekey even though it may carry an inherited old timestamp.
rekey=srow("new-key",cls="rekeyed_duplicate",ingest="initial_migration",sid="new-id")
store2={"records":store["records"]+[rekey]}
r2,s2,h2=funnel.compute(store2,{"records":[]},{"rules":[]},state,hist,"2026-10-06T00:00:00Z")
assert r2["new_sources_total"]==1
assert r2["terminal_reason_counts"]["rekeyed_duplicate"]==1
assert r2["conservation"]["pass"] is True

# 4. Repeating the same inputs never re-counts and never appends another history snapshot.
r3,s3,h3=funnel.compute(store2,{"records":[]},{"rules":[]},s2,h2,"2026-10-07T00:00:00Z")
assert r3["new_sources_total"]==0
assert len(h3["records"])==len(h2["records"])

# 6. Terminal reason priority: admission class wins over downstream content.
amb=srow("amb",cls="identity_ambiguous",ingest="backfill_ingest",ops=[{"symbols":["ABC"]}],symbols=["ABC"])
rr=funnel.terminal_reason(amb,mem("amb",testable=True),[rule("amb")])
assert rr=="identity_ambiguous"

# 7. If Reading Memory has no record, funnel does not invent a semantic reason.
g=srow("g",ops=[{"symbols":["ABC"],"actions":["buy"]}],symbols=["ABC"])
assert funnel.terminal_reason(g,None,[])=="reason_not_recorded"

# Source downstream mappings.
assert funnel.terminal_reason(srow("n"),mem("n"),[])=="no_operations"
assert funnel.terminal_reason(srow("m",ops=[{"actions":["buy"]}]),mem("m"),[])=="operation_missing_symbol"
assert funnel.terminal_reason(srow("p",ops=[{"symbols":["ABC"]}],symbols=["ABC"]),mem("p"),[])=="no_testable_proposition"
assert funnel.terminal_reason(srow("t",ops=[{"symbols":["ABC"]}],symbols=["ABC"]),mem("t",testable=True),[])=="testable_rule_without_registry_rule"
assert funnel.terminal_reason(srow("f",ops=[{"symbols":["ABC"]}],symbols=["ABC"]),mem("f",testable=True),[rule("f")])=="rule_formed"

# 8. Cumulative forward-author counts exclude historical/non-genuine rules.
base_state=s2
newg=srow("gf",ops=[{"symbols":["ABC"]}],symbols=["ABC"],sid="gf")
mixed={"records":store2["records"]+[newg,srow("hist",cls="backfill",ingest="backfill_ingest",sid="hist")]}
reading={"records":[mem("gf",testable=True),mem("hist",testable=True)]}
rules={"rules":[rule("gf","rg","forward",True),rule("hist","rh","legacy",True)]}
r4,_,_=funnel.compute(mixed,reading,rules,base_state,h2,"2026-10-08T00:00:00Z")
assert r4["downstream_counts"]["cumulative_forward_rules"]==1
assert r4["downstream_counts"]["cumulative_forward_authors"]==1
assert r4["terminal_reason_counts"]["rule_formed"]==1
assert r4["terminal_reason_counts"]["backfill"]==1

# Admission-level operation supply and no-operation context split are diagnostic only.
ctx=srow("ctx",ops=[],symbols=["ABC"],sid="ctx")
noc=srow("noc",ops=[],sid="noc")
prior={"schema_version":"1.0","source_keys":sorted({x["source_key"] for x in mixed["records"]})}
mix2={"records":mixed["records"]+[ctx,noc]}
r5,_,_=funnel.compute(mix2,{"records":[]},{"rules":[]},prior,{"records":[]},"2026-10-09T00:00:00Z")
split=r5["downstream_counts"]["no_operations_context_split"]
assert split["with_symbols_or_topics"]==1 and split["without_symbols_or_topics"]==1
assert r5["conservation"]["pass"]

# 5. Transaction rollback: state/history both remain unchanged when replacement fails.
with tempfile.TemporaryDirectory() as td:
    td=Path(td);a=td/"a.json";b=td/"b.json"
    a.write_text('{"v":1}\n');b.write_text('{"v":1}\n')
    original_replace=funnel.os.replace
    calls={"n":0}
    def fail_second(src,dst):
        calls["n"]+=1
        if calls["n"]==2: raise OSError("synthetic")
        return original_replace(src,dst)
    funnel.os.replace=fail_second
    try:
        try:funnel.write_transaction([(a,{"v":2}),(b,{"v":2})])
        except OSError:pass
    finally:
        funnel.os.replace=original_replace
    assert json.loads(a.read_text())=={"v":1}
    assert json.loads(b.read_text())=={"v":1}

# 11. Funnel paths do not include EventScore/outcome artifacts.
assert "events" not in funnel.PATHS
assert "promotion" not in funnel.PATHS
assert "readiness" not in funnel.PATHS

print("PASS Source->Rule Funnel v1.0 baseline/key-diff/conservation/history/rollback/result-blind")


# Failed latest-report publication must occur before state/history advance.
script=(ROOT/"scripts"/"v615_source_rule_funnel.py").read_text(encoding="utf-8")
run_body=script.split("def run():",1)[1].split("def main():",1)[0]
assert run_body.index('dump_atomic(PATHS["latest"],report)') < run_body.index("write_transaction([")
print("PASS funnel failure cannot advance state/history before latest report publication")
