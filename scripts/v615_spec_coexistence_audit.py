#!/usr/bin/env python3
"""Audit append-only coexistence of all EventScore spec versions."""
from __future__ import annotations
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/"research"/"history"/"event_score_history.json"
SPEC=ROOT/"research"/"specs"/"evaluation_spec.json"
OUT=ROOT/"research"/"audit"/"eventscore_spec_coexistence.json"
VERSION="6.15.8d"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def build(history,current_spec_version="1.2"):
    by_event=defaultdict(list)
    by_spec=Counter()
    for row in history.get("records") or []:
        by_event[row.get("event_id")].append(row)
        by_spec[str(row.get("spec_version"))]+=1
    rows_out=[]
    with_current=0
    with_prior_and_current=0
    preserved_prior=0
    for eid,rows in sorted(by_event.items(),key=lambda kv:str(kv[0])):
        current=[r for r in rows if str(r.get("spec_version"))==str(current_spec_version)]
        prior=[r for r in rows if str(r.get("spec_version"))!=str(current_spec_version)]
        if current:with_current+=1
        if current and prior:
            with_prior_and_current+=1
            preserved_prior+=sum(1 for r in prior if r.get("score_hash"))
            new=current[-1]
            new_score=new.get("score") or {}
            new_px=(new_score.get("data_quality") or {}).get("price_series_hash")
            rows_out.append({
                "event_id":eid,
                "current_spec_version":str(current_spec_version),
                "current_score_hash":new.get("score_hash"),
                "current_price_series_hash":new_px,
                "prior_versions":[{
                    "spec_version":str(r.get("spec_version")),
                    "score_hash":r.get("score_hash"),
                    "price_series_hash":((r.get("score") or {}).get("data_quality") or {}).get("price_series_hash"),
                    "record_preserved":bool(r.get("score_hash")),
                } for r in prior],
            })
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "current_spec_version":str(current_spec_version),
        "counts":{
            "records_by_spec":dict(sorted(by_spec.items())),
            "events_total":len(by_event),
            "events_with_current":with_current,
            "events_with_prior_and_current":with_prior_and_current,
            "preserved_prior_records":preserved_prior,
        },
        "events":rows_out,
        "guardrails":[
            "Every historical spec record is append-only and remains addressable by spec_version and score_hash.",
            "A new current spec record may be appended but cannot rewrite prior spec records.",
            "Price-series hashes are compared as provenance context, not used to overwrite old results."
        ],
    }

def main():
    spec=load(SPEC,{})
    out=build(load(HISTORY,{}),spec.get("spec_version") or "unknown")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
