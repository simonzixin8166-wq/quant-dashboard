#!/usr/bin/env python3
"""Candidate Family Shadow Scorecard v1.0.

Aggregates compiled-candidate EventScores by immutable candidate family_signature
using Evaluation Spec 1.7 statistical machinery. This is deliberately separate
from the frozen Rule Family v1.3 Promotion Gate because Candidate signals do not
carry explicit operation-action direction semantics.

Research/Shadow only. No Promotion/Production mutation.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from evaluation_spec import load_spec, block_bootstrap_ci, block_signflip_pvalue, benjamini_hochberg
    from v615_dependence_clusters import overlap_connected_clusters, assert_non_overlapping
except ModuleNotFoundError:
    from scripts.evaluation_spec import load_spec, block_bootstrap_ci, block_signflip_pvalue, benjamini_hochberg
    from scripts.v615_dependence_clusters import overlap_connected_clusters, assert_non_overlapping

ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/"research"/"events"/"candidate_event_scores_v1.json"
OUT=ROOT/"research"/"reports"/"candidate_family_scorecards.json"
PUBLIC=ROOT/"docs"/"research"/"candidate_family_scorecard_status.json"
VERSION="1.0"

def load(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def mean(vals):
    vals=[float(x) for x in vals if x is not None]
    return sum(vals)/len(vals) if vals else None

def family_buckets(events,spec_version):
    buckets=defaultdict(list)
    for e in events.get("events") or []:
        if str(e.get("spec_version"))!=str(spec_version):continue
        fid=str(e.get("family_signature") or "")
        if fid:buckets[fid].append(e)
    return buckets

def unit_rows(rows,h,cluster_map):
    grouped=defaultdict(list)
    for e in rows:
        score=(e.get("scores") or {}).get(str(h))
        if not score or score.get("unconditional_lift") is None:continue
        cluster=cluster_map.get(str(e.get("event_id") or ""))
        if cluster is None:continue
        grouped[(str(e.get("symbol") or "unknown"),cluster)].append(e)
    out=[]
    for (symbol,cluster),evs in sorted(grouped.items()):
        scores=[(x.get("scores") or {}).get(str(h)) or {} for x in evs]
        out.append({
            "symbol":symbol,
            "cluster":cluster,
            "events":len(evs),
            "authors":sorted({str(x.get("author") or "unknown") for x in evs}),
            "lift":mean([x.get("unconditional_lift") for x in scores]),
            "return":mean([x.get("direction_adjusted_return") for x in scores]),
            "mae":mean([x.get("direction_adjusted_mae") for x in scores]),
            "benchmark_mae":mean([x.get("unconditional_baseline_direction_adjusted_mae") for x in scores]),
            "mae_diff":mean([
                x.get("direction_adjusted_mae")-x.get("unconditional_baseline_direction_adjusted_mae")
                for x in scores
                if x.get("direction_adjusted_mae") is not None
                and x.get("unconditional_baseline_direction_adjusted_mae") is not None
            ]),
            "excess_vs_qqq":mean([x.get("excess_vs_qqq") for x in scores]),
        })
    return out

def build(events,spec):
    buckets=family_buckets(events,spec.get("spec_version"))
    defs=spec.get("definitions") or {}
    mt=defs.get("multiple_testing") or {}
    th=spec.get("thresholds") or {}
    horizons=[int(x) for x in (defs.get("horizons_trading_days") or [5,20,60])]
    min_clusters=int(mt.get("minimum_time_clusters_for_testing") or 6)
    resamples=int(mt.get("bootstrap_resamples") or 2000)
    seed=int(mt.get("bootstrap_seed") or 6158)
    q=float(mt.get("fdr_q") or 0.05)

    cards=[];pvals={}
    for fid,rows in sorted(buckets.items()):
        scoreable=[x for x in rows if x.get("scoreable")]
        horizons_out={}
        for h in horizons:
            cluster_map,cluster_meta=overlap_connected_clusters(scoreable,h,require_lift=True)
            if not assert_non_overlapping(cluster_meta):
                raise AssertionError(f"candidate family clusters overlap: {fid}|{h}")
            units=unit_rows(scoreable,h,cluster_map)
            blocks=defaultdict(list);mae_blocks=defaultdict(list)
            for u in units:
                if u.get("lift") is not None:blocks[u["cluster"]].append(u["lift"])
                if u.get("mae_diff") is not None:mae_blocks[u["cluster"]].append(u["mae_diff"])
            block_values=[v for _,v in sorted(blocks.items())]
            mae_values=[v for _,v in sorted(mae_blocks.items())]
            block_means=[mean(v) for v in block_values]
            testable=len(block_values)>=min_clusters
            dseed=seed+int(hashlib.sha256(f"candidate|{fid}|{h}".encode()).hexdigest()[:8],16)%100000
            ci=block_bootstrap_ci(block_values,resamples,dseed) if testable else {
                "blocks":len(block_values),"n":len(units),
                "mean":mean([u.get("lift") for u in units]),"lower":None,"upper":None
            }
            mae_ci=block_bootstrap_ci(mae_values,resamples,dseed+17) if len(mae_values)>=min_clusters else {
                "blocks":len(mae_values),"n":sum(len(v) for v in mae_values),
                "mean":mean([u.get("mae_diff") for u in units]),"lower":None,"upper":None
            }
            p=block_signflip_pvalue(block_means,resamples,dseed) if testable else None
            pvals[f"{fid}|{h}"]=p if p is not None else float(mt.get("untestable_hypothesis_pvalue_for_fdr",1.0))
            sym_counts=defaultdict(int)
            for u in units:sym_counts[u["symbol"]]+=1
            max_share=max(sym_counts.values())/len(units) if units and sym_counts else None
            horizons_out[str(h)]={
                "raw_mature_events":sum(1 for x in scoreable if (x.get("scores") or {}).get(str(h))),
                "effective_n":len(units),
                "independent_time_clusters":len(block_values),
                "independent_authors":len({a for u in units for a in (u.get("authors") or [])}),
                "direction_adjusted_return_mean":mean([u.get("return") for u in units]),
                "unconditional_lift_mean":mean([u.get("lift") for u in units]),
                "lift_ci95":ci,
                "excess_vs_qqq_mean":mean([u.get("excess_vs_qqq") for u in units]),
                "direction_adjusted_mae_mean":mean([u.get("mae") for u in units]),
                "benchmark_direction_adjusted_mae_mean":mean([u.get("benchmark_mae") for u in units]),
                "mae_noninferiority_difference_mean":mean([u.get("mae_diff") for u in units]),
                "mae_noninferiority_ci95":mae_ci,
                "single_symbol_effective_unit_share_max":max_share,
                "symbol_effective_unit_counts":dict(sorted(sym_counts.items())),
                "test_status":"testable" if testable else "not_testable",
                "p_value":p,
                "fdr":None,
            }
        cards.append({
            "candidate_family_signature":fid,
            "event_count":len(rows),
            "scoreable_event_count":len(scoreable),
            "authors":sorted({str(x.get("author") or "unknown") for x in scoreable}),
            "symbols":sorted({str(x.get("symbol") or "unknown") for x in scoreable}),
            "horizons":horizons_out,
            "promotion_gate_compatible":False,
            "promotion_gate_blocker":"frozen_rule_family_v1_3_requires_explicit_operation_action_semantics",
        })

    fdr=benjamini_hochberg(pvals,q) if pvals else {}
    for card in cards:
        for h in [str(x) for x in horizons]:
            key=f"{card['candidate_family_signature']}|{h}"
            if key in fdr:card["horizons"][h]["fdr"]=fdr[key]
        h60=card["horizons"].get("60") or {}
        statistical_reviewable=(
            h60.get("effective_n",0)>=int(th.get("mature_60_effective_samples_min") or 20)
            and h60.get("independent_authors",0)>=int(th.get("independent_authors_min") or 3)
            and h60.get("independent_time_clusters",0)>=int(th.get("independent_time_clusters_min") or 6)
            and h60.get("test_status")=="testable"
        )
        card["shadow_statistical_status"]="statistically_reviewable" if statistical_reviewable else "sample_insufficient_research_only"

    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "spec_version":spec.get("spec_version"),
        "mode":"candidate_family_shadow_statistics_only",
        "counts":{
            "families":len(cards),
            "families_with_events":sum(1 for c in cards if c.get("event_count",0)>0),
            "statistically_reviewable":sum(1 for c in cards if c.get("shadow_statistical_status")=="statistically_reviewable"),
            "promotion_gate_compatible":0,
        },
        "multiple_testing":{
            "hypotheses_declared":len(pvals),
            "fdr_q":q,
            "method":"Benjamini-Hochberg",
            "untestable_pvalue":float(mt.get("untestable_hypothesis_pvalue_for_fdr",1.0)),
        },
        "cards":cards,
        "promotion_effect":"none",
        "production_effect":"none",
        "guardrails":[
            "Candidate families are research groupings keyed by candidate family_signature, not frozen Rule Family v1.3 identities.",
            "Inference reuses Spec 1.7 overlap-connected clustering, block bootstrap, sign-flip p-values and FDR.",
            "Statistical reviewability does not imply Promotion eligibility.",
            "No Candidate family may enter the existing Promotion Gate without an explicit reviewed governance/spec decision.",
            "No Production mutation or automatic trading is possible from this scorecard.",
        ],
    }

def public_status(out):
    return {
        "version":out.get("version"),
        "generated_at":out.get("generated_at"),
        "spec_version":out.get("spec_version"),
        "counts":out.get("counts"),
        "state":"shadow_statistics_ready",
        "promotion_bridge":"blocked_by_frozen_rule_family_semantics",
        "promotion_effect":"none",
        "production_effect":"none",
    }

def main():
    out=build(load(EVENTS,{}),load_spec())
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    PUBLIC.parent.mkdir(parents=True,exist_ok=True)
    PUBLIC.write_text(json.dumps(public_status(out),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
