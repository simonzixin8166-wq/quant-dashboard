#!/usr/bin/env python3
"""V6.14.5 Structured Source Rule Lifecycle (research-only).

Links Source Reading testable rules to Source Outcome events using the exact
(source_id, operation_index) key. It tracks whether a rule is still waiting for
its trigger, has matured stock outcomes, or is an option structure that cannot
be scored without real option P&L.

Critical boundary:
- Sell Put strike touches are underlying-price context only.
- A Sell Put is never scored as successful/failed from stock return alone.
- No lifecycle state can mutate production trading rules or place orders.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
READING=ROOT/"docs"/"research"/"source_reading_memory.json"
OUTCOMES=ROOT/"docs"/"research"/"source_outcome_validation.json"
OUT=ROOT/"docs"/"research"/"source_rule_lifecycle.json"
VERSION="6.14.5"

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def is_scored_alignment(value):
    return value in {"aligned","not_aligned"}

def option_structure(rule,methods):
    actions={str(x).lower() for x in (rule.get("actions") or [])}
    fields=rule.get("fields") or {}
    return (
        "Sell Put" in (methods or [])
        or "sell_put" in actions
        or fields.get("sell_put_strike") is not None
    )

def mapped_events(source_id,operation_index,outcomes):
    prefix=f"{source_id}:{operation_index}:"
    return [e for e in (outcomes.get("events") or []) if str(e.get("event_id") or "").startswith(prefix)]

def stock_maturity(events):
    triggered=[e for e in events if e.get("triggered")]
    if not triggered:
        return "awaiting_trigger",0,0,0
    counts={}
    for h in ("5","20","60"):
        counts[h]=sum(1 for e in triggered if (e.get("outcomes") or {}).get(h))
    if counts["60"]>0:return "mature_60",counts["5"],counts["20"],counts["60"]
    if counts["20"]>0:return "mature_20",counts["5"],counts["20"],counts["60"]
    if counts["5"]>0:return "mature_5",counts["5"],counts["20"],counts["60"]
    return "triggered_pending",0,0,0

def strike_context(events):
    rows=[]
    for e in events:
        check=((e.get("level_checks") or {}).get("sell_put_strike") or {})
        if not check:continue
        rows.append({
            "event_id":e.get("event_id"),
            "symbol":e.get("symbol"),
            "strike":check.get("level"),
            "touch20":check.get("touch20"),
            "touch60":check.get("touch60"),
        })
    return rows

def lifecycle_row(record,prop,outcomes):
    evidence=prop.get("evidence") or {}
    op_index=evidence.get("operation_index")
    methods=evidence.get("method_candidates") or []
    rule=evidence.get("rule") or {}
    events=mapped_events(record.get("source_id"),op_index,outcomes) if op_index is not None else []

    base={
        "rule_id":prop.get("proposition_id"),
        "source_id":record.get("source_id"),
        "operation_index":op_index,
        "author":record.get("author"),
        "published_at":record.get("published_at"),
        "title":record.get("title"),
        "url":record.get("url"),
        "method_candidates":methods,
        "rule":rule,
        "mapped_event_count":len(events),
        "mapped_event_ids":[e.get("event_id") for e in events],
        "scoreable_as_method_performance":False,
        "eligible_for_production":False,
    }

    if not events:
        return {
            **base,
            "state":"mapping_missing",
            "reason":"No Source Outcome event matched the exact source_id + operation_index key.",
            "maturity":{"5":0,"20":0,"60":0},
            "underlying_strike_context":[],
        }

    if option_structure(rule,methods):
        context=strike_context(events)
        touched=any(
            bool(((x.get("touch20") or {}).get("touched"))) or bool(((x.get("touch60") or {}).get("touched")))
            for x in context
        )
        return {
            **base,
            "state":"option_outcome_unscored",
            "reason":"Option strategy outcome requires premium/expiry/option-P&L data; stock return is context only.",
            "maturity":{"5":0,"20":0,"60":0},
            "underlying_strike_context":context,
            "underlying_strike_touched":touched,
            "required_evidence":[
                "option premium at entry",
                "expiry / contract terms",
                "close / assignment outcome or option mark history",
                "fees where available",
            ],
        }

    state,n5,n20,n60=stock_maturity(events)
    scored={
        h:sum(1 for e in events if is_scored_alignment((e.get("alignment") or {}).get(h)))
        for h in ("5","20","60")
    }
    scoreable=any(scored.values())
    return {
        **base,
        "state":state,
        "reason":"Stock-entry lifecycle derived from existing Source Outcome events.",
        "maturity":{"5":n5,"20":n20,"60":n60},
        "scored_alignment":scored,
        "scoreable_as_method_performance":scoreable,
        "underlying_strike_context":[],
    }

def build(reading,outcomes):
    rows=[]
    for record in reading.get("records") or []:
        for prop in record.get("propositions") or []:
            if prop.get("kind")!="testable_rule":continue
            rows.append(lifecycle_row(record,prop,outcomes))

    state_counts=Counter(x["state"] for x in rows)
    by_method=defaultdict(lambda:Counter())
    for row in rows:
        for method in row.get("method_candidates") or []:
            by_method[method][row["state"]]+=1

    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "mode":"research_only_rule_lifecycle",
        "source_reading_version":reading.get("version"),
        "source_outcome_version":outcomes.get("version"),
        "counts":{
            "rules":len(rows),
            "by_state":dict(state_counts),
            "scoreable_stock_rules":sum(1 for x in rows if x.get("scoreable_as_method_performance")),
            "option_unscored":sum(1 for x in rows if x.get("state")=="option_outcome_unscored"),
            "mapping_missing":sum(1 for x in rows if x.get("state")=="mapping_missing"),
        },
        "by_method":{k:dict(v) for k,v in by_method.items()},
        "rules":rows,
        "guardrails":[
            "Mapping uses exact source_id + operation_index; same-article operations are never mixed.",
            "Sell Put strike touch is underlying-price context only, never option P&L.",
            "Option rules stay unscored until option premium/expiry/outcome evidence exists.",
            "Lifecycle states do not change Method Memory performance by themselves.",
            "No lifecycle state can change production thresholds, positions, allocations or orders.",
        ],
    }

def main():
    out=build(load(READING,{}),load(OUTCOMES,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"version":out["version"],"counts":out["counts"]},ensure_ascii=False))

if __name__=="__main__":
    main()
