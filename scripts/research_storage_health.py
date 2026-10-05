#!/usr/bin/env python3
"""Non-destructive storage health for large research artifacts.

Formal append-only evidence is never pruned here. This report identifies when
reader-compatible monthly partitioning should be scheduled.
"""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"research"/"reports"/"storage_health.json"
FILES={
  "step_boundary_log":"research/audit/step_boundary_log.json",
  "source_store":"research/store/source_store.json",
  "event_score_history":"research/history/event_score_history.json",
}
LIMITS={
  "step_boundary_log":5_000_000,
  "source_store":5_000_000,
  "event_score_history":5_000_000,
}

def main():
    rows={}
    for name,rel in FILES.items():
        p=ROOT/rel
        size=p.stat().st_size if p.exists() else 0
        limit=LIMITS[name]
        rows[name]={
          "path":rel,"bytes":size,"limit_bytes":limit,
          "status":"watch" if size>=limit*.75 else "ok",
          "partition_ready":False if name in {"source_store","event_score_history"} else True,
        }
    out={
      "version":"6.15-p2",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "mode":"non_destructive_storage_governance",
      "artifacts":rows,
      "policy":{
        "step_boundary_log":"hash-only + 80-record retention",
        "source_store":"append-only; no pruning before reader-compatible partition migration",
        "event_score_history":"append-only; no pruning before reader-compatible partition migration",
      },
      "next_partition_trigger":"Any formal evidence artifact >=5MB or sustained growth makes reader migration a P2 maintenance task; never delete evidence to hit the threshold.",
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v["bytes"] for k,v in rows.items()},ensure_ascii=False))

if __name__=="__main__":main()
