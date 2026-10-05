#!/usr/bin/env python3
"""Forward intake production-health guard for V6.15.

This report distinguishes "no genuine forward rule has arrived yet" from a
broken production path. It is research-only and never changes Promotion or
production trading state.
"""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATHS={
 "store":ROOT/"research"/"store"/"source_store.json",
 "rules":ROOT/"research"/"registry"/"rules.json",
 "families":ROOT/"research"/"registry"/"rule_families.json",
 "events":ROOT/"research"/"events"/"event_scores_v1.json",
 "spec":ROOT/"research"/"specs"/"evaluation_spec.json",
}
OUT=ROOT/"research"/"reports"/"forward_intake_health.json"
VERSION="6.15.8j"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def build(store,rules,families,events,spec,now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    source_meta={}
    for row in store.get("records") or []:
        rec=row.get("record") or {}
        sid=str(rec.get("id") or row.get("source_key") or "")
        if sid:
            source_meta[sid]=row

    active_rules=[r for r in rules.get("rules") or [] if r.get("active",True)]
    live_rules=[r for r in active_rules if (source_meta.get(str(r.get("source_id"))) or {}).get("ingest_type")=="live_ingest"]
    live_rule_ids={str(r.get("rule_id")) for r in live_rules if r.get("rule_id")}

    current_hash=((spec.get("definitions") or {}).get("rule_family_definition_hash"))
    family_rule_ids={
        str(a.get("rule_id")) for a in families.get("assignments") or []
        if a.get("active") and (not current_hash or a.get("definition_hash")==current_hash) and a.get("rule_id")
    }

    current_events=events.get("events") or []
    event_rule_ids={str(e.get("rule_id")) for e in current_events if e.get("rule_id")}
    forward_events=[e for e in current_events if str(e.get("rule_id")) in live_rule_ids]
    eligible_forward=[e for e in forward_events if e.get("point_in_time_status")=="eligible"]
    scoreable_forward=[e for e in eligible_forward if e.get("scoreable")]

    missing_family=sorted(live_rule_ids-family_rule_ids)
    missing_event=sorted(live_rule_ids-event_rule_ids)
    noneligible=[
        {
            "event_id":e.get("event_id"),
            "rule_id":e.get("rule_id"),
            "point_in_time_status":e.get("point_in_time_status"),
            "primary_exclusion_reason":e.get("primary_exclusion_reason"),
        }
        for e in forward_events if e.get("point_in_time_status")!="eligible"
    ]
    blockers=[]
    if missing_family: blockers.append("live_rule_missing_current_family_assignment")
    if missing_event: blockers.append("live_rule_missing_eventscore_event")
    if noneligible: blockers.append("live_rule_event_not_point_in_time_eligible")

    forward_path_observed=bool(live_rules)
    integrity_pass=not blockers
    status=(
        "waiting_for_first_genuine_forward_rule"
        if not forward_path_observed
        else ("healthy_forward_intake_observed" if integrity_pass else "forward_intake_integrity_failure")
    )
    exclusions=Counter(str(e.get("primary_exclusion_reason") or "scoreable") for e in eligible_forward)

    return {
        "version":VERSION,
        "generated_at":now,
        "spec_version":spec.get("spec_version"),
        "scoring_engine_version":events.get("scoring_engine_version"),
        "status":status,
        "integrity_pass":integrity_pass,
        "forward_path_observed":forward_path_observed,
        "first_scoreable_forward_observed":bool(scoreable_forward),
        "counts":{
            "active_rules":len(active_rules),
            "genuine_forward_rules":len(live_rules),
            "genuine_forward_rule_authors":len({str(r.get("author")) for r in live_rules if r.get("author")}),
            "forward_eventscore_events":len(forward_events),
            "point_in_time_eligible_events":len(eligible_forward),
            "scoreable_forward_events":len(scoreable_forward),
        },
        "eligible_event_primary_outcomes":dict(sorted(exclusions.items())),
        "blockers":blockers,
        "details":{
            "missing_family_rule_ids":missing_family,
            "missing_event_rule_ids":missing_event,
            "noneligible_forward_events":noneligible[:50],
        },
        "guardrails":[
            "No live rule is fabricated to make the forward count non-zero.",
            "Waiting for the first genuine live rule is healthy and distinct from a broken path.",
            "A genuine live rule must map to the current Rule Family definition and an EventScore event.",
            "Its EventScore event must be point-in-time eligible; scoreability may still be blocked by pre-registered semantic or price-source rules.",
            "This guard cannot alter Promotion, thresholds, production rules, positions, or orders."
        ],
    }

def main():
    d={k:load(p,{}) for k,p in PATHS.items()}
    out=build(d["store"],d["rules"],d["families"],d["events"],d["spec"])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":out["status"],
        "integrity_pass":out["integrity_pass"],
        "genuine_forward_rules":out["counts"]["genuine_forward_rules"],
        "scoreable_forward_events":out["counts"]["scoreable_forward_events"],
    },ensure_ascii=False))
    if not out["integrity_pass"]:
        raise SystemExit("forward intake integrity failure: "+",".join(out["blockers"]))

if __name__=="__main__":
    main()
