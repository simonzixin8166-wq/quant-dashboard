#!/usr/bin/env python3
"""Frozen V6.15.8b entry-semantics interpreter."""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REGISTRY_PATH=ROOT/"research"/"specs"/"entry_semantics_registry.json"

def load_registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

def _condition_text(operation):
    return " ".join(str(x).lower() for x in ((operation or {}).get("conditions") or []))

def classify_event(event,registry=None):
    registry=registry or load_registry()
    kind=str(event.get("baseline_kind") or "")
    op=event.get("operation") or {}
    text=_condition_text(op)
    sem=registry.get("semantics") or {}

    if kind in set((sem.get("next_session") or {}).get("baseline_kinds") or []):
        entry="next_session";source="baseline_kind:next_session"
    elif kind in set((sem.get("conditional") or {}).get("baseline_kinds") or []):
        entry="conditional";source=f"baseline_kind:{kind}"
    else:
        entry="unknown";source="no_frozen_match"
        for name in ("breakout","pullback_limit"):
            words=(sem.get(name) or {}).get("condition_keywords") or []
            hit=next((w for w in words if str(w).lower() in text),None)
            if hit:
                entry=name;source=f"condition_keyword:{hit}";break

    cfg=sem.get(entry) or sem.get("unknown") or {}
    triggered=bool(event.get("triggered"))
    if entry=="unknown":
        fill_status="unknown"
    elif triggered:
        fill_status=cfg.get("default_fill_status") or "simulated_fill"
    else:
        fill_status="no_fill"
    return {
        "entry_type":entry,
        "fill_status":fill_status,
        "fill_confidence":cfg.get("fill_confidence") or "none",
        "fill_model":cfg.get("fill_model") or "none",
        "inference_source":source,
        "registry_version":registry.get("registry_version"),
        "scoreable_semantics":bool(cfg.get("scoreable_if_other_guards_pass")),
    }

def classify_rule(rule,registry=None):
    """Result-blind entry class for family assignment."""
    registry=registry or load_registry()
    fields=(rule or {}).get("fields") or {}
    conditions=" ".join(str(x).lower() for x in ((rule or {}).get("conditions") or []))
    sem=registry.get("semantics") or {}
    if fields.get("entry_below") is not None:
        return "conditional"
    for name in ("breakout","pullback_limit"):
        words=(sem.get(name) or {}).get("condition_keywords") or []
        if any(str(w).lower() in conditions for w in words):
            return name
    if fields.get("entry_1") is not None or fields.get("entry_2") is not None:
        return "unknown"
    return "next_session"
