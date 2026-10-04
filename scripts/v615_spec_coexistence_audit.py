#!/usr/bin/env python3
"""Audit coexistence of legacy and current EventScore specs without overwriting history."""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/"research"/"history"/"event_score_history.json"
OUT=ROOT/"research"/"audit"/"eventscore_spec_coexistence.json"
VERSION="6.15.8c"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def build(history):
    by_event=defaultdict(list)
    for row in history.get("records") or []:
        by_event[row.get("event_id")].append(row)
    both=[]
    legacy_count=current_count=0
    for eid,rows in by_event.items():
        specs={str(r.get("spec_version")) for r in rows}
        legacy=[r for r in rows if str(r.get("spec_version"))=="1.0"]
        current=[r for r in rows if str(r.get("spec_version"))=="1.1"]
        legacy_count+=len(legacy);current_count+=len(current)
        if legacy and current:
            old=legacy[0];new=current[-1]
            old_score=old.get("score") or {};new_score=new.get("score") or {}
            old_hash=(old_score.get("data_quality") or {}).get("price_series_hash")
            new_hash=(new_score.get("data_quality") or {}).get("price_series_hash")
            both.append({
                "event_id":eid,
                "legacy_score_hash":old.get("score_hash"),
                "current_score_hash":new.get("score_hash"),
                "legacy_price_series_hash":old_hash,
                "current_price_series_hash":new_hash,
                "legacy_record_preserved":bool(old.get("score_hash")),
                "price_series_hash_equal":old_hash==new_hash,
                "note":"Different current score hash is allowed when schema/spec metadata changes. The stored legacy record is never overwritten."
            })
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "counts":{"legacy_v1_0_records":legacy_count,"current_v1_1_records":current_count,"events_with_both":len(both)},
        "events":both,
        "guardrails":[
            "Legacy spec records remain append-only.",
            "Spec migration may create a new EventScore record but cannot rewrite the stored v1.0 score_hash.",
            "A full-series price hash can legitimately change as archives append new bars; historical record preservation is the rollback guarantee."
        ],
    }

def main():
    out=build(load(HISTORY,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
