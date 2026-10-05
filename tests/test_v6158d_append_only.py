import copy,sys
from unittest.mock import patch,Mock
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from v615_append_only_guard import check,head_json

old={
 "event_history":{"records":[{"event_id":"e","spec_version":"1.1","score_hash":"h","recorded_at":"t","score":{"x":1}}]},
 "rules":{"rules":[{"rule_id":"r","semantic_hash":"s","duplicate_rank":1,"first_seen_at":"t","source_id":"src","normalized_rule_hash":"n","extractor_input_hash":"x","extractor_input_revisions":[]}],
 "source_observations":[{"source_id":"src","first_registry_seen_at":"t","first_extractor_version":"x","first_extractor_input_hash":"h"}]},
 "source_store":{"records":[{"source_key":"src","first_fetched_at":"t","ingest_type":"initial_migration","admission_class":"initial_migration","admission_classified_at":"t","identity_parent_source_key":None,"snapshot_hash":"a","snapshot_history":[]}]},
 "contradictions":{"records":[{"contradiction_id":"c","first_seen_at":"t","last_seen_at":"t"}]},
 "source_rule_funnel_history":{"records":[{"snapshot_id":"snap1","schema_version":"1.0","new_sources_total":0}]}
}
assert check(old,copy.deepcopy(old))==[]

bad=copy.deepcopy(old);bad["event_history"]["records"]=[]
assert any("event_history_missing" in x for x in check(old,bad))

bad=copy.deepcopy(old);bad["rules"]["rules"][0]["first_seen_at"]="changed"
assert any("rule_immutable_changed" in x for x in check(old,bad))

# Content can evolve only when prior provenance hash is retained.
good=copy.deepcopy(old);good["rules"]["rules"][0]["extractor_input_hash"]="y";good["rules"]["rules"][0]["extractor_input_revisions"]=[{"extractor_input_hash":"x"}]
assert not any("rule_extractor_revision_lost" in x for x in check(old,good))
bad=copy.deepcopy(old);bad["rules"]["rules"][0]["extractor_input_hash"]="y"
assert any("rule_extractor_revision_lost" in x for x in check(old,bad))

good=copy.deepcopy(old);good["source_store"]["records"][0]["snapshot_hash"]="b";good["source_store"]["records"][0]["snapshot_history"]=["a"]
assert not any("source_snapshot_revision_lost" in x for x in check(old,good))
bad=copy.deepcopy(old);bad["source_store"]["records"][0]["snapshot_hash"]="b"
assert any("source_snapshot_revision_lost" in x for x in check(old,bad))
print("PASS V6.15.8d-2 append-only negative invariants")


bad=copy.deepcopy(old);bad["source_store"]["records"][0]["admission_class"]="genuine_forward"
assert any("source_immutable_changed:src:admission_class" in x for x in check(old,bad))

# HEAD absence is legal; other git failures must fail closed.
with patch("v615_append_only_guard.subprocess.check_output") as co, patch("v615_append_only_guard.subprocess.run") as run:
    co.return_value="deadbeef\n"
    run.side_effect=[
        Mock(returncode=128,stdout="",stderr="missing"),
        Mock(returncode=0,stdout="",stderr=""),
    ]
    assert head_json("research/does-not-exist.json")=={}

with patch("v615_append_only_guard.subprocess.check_output") as co, patch("v615_append_only_guard.subprocess.run") as run:
    co.return_value="deadbeef\n"
    run.side_effect=[
        Mock(returncode=128,stdout="",stderr="io failure"),
        Mock(returncode=2,stdout="",stderr="repo failure"),
    ]
    try:
        head_json("research/history/event_score_history.json")
        raise AssertionError("non-missing git failure must fail closed")
    except RuntimeError:
        pass
print("PASS V6.15.8l append-only HEAD read fail-closed behavior")


bad=copy.deepcopy(old);bad["rules"]["source_observations"][0]["first_registry_seen_at"]="changed"
assert any("source_observation_immutable_changed" in x for x in check(old,bad))

bad=copy.deepcopy(old);bad["rules"]["source_observations"]=[]
assert any("source_observation_missing" in x for x in check(old,bad))

bad=copy.deepcopy(old);bad["source_rule_funnel_history"]["records"][0]["new_sources_total"]=99
assert any("funnel_history_rewritten" in x for x in check(old,bad))

bad=copy.deepcopy(old);bad["source_rule_funnel_history"]["records"]=[]
assert any("funnel_history_missing" in x for x in check(old,bad))
print("PASS funnel/source-observation append-only invariants")
