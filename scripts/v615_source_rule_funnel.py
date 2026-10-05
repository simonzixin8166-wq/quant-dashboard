#!/usr/bin/env python3
"""Source -> Rule diagnostic funnel v1.0.

Result-blind, non-gating observability only. It never reads outcomes, returns,
Promotion results, or readiness state, and it never changes evidence semantics.
"""
from __future__ import annotations
import hashlib, json, os, tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATHS={
    "store":ROOT/"research"/"store"/"source_store.json",
    "reading":ROOT/"docs"/"research"/"source_reading_memory.json",
    "rules":ROOT/"research"/"registry"/"rules.json",
    "state":ROOT/"research"/"state"/"source_rule_funnel_state.json",
    "history":ROOT/"research"/"history"/"source_rule_funnel_history.json",
    "latest":ROOT/"research"/"reports"/"source_rule_funnel_latest.json",
}
SCHEMA_VERSION="1.0"
TERMINAL_REASONS=(
    "backfill",
    "rekeyed_duplicate",
    "identity_ambiguous",
    "late_discovery",
    "admission_integrity_rejected",
    "no_operations",
    "operation_missing_symbol",
    "no_testable_proposition",
    "testable_rule_without_registry_rule",
    "rule_formed",
    "reason_not_recorded",
)

def load(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def dump_atomic(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(obj,f,ensure_ascii=False,indent=2)
            f.write("\n")
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def write_transaction(items):
    """Atomically-as-practical replace a small file bundle with rollback."""
    prepared=[]
    originals={}
    try:
        for path,obj in items:
            path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
            originals[path]=(path.exists(),path.read_bytes() if path.exists() else None)
            fd,tmp=tempfile.mkstemp(prefix=path.name+".",dir=path.parent)
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                json.dump(obj,f,ensure_ascii=False,indent=2);f.write("\n")
            prepared.append((path,tmp))
        replaced=[]
        for path,tmp in prepared:
            os.replace(tmp,path);replaced.append(path)
        return
    except Exception:
        for path in reversed(locals().get("replaced",[])):
            existed,data=originals[path]
            if existed:
                path.write_bytes(data)
            else:
                path.unlink(missing_ok=True)
        raise
    finally:
        for _,tmp in prepared:
            if os.path.exists(tmp):os.unlink(tmp)

def stable_hash(v):
    raw=json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def row_source_id(row):
    rec=(row or {}).get("record") or {}
    return str(rec.get("id") or row.get("source_key") or "")

def admission_consistent(row):
    cls=(row or {}).get("admission_class")
    ingest=(row or {}).get("ingest_type")
    if cls=="genuine_forward":return ingest=="live_ingest"
    if cls=="initial_migration":return ingest=="initial_migration"
    if cls in {"backfill","late_discovery","identity_ambiguous"}:return ingest=="backfill_ingest"
    if cls=="rekeyed_duplicate":return ingest in {"initial_migration","backfill_ingest","live_ingest"}
    return False

def effective_operation_symbols(op,rec):
    return list((op or {}).get("symbols") or (rec or {}).get("symbols") or [])

def terminal_reason(row,reading_rec,active_forward_rules):
    cls=(row or {}).get("admission_class")
    if cls=="backfill":return "backfill"
    if cls=="rekeyed_duplicate":return "rekeyed_duplicate"
    if cls=="identity_ambiguous":return "identity_ambiguous"
    if cls=="late_discovery":return "late_discovery"
    if cls!="genuine_forward" or not admission_consistent(row):
        return "admission_integrity_rejected"

    rec=(row or {}).get("record") or {}
    ops=list(rec.get("operations") or [])
    if not ops:return "no_operations"
    if not any(effective_operation_symbols(op,rec) for op in ops):
        return "operation_missing_symbol"
    if reading_rec is None:return "reason_not_recorded"
    testable=[
        p for p in (reading_rec.get("propositions") or [])
        if p.get("kind")=="testable_rule"
    ]
    if not testable:return "no_testable_proposition"
    sid=row_source_id(row)
    if not any(r.get("source_id")==sid for r in active_forward_rules):
        return "testable_rule_without_registry_rule"
    return "rule_formed"

def concentration(rules):
    if not rules:return {"independent_authors":0,"largest_author_rule_count":0,"largest_author_rule_share":None}
    counts=Counter(str(r.get("author") or "unknown") for r in rules)
    largest=max(counts.values()) if counts else 0
    return {
        "independent_authors":len(counts),
        "largest_author_rule_count":largest,
        "largest_author_rule_share":largest/len(rules) if rules else None,
    }

def compute(store,reading,rules,state=None,history=None,now=None):
    now=now or datetime.now(timezone.utc).isoformat()
    rows=list(store.get("records") or [])
    current_keys={str(r.get("source_key")) for r in rows if r.get("source_key")}
    prior_keys=set((state or {}).get("source_keys") or [])
    baseline=not bool(state and "source_keys" in state)
    new_keys=set() if baseline else current_keys-prior_keys
    new_rows=[r for r in rows if str(r.get("source_key")) in new_keys]

    reading_by_id={str(r.get("source_id")):r for r in (reading.get("records") or []) if r.get("source_id")}
    active_forward_rules=[
        r for r in (rules.get("rules") or [])
        if r.get("active",True) and r.get("forward_eligible") is True
    ]

    reasons=Counter()
    assignments=[]
    for row in sorted(new_rows,key=lambda x:str(x.get("source_key") or "")):
        sid=row_source_id(row)
        rr=terminal_reason(row,reading_by_id.get(sid),active_forward_rules)
        reasons[rr]+=1
        assignments.append({
            "source_key":row.get("source_key"),
            "source_id":sid,
            "admission_class":row.get("admission_class"),
            "terminal_reason":rr,
        })
    counts={k:int(reasons.get(k,0)) for k in TERMINAL_REASONS}
    total=len(new_rows)
    terminal_total=sum(counts.values())
    shares={k:(counts[k]/total if total else None) for k in TERMINAL_REASONS}

    admission_ops={}
    for cls in sorted({str(r.get("admission_class") or "missing") for r in new_rows}):
        subset=[r for r in new_rows if str(r.get("admission_class") or "missing")==cls]
        admission_ops[cls]={
            "sources":len(subset),
            "sources_with_operations":sum(1 for r in subset if ((r.get("record") or {}).get("operations") or [])),
        }

    no_ops=[r for r in new_rows if reasons and terminal_reason(r,reading_by_id.get(row_source_id(r)),active_forward_rules)=="no_operations"]
    no_ops_with_context=sum(1 for r in no_ops if ((r.get("record") or {}).get("symbols") or (r.get("record") or {}).get("topics")))
    no_ops_without_context=len(no_ops)-no_ops_with_context

    new_ids={row_source_id(r) for r in new_rows}
    new_rule_rows=[r for r in active_forward_rules if str(r.get("source_id") or "") in new_ids]
    new_ops=sum(len((r.get("record") or {}).get("operations") or []) for r in new_rows)
    new_props=sum(len((reading_by_id.get(row_source_id(r)) or {}).get("propositions") or []) for r in new_rows)
    new_rule_author=concentration(new_rule_rows)

    store_by_sid={row_source_id(r):r for r in rows}
    cumulative_forward_rules=[
        r for r in active_forward_rules
        if (store_by_sid.get(str(r.get("source_id") or "")) or {}).get("admission_class")=="genuine_forward"
    ]
    cumulative_author=concentration(cumulative_forward_rules)

    low_conf_new=sum(
        1 for r in new_rows
        if r.get("admission_class")=="genuine_forward" and r.get("timestamp_confidence")!="high"
    )
    low_conf_total=sum(
        1 for r in rows
        if r.get("admission_class")=="genuine_forward" and r.get("timestamp_confidence")!="high"
    )

    status="baseline_established" if baseline else "ok"
    snapshot_core={
        "schema_version":SCHEMA_VERSION,
        "window":{
            "definition":"current persistent Source Store keys minus previous successful funnel-state keys",
            "previous_key_count":len(prior_keys) if not baseline else None,
            "current_key_count":len(current_keys),
        },
        "status":status,
        "new_sources_total":total,
        "terminal_reason_counts":counts,
        "terminal_reason_share":shares,
        "conservation":{"terminal_total":terminal_total,"expected_total":total,"pass":terminal_total==total},
        "downstream_counts":{
            "admission_sources_with_operations":admission_ops,
            "no_operations_context_split":{
                "with_symbols_or_topics":no_ops_with_context,
                "without_symbols_or_topics":no_ops_without_context,
            },
            "operations_total":new_ops,
            "propositions_total":new_props,
            "new_forward_rules_total":len(new_rule_rows),
            **new_rule_author,
            "cumulative_forward_rules":len(cumulative_forward_rules),
            "cumulative_forward_authors":cumulative_author["independent_authors"],
            "cumulative_largest_author_rule_share":cumulative_author["largest_author_rule_share"],
        },
        "low_confidence_genuine_forward_sources":{
            "new":low_conf_new,
            "cumulative":low_conf_total,
            "review_required":low_conf_new>0,
        },
        "assignments":assignments,
        "guardrails":[
            "Diagnostic only; this artifact is never a Promotion, Readiness, Planner, Agent, or trading input.",
            "Source-level terminal reasons conserve new source identities; downstream counts are intentionally non-conserving.",
            "No realized performance or outcome fields are read by this funnel.",
        ],
    }
    snapshot_id=stable_hash({
        "schema_version":SCHEMA_VERSION,
        "baseline":baseline,
        "new_keys":sorted(new_keys),
        "current_keys":sorted(current_keys),
    })
    report={**snapshot_core,"generated_at":now,"snapshot_id":snapshot_id}
    hist=list((history or {}).get("records") or [])
    should_append=baseline or bool(new_keys)
    if should_append and not any(x.get("snapshot_id")==snapshot_id for x in hist):
        hist.append({k:v for k,v in report.items() if k!="assignments"})
    history_out={"schema_version":SCHEMA_VERSION,"generated_at":now,"records":hist}
    state_out={
        "schema_version":SCHEMA_VERSION,
        "generated_at":now,
        "source_keys":sorted(current_keys),
        "source_key_count":len(current_keys),
        "last_snapshot_id":snapshot_id,
    }
    return report,state_out,history_out

def run():
    now=datetime.now(timezone.utc).isoformat()
    store=load(PATHS["store"],{})
    reading=load(PATHS["reading"],{})
    rules=load(PATHS["rules"],{})
    state=load(PATHS["state"],None)
    history=load(PATHS["history"],{"schema_version":SCHEMA_VERSION,"records":[]})
    report,state_out,history_out=compute(store,reading,rules,state,history,now)
    if not report["conservation"]["pass"]:
        raise RuntimeError("source funnel conservation failed")
    # State/history are written only after successful computation.
    # Publish the diagnostic view first. Only after that succeeds do we advance
    # the key-set window atomically; any failure leaves state/history unchanged.
    dump_atomic(PATHS["latest"],report)
    write_transaction([
        (PATHS["history"],history_out),
        (PATHS["state"],state_out),
    ])
    return report

def main():
    try:
        out=run()
        print(json.dumps({
            "status":out.get("status"),
            "new_sources_total":out.get("new_sources_total"),
            "conservation_pass":(out.get("conservation") or {}).get("pass"),
            "new_forward_rules_total":((out.get("downstream_counts") or {}).get("new_forward_rules_total")),
        },ensure_ascii=False))
        return 0
    except Exception as exc:
        # Non-gating observability: preserve state/history and emit an error report only.
        err={
            "schema_version":SCHEMA_VERSION,
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "status":"funnel_error",
            "funnel_error":str(exc),
            "non_gating":True,
        }
        try:dump_atomic(PATHS["latest"],err)
        except Exception:pass
        print(json.dumps(err,ensure_ascii=False))
        return 0

if __name__=="__main__":raise SystemExit(main())
