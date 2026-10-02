#!/usr/bin/env python3
"""MyAlpha V6.5 Event Window Attribution.

Align mature external outcome-review events with nearby SEC filings and ranked
event/news timestamps. This is descriptive context only: proximity is not
causality.

Research only. No orders. No production-rule mutation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"docs/research/evidence_attribution.json"
OFFICIAL=ROOT/"docs/research/official_evidence.json"
EVENTS=ROOT/"docs/research/event_evidence.json"
OUT=ROOT/"docs/research/event_window_attribution.json"

def load(p):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {}

def parse_date(v):
    if not v:return None
    s=str(v).strip()
    for fmt in ("%Y-%m-%d","%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S.%f%z"):
        try:return datetime.strptime(s.replace("Z","+0000"),fmt).date()
        except Exception:pass
    try:return datetime.fromisoformat(s.replace("Z","+00:00")).date()
    except Exception:return None

def nearest(anchor, rows, date_key):
    a=parse_date(anchor)
    best=None
    if not a:return None
    for row in rows or []:
        d=parse_date(row.get(date_key))
        if not d:continue
        delta=(d-a).days
        cand=(abs(delta),delta,row)
        if best is None or cand[0]<best[0]:best=cand
    if best is None:return None
    _,delta,row=best
    rel="same_day" if delta==0 else "after" if delta>0 else "before"
    return {"days":delta,"abs_days":abs(delta),"relation":rel,"row":row}

def classify_distance(days):
    if days is None:return "unknown"
    a=abs(days)
    if a<=1:return "very_near"
    if a<=3:return "near"
    if a<=7:return "week"
    if a<=14:return "two_weeks"
    return "far"

def build(evidence,official,event_evidence):
    reviews=(evidence.get("failure_attribution") or {}).get("external_outcome_reviews") or []
    sec_symbols=official.get("symbols") or {}
    event_symbols=event_evidence.get("symbols") or {}
    rows=[]
    for r in reviews:
        sym=r.get("symbol"); pub=r.get("published_at")
        sec=(sec_symbols.get(sym) or {}).get("filings") or []
        news=(event_symbols.get(sym) or {}).get("news") or []
        nsec=nearest(pub,sec,"filing_date")
        nnews=nearest(pub,news,"published_at")
        sec_ctx=None
        if nsec:
            f=nsec["row"]
            sec_ctx={
              "form":f.get("form"),"filing_date":f.get("filing_date"),
              "days_from_research":nsec["days"],"distance_band":classify_distance(nsec["days"]),
              "relation":nsec["relation"],"url":f.get("url"),
            }
        news_ctx=None
        if nnews:
            n=nnews["row"]
            news_ctx={
              "title":n.get("title"),"publisher":n.get("publisher"),
              "source_type":n.get("source_type"),"source_priority":n.get("source_priority"),
              "published_at":n.get("published_at"),"days_from_research":nnews["days"],
              "distance_band":classify_distance(nnews["days"]),"relation":nnews["relation"],
              "url":n.get("url"),
            }
        rows.append({
          "event_id":r.get("event_id"),"symbol":sym,"published_at":pub,"title":r.get("title"),
          "review_tags":r.get("review_tags") or [],
          "return_20":r.get("return_20"),"mae_20":r.get("mae_20"),"mfe_20":r.get("mfe_20"),
          "nearest_sec":sec_ctx,"nearest_event":news_ctx,
          "event_context_available":bool(sec_ctx or news_ctx),
          "guardrail":"日期接近只用于生成复盘假设，不代表事件导致该研究结果。"
        })
    with_sec=sum(bool(x["nearest_sec"]) for x in rows)
    with_event=sum(bool(x["nearest_event"]) for x in rows)
    near_sec=sum(bool(x["nearest_sec"]) and x["nearest_sec"]["distance_band"] in {"very_near","near","week"} for x in rows)
    near_event=sum(bool(x["nearest_event"]) and x["nearest_event"]["distance_band"] in {"very_near","near","week"} for x in rows)
    return {
      "version":"6.5.0","generated_at":datetime.now(timezone.utc).isoformat(),
      "rows":rows,
      "summary":{"reviews":len(rows),"with_sec":with_sec,"with_ranked_event":with_event,
                 "sec_within_7d":near_sec,"ranked_event_within_7d":near_event},
      "policy":{
        "descriptive_only":True,"causal_claims":False,"window_unit":"calendar_days",
        "automatic_orders":False,"production_rule_mutation":False
      }
    }

def main():
    out=build(load(EVIDENCE),load(OFFICIAL),load(EVENTS))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["summary"],ensure_ascii=False))
if __name__=="__main__":main()
