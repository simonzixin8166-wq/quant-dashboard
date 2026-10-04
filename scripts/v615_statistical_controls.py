#!/usr/bin/env python3
"""V6.15.8c statistical controls for the family evidence pipeline."""
from __future__ import annotations
import copy,json,random,sys
from datetime import datetime,timezone
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
OUT=ROOT/"research"/"reports"/"statistical_controls.json"
VERSION="6.15.8c"

sys.path.insert(0,str(ROOT/"scripts"))
from v615_family_scorecard import build as build_family_scorecard
from v615_promotion_gate import build as build_promotion
from v615_event_score import adapt,historical_unconditional_metrics

WEEK_DATES=["2026-01-05","2026-01-12","2026-01-19","2026-01-26","2026-02-02","2026-02-09","2026-02-16","2026-02-23"]
RULES=["r1","r2","r3"]
AUTHORS=["author-a","author-b","author-c"]
FAMILY="synthetic-family"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def synthetic_common(spec):
    dh=(spec.get("definitions") or {}).get("rule_family_definition_hash")
    families={"assignments":[]}
    registry={"rules":[]}
    for rid,author in zip(RULES,AUTHORS):
        families["assignments"].append({
            "rule_id":rid,"family_id":FAMILY,"definition_hash":dh,"active":True,
            "family_key":{"primary_method":"synthetic","instrument_type":"equity"}
        })
        registry["rules"].append({
            "rule_id":rid,"author":author,"source_snapshot_hash":"src-"+rid,
            "normalized_rule_hash":"rule-"+rid,"url":"https://example.invalid/"+rid
        })
    return families,registry

def synthetic_events(lifts):
    events=[]
    for wi,day in enumerate(WEEK_DATES):
        for ai,(rid,author) in enumerate(zip(RULES,AUTHORS)):
            lift=float(lifts[wi])
            events.append({
                "event_id":f"synthetic-{wi}-{ai}","rule_id":rid,"author":author,"symbol":"ABC",
                "baseline_date":day,"triggered":True,"scoreable":True,"direction":"bullish",
                "data_quality":{"status":"ok"},
                "scores":{"5":None,"20":None,"60":{
                    "unconditional_lift":lift,
                    "direction_adjusted_return":lift+0.01,
                    "direction_adjusted_mae":-0.04,
                    "unconditional_baseline_direction_adjusted_mae":-0.05,
                    "excess_vs_qqq":lift,
                }}
            })
    return {"events":events}

def active_spec(spec):
    s=copy.deepcopy(spec)
    s["promotion_activation"]={"state":"active"}
    return s

def full_pipeline_pass(events,spec):
    families,registry=synthetic_common(spec)
    score=build_family_scorecard(events,families,spec)
    gate=build_promotion(score,{"records":[]},registry,families,events,active_spec(spec))
    row=(gate.get("results") or [{}])[0]
    return bool(row.get("passed")),score,gate

def positive_control(spec):
    passed,score,gate=full_pipeline_pass(synthetic_events([0.02]*len(WEEK_DATES)),spec)
    h60=score["cards"][0]["horizons"]["60"]
    return {
        "pass":passed,
        "effective_n":h60.get("effective_n"),
        "time_clusters":h60.get("independent_time_clusters"),
        "ci_lower":(h60.get("lift_ci95") or {}).get("lower"),
        "fdr":h60.get("fdr"),
        "promotion_state":gate["results"][0].get("state"),
        "expected":"known positive alpha is statistically detectable under an active test-only gate",
    }

def repeated_negative_control(spec,seeds=60,max_false_rate=0.10):
    false_promotions=0
    details=[]
    for seed in range(seeds):
        rng=random.Random(100000+seed)
        # One independent zero-mean shock per weekly block; all authors in the
        # block share it, deliberately preserving market correlation.
        lifts=[rng.gauss(0.0,0.02) for _ in WEEK_DATES]
        passed,score,_=full_pipeline_pass(synthetic_events(lifts),spec)
        if passed:false_promotions+=1
        if seed<10:
            h=score["cards"][0]["horizons"]["60"]
            details.append({"seed":seed,"passed":passed,"mean":h.get("unconditional_lift_mean"),"fdr":h.get("fdr")})
    rate=false_promotions/seeds
    return {
        "pass":rate<=max_false_rate,
        "seeds":seeds,
        "false_promotions":false_promotions,
        "false_promotion_rate":rate,
        "maximum_allowed_rate":max_false_rate,
        "sample":details,
        "expected":"repeated zero-alpha simulations remain below the predeclared false-promotion ceiling",
    }

def leakage_canary(spec):
    idx=pd.date_range("2025-09-01",periods=120,freq="B")
    df=pd.DataFrame({"open":100.0,"high":101.0,"low":99.0,"close":100.0},index=idx)
    baseline="2026-01-05"
    validation={"events":[{
        "event_id":"s1:0:ABC:0","author":"a","symbol":"ABC","published_at":"2026-01-04",
        "baseline_date":baseline,"baseline_kind":"next_session","triggered":True,
        "operation":{"conditions":[],"actions":["buy"]},
        "alignment":{"direction":"bullish","5":"aligned"},
        "outcomes":{"5":{"return":0.01,"benchmark_return":0.0,"excess_vs_qqq":0.01,"mae":-0.01,"mfe":0.02}}
    }]}
    registry={"legacy_mapping":[{"source_id":"s1","operation_index":0,"rule_id":"r1"}]}
    histories={"ABC":{"df":df,"meta":{"status":"ok","source":"stooq_archive","price_series_hash":"synthetic"}}}
    source_store={"records":[{
        "source_key":"s1","first_fetched_at":"2026-01-20T00:00:00Z",
        "ingest_type":"test","published_at_semantics":"source_archive_publication_date",
        "timestamp_confidence":"high","snapshot_hash":"h","record":{"id":"s1"}
    }]}
    out=adapt(validation,registry,histories,spec,source_store)
    row=out["events"][0]
    pre_ingest_rejected=(row.get("primary_exclusion_reason")=="non_point_in_time_source")

    decision=pd.Timestamp(baseline)
    m1=historical_unconditional_metrics(df,decision,20,"bullish")
    mutated=df.copy()
    mutated.loc[mutated.index>=decision,["open","high","low","close"]]=9999.0
    m2=historical_unconditional_metrics(mutated,decision,20,"bullish")
    future_mutation_invariant=(m1==m2)
    return {
        "pass":pre_ingest_rejected and future_mutation_invariant,
        "pre_ingest_event_rejected":pre_ingest_rejected,
        "primary_exclusion_reason":row.get("primary_exclusion_reason"),
        "future_price_mutation_does_not_change_prior_baseline":future_mutation_invariant,
        "expected":"future or post-ingest information cannot silently enter scoreable evidence",
    }

def build(spec):
    positive=positive_control(spec)
    negative=repeated_negative_control(spec)
    leak=leakage_canary(spec)
    all_pass=bool(positive["pass"] and negative["pass"] and leak["pass"])
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "all_pass":all_pass,
        "controls":{
            "positive_control":positive,
            "repeated_negative_control":negative,
            "leakage_canary":leak,
        },
        "guardrails":[
            "Synthetic controls never alter production rules or real evidence.",
            "The positive control tests detectability, not investment validity.",
            "The repeated negative control is deterministic across fixed seeds.",
            "The leakage canary must fail closed on post-decision or pre-ingest information."
        ],
    }

def main():
    out=build(load(SPEC,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"all_pass":out["all_pass"],"controls":{k:v["pass"] for k,v in out["controls"].items()}},ensure_ascii=False))
    return 0 if out["all_pass"] else 2

if __name__=="__main__":
    raise SystemExit(main())
