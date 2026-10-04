#!/usr/bin/env python3
"""Dependence clustering for Evidence Foundation.

A time cluster is the connected component of overlapping realized evaluation
windows [baseline_date, horizon_end_date]. This avoids the boundary problem of
fixed calendar buckets: two windows that share any dates can never count as
independent time clusters merely because they straddle a bucket boundary.
"""
from __future__ import annotations
from datetime import date

VERSION="6.15.8e"

def _date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None

def event_interval(event,horizon):
    score=(event.get("scores") or {}).get(str(horizon)) or {}
    start=_date(event.get("baseline_date"))
    end=_date(score.get("horizon_end_date") or score.get("date"))
    if not start or not end or end < start:
        return None
    return start,end

def overlap_connected_clusters(events,horizon,require_lift=False):
    """Return event->cluster mapping and pairwise non-overlapping cluster metadata.

    Intervals form one cluster when they overlap directly or transitively.
    Therefore distinct returned clusters are guaranteed not to share dates.
    """
    rows=[]
    for e in events:
        score=(e.get("scores") or {}).get(str(horizon))
        if not score:
            continue
        if require_lift and score.get("unconditional_lift") is None:
            continue
        interval=event_interval(e,horizon)
        if not interval:
            continue
        start,end=interval
        rows.append((start,end,str(e.get("event_id") or ""),e))
    rows.sort(key=lambda x:(x[0],x[1],x[2]))

    clusters=[]
    assignments={}
    current=None
    for start,end,eid,e in rows:
        if current is None or start > current["end"]:
            current={
                "cluster_index":len(clusters),
                "start":start,
                "end":end,
                "event_ids":[],
            }
            clusters.append(current)
        else:
            if end > current["end"]:
                current["end"]=end
        current["event_ids"].append(eid)
        assignments[eid]=current["cluster_index"]

    meta=[]
    for c in clusters:
        meta.append({
            "cluster_index":c["cluster_index"],
            "cluster_id":f"h{horizon}-c{c['cluster_index']:04d}",
            "start":c["start"].isoformat(),
            "end":c["end"].isoformat(),
            "events":len(c["event_ids"]),
        })
    return assignments,meta

def assert_non_overlapping(cluster_meta):
    prev_end=None
    for c in sorted(cluster_meta,key=lambda x:x["start"]):
        start=_date(c.get("start"));end=_date(c.get("end"))
        if not start or not end:return False
        if prev_end is not None and start <= prev_end:return False
        prev_end=end
    return True
