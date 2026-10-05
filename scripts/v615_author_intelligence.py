#!/usr/bin/env python3
"""V6.15 Author Intelligence.

Combines two strictly separated views:
1) historical_learning: descriptive author memory from non-gating archives;
2) forward_evidence: point-in-time rules/events only.

Historical rows are never counted as forward evidence and never affect Promotion.
"""
from __future__ import annotations
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"docs"/"data"/"source_intelligence.json"
RULES=ROOT/"research"/"registry"/"rules.json"
FAMILIES=ROOT/"research"/"registry"/"rule_families.json"
EVENTS=ROOT/"research"/"events"/"event_scores_v1.json"
CONTRA=ROOT/"research"/"history"/"contradictions.json"
OUT=ROOT/"docs"/"research"/"author_intelligence.json"
VERSION="6.15-author-intelligence-1"

def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d

def top(values,n=8):
    c=Counter(x for x in values if x)
    return [{"name":k,"count":v} for k,v in c.most_common(n)]

def build(source,rules,families,events,contradictions):
    hist=((source or {}).get("historical_learning") or {})
    hist_rows=list(hist.get("records") or [])
    rule_rows=list((rules or {}).get("rules") or [])
    family_by_rule={
        a.get("rule_id"):a.get("family_id")
        for a in (families or {}).get("assignments") or []
        if a.get("active")
    }
    event_rows=list((events or {}).get("events") or [])

    historical=[]
    by_author=defaultdict(list)
    for r in hist_rows: by_author[str(r.get("author") or "未知作者")].append(r)
    for author,rows in sorted(by_author.items()):
        eligible=[r for r in rows if r.get("historical_learning_eligible")]
        historical.append({
            "author":author,
            "role":rows[0].get("role") if rows else None,
            "records":len(rows),
            "q1_q2_learning_eligible":len(eligible),
            "quality_counts":dict(Counter(str(r.get("quality") or "Q5") for r in rows)),
            "symbols":top([x for r in eligible for x in (r.get("symbols") or [])]),
            "themes":top([x for r in eligible for x in (r.get("themes") or [])]),
            "macro_topics":top([x for r in eligible for x in (r.get("macro_topics") or [])]),
            "structured_operations":sum(len(r.get("operations") or []) for r in eligible),
            "mode":"historical_descriptive_only",
            "gating_effect":"none",
        })

    forward_rules=[r for r in rule_rows if r.get("forward_eligible") is True]
    forward_by_author=defaultdict(list)
    for r in forward_rules: forward_by_author[str(r.get("author") or "未知作者")].append(r)
    forward=[]
    for author,rows in sorted(forward_by_author.items()):
        ids={r.get("rule_id") for r in rows if r.get("rule_id")}
        ev=[e for e in event_rows if e.get("rule_id") in ids and e.get("point_in_time_status")=="eligible"]
        forward.append({
            "author":author,
            "rules":len(rows),
            "families":len({family_by_rule.get(r.get("rule_id")) for r in rows if family_by_rule.get(r.get("rule_id"))}),
            "events":len(ev),
            "scoreable_events":sum(1 for e in ev if e.get("scoreable")),
            "mature_20_events":sum(1 for e in ev if (e.get("maturity") or {}).get("20") and e.get("scoreable")),
            "mature_60_events":sum(1 for e in ev if (e.get("maturity") or {}).get("60") and e.get("scoreable")),
            "status":"forward_observation_only",
        })

    unresolved=[x for x in (contradictions or {}).get("records") or [] if x.get("status")=="unresolved"]
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "historical_learning":{
            "non_gating":True,
            "authors":historical,
            "counts":{
                "records":len(hist_rows),
                "q1_q2_learning_eligible":sum(1 for r in hist_rows if r.get("historical_learning_eligible")),
                "authors":len(historical),
            },
        },
        "forward_evidence":{
            "point_in_time_only":True,
            "authors":forward,
            "counts":{
                "rules":len(forward_rules),
                "authors":len(forward),
                "events":sum(x["events"] for x in forward),
                "scoreable_events":sum(x["scoreable_events"] for x in forward),
            },
        },
        "contradictions":{
            "unresolved_total":len(unresolved),
            "note":"Contradictions remain a risk/diagnostic layer; they do not convert historical learning into forward evidence.",
        },
        "guardrails":[
            "Historical author profiles are descriptive only and never feed Rule Registry, EventScore, Promotion, Planner weights or orders.",
            "Forward author statistics use only forward_eligible Rule Registry rows and point-in-time eligible EventScore events.",
            "No cross-author leaderboard is produced before sufficient independent forward evidence exists.",
            "Zero forward evidence is a valid healthy state and must not be filled with backtests or historical videos.",
        ],
    }

def main():
    out=build(load(SOURCE,{}),load(RULES,{}),load(FAMILIES,{}),load(EVENTS,{}),load(CONTRA,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"historical":out["historical_learning"]["counts"],"forward":out["forward_evidence"]["counts"]},ensure_ascii=False))

if __name__=="__main__":main()
