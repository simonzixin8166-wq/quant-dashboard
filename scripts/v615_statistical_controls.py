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
VERSION="6.15.8f"

sys.path.insert(0,str(ROOT/"scripts"))
from v615_family_scorecard import build as build_family_scorecard
from v615_promotion_gate import build as build_promotion
from v615_event_score import adapt,historical_unconditional_metrics

BLOCK_DATES=["2026-01-05","2026-04-13","2026-07-20","2026-10-26","2027-02-01","2027-05-10","2027-08-16","2027-11-22"]
RULES=["r1","r2","r3"]
AUTHORS=["author-a","author-b","author-c"]
SYMBOLS=["AAA","BBB","CCC"]
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

def synthetic_dates(n,start="2026-01-05",spacing_business_days=70):
    base=pd.Timestamp(start)
    return [(base+pd.tseries.offsets.BDay(spacing_business_days*i)).date().isoformat() for i in range(int(n))]

def synthetic_events(lifts,dates=None,symbols=None):
    dates=list(dates or BLOCK_DATES)
    symbols=list(symbols or SYMBOLS)
    if len(lifts)!=len(dates):
        raise ValueError("lifts and dates must have the same length")
    events=[]
    for wi,day in enumerate(dates):
        for si,symbol in enumerate(symbols):
            rid=RULES[si%len(RULES)]
            author=AUTHORS[si%len(AUTHORS)]
            lift=float(lifts[wi])
            events.append({
                "event_id":f"synthetic-{wi}-{si}-{symbol}","rule_id":rid,"author":author,"symbol":symbol,
                "baseline_date":day,"triggered":True,"scoreable":True,"direction":"bullish",
                "data_quality":{"status":"ok"},
                "scores":{"5":None,"20":None,"60":{
                    "horizon_end_date":(pd.Timestamp(day)+pd.tseries.offsets.BDay(60)).date().isoformat(),
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
    passed,score,gate=full_pipeline_pass(synthetic_events([0.02]*len(BLOCK_DATES)),spec)
    h60=score["cards"][0]["horizons"]["60"]
    return {
        "pass":passed,
        "effective_n":h60.get("effective_n"),
        "time_clusters":h60.get("independent_time_clusters"),
        "ci_lower":(h60.get("lift_ci95") or {}).get("lower"),
        "fdr":h60.get("fdr"),
        "promotion_state":gate["results"][0].get("state"),
        "hypotheses_declared":score.get("multiple_testing",{}).get("hypotheses_declared"),
        "expected":"known positive alpha is statistically detectable using pairwise non-overlapping realized 60-session windows under an active test-only gate",
    }

def wilson_interval(successes,n,z=1.959963984540054):
    if n<=0:return {"lower":None,"upper":None}
    p=successes/n
    denom=1+(z*z)/n
    centre=(p+(z*z)/(2*n))/denom
    half=(z*((p*(1-p)/n)+(z*z)/(4*n*n))**0.5)/denom
    return {"lower":max(0.0,centre-half),"upper":min(1.0,centre+half)}

def repeated_negative_control(spec,seeds=500,max_false_rate_upper=0.10):
    false_promotions=0
    details=[]
    for seed in range(seeds):
        rng=random.Random(100000+seed)
        # One zero-mean shock per pairwise non-overlapping 60-session cluster.
        # All symbols in that cluster share the shock, preserving cross-sectional dependence.
        lifts=[rng.gauss(0.0,0.02) for _ in BLOCK_DATES]
        passed,score,_=full_pipeline_pass(synthetic_events(lifts),spec)
        if passed:false_promotions+=1
        if seed<10:
            h=score["cards"][0]["horizons"]["60"]
            details.append({"seed":seed,"passed":passed,"mean":h.get("unconditional_lift_mean"),"fdr":h.get("fdr")})
    rate=false_promotions/seeds
    interval=wilson_interval(false_promotions,seeds)
    return {
        "pass":interval["upper"]<=max_false_rate_upper,
        "seeds":seeds,
        "false_promotions":false_promotions,
        "false_promotion_rate":rate,
        "wilson95":interval,
        "maximum_allowed_wilson_upper":max_false_rate_upper,
        "sample":details,
        "expected":"under zero alpha, the Wilson 95% upper bound of false promotion stays below the predeclared ceiling",
    }

def _student_t3(rng,scale=0.02):
    z=rng.gauss(0.0,1.0)
    chi=sum(rng.gauss(0.0,1.0)**2 for _ in range(3))
    # t(3) has variance 3; scale back to requested standard deviation.
    return (z/((chi/3.0)**0.5))/(3.0**0.5)*float(scale)

def _ar1_null(seed,n,rho=0.35,scale=0.02):
    rng=random.Random(200000+int(seed))
    innov=float(scale)*((1.0-rho*rho)**0.5)
    x=0.0;out=[]
    for _ in range(int(n)):
        x=rho*x+rng.gauss(0.0,innov)
        out.append(x)
    return out

def _heavy_tail_null(seed,n,scale=0.02):
    rng=random.Random(300000+int(seed))
    return [_student_t3(rng,scale) for _ in range(int(n))]

def scenario_negative_control(spec,name,generator,seeds=500,max_false_rate_upper=0.10,dates=None,symbols=None):
    dates=list(dates or BLOCK_DATES)
    symbols=list(symbols or SYMBOLS)
    false_promotions=0
    for seed in range(int(seeds)):
        lifts=generator(seed,len(dates))
        passed,_,_=full_pipeline_pass(synthetic_events(lifts,dates=dates,symbols=symbols),spec)
        if passed:false_promotions+=1
    interval=wilson_interval(false_promotions,int(seeds))
    return {
        "name":name,
        "pass":interval["upper"]<=float(max_false_rate_upper),
        "seeds":int(seeds),
        "clusters":len(dates),
        "symbols_per_cluster":len(symbols),
        "effective_units":len(dates)*len(symbols),
        "false_promotions":false_promotions,
        "false_promotion_rate":false_promotions/int(seeds),
        "wilson95":interval,
        "maximum_allowed_wilson_upper":float(max_false_rate_upper),
    }

def realism_negative_controls(spec,seeds=500,max_false_rate_upper=0.10):
    # Minimum inferential cluster count (6) with four symbols => 24 effective units,
    # so failure cannot be hidden by the mature60 n>=20 gate.
    min_dates=synthetic_dates(6)
    four_symbols=["AAA","BBB","CCC","DDD"]
    scenarios=[
        scenario_negative_control(
            spec,"minimum_6_clusters_iid",
            lambda seed,n:[random.Random(400000+seed).gauss(0.0,0.02) for _ in range(n)],
            seeds,max_false_rate_upper,min_dates,four_symbols,
        ),
        scenario_negative_control(
            spec,"serial_ar1_rho_0_35",
            lambda seed,n:_ar1_null(seed,n,rho=0.35,scale=0.02),
            seeds,max_false_rate_upper,BLOCK_DATES,SYMBOLS,
        ),
        scenario_negative_control(
            spec,"heavy_tail_student_t3",
            lambda seed,n:_heavy_tail_null(seed,n,scale=0.02),
            seeds,max_false_rate_upper,BLOCK_DATES,SYMBOLS,
        ),
    ]
    return {
        "pass":all(x["pass"] for x in scenarios),
        "predeclared_ceiling":float(max_false_rate_upper),
        "scenarios":scenarios,
        "expected":"zero-alpha false-promotion Wilson 95% upper bound stays below the same predeclared ceiling under minimum-cluster, serial-correlation and heavy-tail conditions",
    }

def power_curve(spec,seeds=80):
    """Diagnostic-only detection curve; never changes thresholds or Promotion."""
    points=[]
    designs=[
        {"clusters":6,"symbols":["AAA","BBB","CCC","DDD"]},
        {"clusters":8,"symbols":["AAA","BBB","CCC"]},
        {"clusters":12,"symbols":["AAA","BBB","CCC"]},
    ]
    effects=[0.0,0.005,0.01,0.02]
    for design in designs:
        dates=synthetic_dates(design["clusters"])
        for effect in effects:
            detected=0
            for seed in range(int(seeds)):
                rng=random.Random(500000+seed+design["clusters"]*1000+int(effect*100000))
                lifts=[float(effect)+rng.gauss(0.0,0.02) for _ in dates]
                passed,_,_=full_pipeline_pass(synthetic_events(lifts,dates=dates,symbols=design["symbols"]),spec)
                if passed:detected+=1
            points.append({
                "clusters":design["clusters"],
                "symbols_per_cluster":len(design["symbols"]),
                "effective_units":design["clusters"]*len(design["symbols"]),
                "effect":effect,
                "seeds":int(seeds),
                "detections":detected,
                "detection_rate":detected/int(seeds),
            })
    return {
        "diagnostic_only":True,
        "threshold_tuning_allowed":False,
        "points":points,
        "note":"This curve describes current frozen-spec detectability. It must not be used to tune thresholds to make a named method pass.",
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

    # Entry-date shift canary: the baseline window must follow the shifted decision
    # date, and future prices after that shifted cutoff still cannot enter its prior baseline.
    shifted=idx[min(90,len(idx)-1)]
    ms1=historical_unconditional_metrics(df,shifted,20,"bullish")
    shifted_mutated=df.copy()
    shifted_mutated.loc[shifted_mutated.index>=shifted,["open","high","low","close"]]=7777.0
    ms2=historical_unconditional_metrics(shifted_mutated,shifted,20,"bullish")
    shifted_future_invariant=(ms1==ms2)

    # Label/order permutation canary: family statistics cannot depend on event list
    # order or within-family rule/author labels when the numeric evidence is unchanged.
    base_events=synthetic_events([0.01,-0.01,0.005,-0.005,0.0,0.0,0.002,-0.002])
    fam,_=synthetic_common(spec)
    base_score=build_family_scorecard(base_events,fam,spec)
    perm=copy.deepcopy(base_events)
    perm["events"]=list(reversed(perm["events"]))
    for i,e in enumerate(perm["events"]):
        e["rule_id"]=RULES[i%len(RULES)]
        e["author"]=AUTHORS[i%len(AUTHORS)]
    perm_score=build_family_scorecard(perm,fam,spec)
    def stable_stat(doc):
        h=((doc.get("cards") or [{}])[0].get("horizons") or {}).get("60") or {}
        f=h.get("fdr") or {}
        return (
            h.get("effective_n"),h.get("independent_time_clusters"),
            h.get("unconditional_lift_mean"),
            (h.get("lift_ci95") or {}).get("lower"),
            f.get("p_value"),f.get("q_value"),f.get("reject"),
        )
    label_order_invariant=(stable_stat(base_score)==stable_stat(perm_score))

    return {
        "pass":pre_ingest_rejected and future_mutation_invariant and shifted_future_invariant and label_order_invariant,
        "pre_ingest_event_rejected":pre_ingest_rejected,
        "primary_exclusion_reason":row.get("primary_exclusion_reason"),
        "future_price_mutation_does_not_change_prior_baseline":future_mutation_invariant,
        "shifted_entry_future_mutation_invariant":shifted_future_invariant,
        "label_and_event_order_permutation_invariant":label_order_invariant,
        "expected":"future/post-ingest information, shifted entry dates, event ordering or within-family labels cannot silently create evidence",
    }

def build(spec):
    positive=positive_control(spec)
    negative=repeated_negative_control(spec)
    realism=realism_negative_controls(spec)
    leak=leakage_canary(spec)
    power=power_curve(spec)
    all_pass=bool(positive["pass"] and negative["pass"] and realism["pass"] and leak["pass"])
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "all_pass":all_pass,
        "controls":{
            "positive_control":positive,
            "repeated_negative_control":negative,
            "realism_negative_controls":realism,
            "leakage_canary":leak,
            "power_curve":power,
        },
        "guardrails":[
            "Synthetic controls never alter production rules or real evidence.",
            "The positive control tests detectability, not investment validity.",
            "All zero-alpha realism scenarios use at least 500 deterministic seeds and the same predeclared Wilson-upper-bound ceiling.",
            "Autocorrelation, heavy tails and the minimum six-cluster boundary are tested without changing thresholds.",
            "The power curve is diagnostic only and cannot tune Promotion thresholds.",
            "Leakage canaries cover pre-ingest rejection, future-price injection, shifted-entry cutoff, and within-family label/order permutations."
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
