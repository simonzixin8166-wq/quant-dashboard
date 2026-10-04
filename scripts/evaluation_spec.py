#!/usr/bin/env python3
from __future__ import annotations
import json, math, random, statistics
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


def percentile(values,q):
    vals=sorted(float(x) for x in values if x is not None and math.isfinite(float(x)))
    if not vals:return None
    if len(vals)==1:return vals[0]
    pos=(len(vals)-1)*float(q)
    lo=int(math.floor(pos));hi=int(math.ceil(pos))
    if lo==hi:return vals[lo]
    w=pos-lo
    return vals[lo]*(1-w)+vals[hi]*w

def block_bootstrap_ci(block_values,resamples=2000,seed=6158):
    """Percentile CI by resampling complete time blocks."""
    blocks=[[float(x) for x in vals if x is not None and math.isfinite(float(x))] for vals in block_values if vals]
    blocks=[x for x in blocks if x]
    if len(blocks)<2:
        flat=[x for b in blocks for x in b]
        return {"blocks":len(blocks),"n":len(flat),"mean":statistics.fmean(flat) if flat else None,"lower":None,"upper":None}
    rng=random.Random(int(seed))
    reps=[]
    for _ in range(int(resamples)):
        chosen=[blocks[rng.randrange(len(blocks))] for _ in range(len(blocks))]
        flat=[x for b in chosen for x in b]
        if flat:reps.append(statistics.fmean(flat))
    flat=[x for b in blocks for x in b]
    return {
        "blocks":len(blocks),
        "n":len(flat),
        "mean":statistics.fmean(flat) if flat else None,
        "lower":percentile(reps,0.025),
        "upper":percentile(reps,0.975),
    }

def block_signflip_pvalue(block_means,resamples=2000,seed=6158):
    """One-sided cluster sign-flip p-value for H0 mean lift <= 0."""
    vals=[float(x) for x in block_means if x is not None and math.isfinite(float(x))]
    if len(vals)<2:return None
    observed=statistics.fmean(vals)
    rng=random.Random(int(seed))
    extreme=0
    for _ in range(int(resamples)):
        simulated=statistics.fmean(v*(1 if rng.random()<0.5 else -1) for v in vals)
        if simulated>=observed:
            extreme+=1
    return (extreme+1)/(int(resamples)+1)

def benjamini_hochberg(pvalues,q=0.05):
    """Return adjusted q-values and reject flags for keyed p-values."""
    valid=[(k,float(v)) for k,v in pvalues.items() if v is not None and math.isfinite(float(v))]
    valid.sort(key=lambda kv:kv[1])
    m=len(valid)
    adjusted={}
    running=1.0
    for rank in range(m,0,-1):
        k,p=valid[rank-1]
        adj=min(running,p*m/rank)
        running=adj
        adjusted[k]=min(1.0,adj)
    return {k:{"p_value":p,"q_value":adjusted[k],"reject":adjusted[k]<=float(q)} for k,p in valid}
