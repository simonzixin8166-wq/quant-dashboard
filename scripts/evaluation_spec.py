#!/usr/bin/env python3
from __future__ import annotations
import json, math, statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC_PATH=ROOT/"research"/"specs"/"evaluation_spec.json"

def load_spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))

def direction_sign(direction):
    return {"bullish":1.0,"long":1.0,"bearish":-1.0,"short":-1.0}.get(str(direction or "").lower(),0.0)

def direction_adjusted_return(direction, raw_return):
    if raw_return is None:return None
    sign=direction_sign(direction)
    return None if sign==0 else sign*float(raw_return)

def unconditional_lift(direction, raw_return, unconditional_return):
    a=direction_adjusted_return(direction,raw_return)
    b=direction_adjusted_return(direction,unconditional_return)
    return None if a is None or b is None else a-b

def ci95(values):
    vals=[float(x) for x in values if x is not None and math.isfinite(float(x))]
    if len(vals)<2:return {"n":len(vals),"mean":vals[0] if vals else None,"lower":None,"upper":None}
    mean=statistics.fmean(vals)
    sd=statistics.stdev(vals)
    half=1.96*sd/(len(vals)**0.5)
    return {"n":len(vals),"mean":mean,"lower":mean-half,"upper":mean+half}
