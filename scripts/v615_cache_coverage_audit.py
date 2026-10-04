#!/usr/bin/env python3
"""V6.15.8a audit cache-only EventScore symbols against local and upstream STOOQ.

This is diagnostic only. It never upgrades cache data into scoreable evidence and
never chooses a fallback source based on performance.
"""
from __future__ import annotations
import csv, io, json, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
OUT=ROOT/"research"/"audit"/"v615_cache_only_stooq_coverage.json"

import sys
sys.path.insert(0,str(ROOT/"scripts"))
from local_history_agent import read_archive
from source_history_cache import read_cache

VERSION="6.15.8a"

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def stooq_symbol(symbol):
    return f"{str(symbol or '').lower()}.us"

def probe_stooq(symbol,days=45,timeout=12):
    end=datetime.now(timezone.utc).date()
    start=end-timedelta(days=days)
    params=urllib.parse.urlencode({
        "s":stooq_symbol(symbol),"i":"d",
        "d1":start.strftime("%Y%m%d"),"d2":end.strftime("%Y%m%d"),
    })
    url="https://stooq.com/q/d/l/?"+params
    req=urllib.request.Request(url,headers={"User-Agent":"MyAlphaView/ResearchCoverageAudit"})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as resp:
            body=resp.read().decode("utf-8","replace")
        rows=list(csv.DictReader(io.StringIO(body)))
        valid=[r for r in rows if r.get("Date") and r.get("Close")]
        if valid:
            return {
                "status":"available",
                "rows":len(valid),
                "from":valid[0].get("Date"),
                "to":valid[-1].get("Date"),
                "symbol_mapping":stooq_symbol(symbol),
            }
        return {"status":"no_valid_rows","rows":0,"symbol_mapping":stooq_symbol(symbol)}
    except Exception as exc:
        return {"status":"temporary_probe_failure","error":str(exc)[:180],"symbol_mapping":stooq_symbol(symbol)}

def classify(local_present,cache_present,probe):
    if local_present:
        return "mapping_or_local_selection_bug"
    if probe.get("status")=="available":
        return "local_archive_provisioning_gap"
    if probe.get("status")=="temporary_probe_failure":
        return "temporary_probe_failure"
    if cache_present:
        return "structural_or_symbol_mapping_unresolved"
    return "missing_everywhere_unresolved"

def build(events,core,cache,probe_fn=probe_stooq):
    candidates={}
    for ev in events.get("events") or []:
        if not ev.get("rule_id"):continue
        if (ev.get("data_quality") or {}).get("status")!="cache_only_unscored":continue
        sym=str(ev.get("symbol") or "")
        if not sym:continue
        row=candidates.setdefault(sym,{"event_ids":[],"authors":set(),"entry_types":set()})
        row["event_ids"].append(ev.get("event_id"))
        row["authors"].add(ev.get("author"))
        row["entry_types"].add(ev.get("entry_type"))
    rows=[]
    for sym,data in sorted(candidates.items()):
        local_present=sym in core
        cache_present=sym in cache
        probe=probe_fn(sym)
        rows.append({
            "symbol":sym,
            "event_count":len(data["event_ids"]),
            "event_ids":data["event_ids"],
            "authors":sorted(x for x in data["authors"] if x),
            "entry_types":sorted(x for x in data["entry_types"] if x),
            "local_stooq_archive_present":local_present,
            "cache_present":cache_present,
            "upstream_stooq_probe":probe,
            "classification":classify(local_present,cache_present,probe),
        })
    counts={}
    for row in rows:counts[row["classification"]]=counts.get(row["classification"],0)+1
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "policy":"diagnostic_only_no_fallback_selection",
        "counts":{"symbols":len(rows),"events":sum(x["event_count"] for x in rows),"by_classification":counts},
        "symbols":rows,
        "guardrails":[
            "Absence from the local STOOQ watchlist archive does not imply absence from the STOOQ service.",
            "No fallback source is selected in this audit.",
            "Coverage/data-quality criteria may determine a future source policy; investment performance may not.",
            "Cache-only data remains unscored."
        ]
    }

def main():
    out=build(load(EVENTS,{}),read_archive(),read_cache())
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
