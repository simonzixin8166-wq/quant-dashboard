#!/usr/bin/env python3
"""Continuous Source Coverage Audit v1.0.

Research-quality audit for the external-source layer. It detects silent source
dropouts and provenance-quality regressions without changing trading rules,
Promotion, positions, or orders.

The audit operates on the recent Source Intelligence presentation window, which
is sufficient for continuity checks because records are newest-first.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"docs"/"data"/"source_intelligence.json"
OUT=ROOT/"docs"/"research"/"source_coverage_audit.json"
STORE=ROOT/"research"/"store"/"source_store.json"
# SRC-01 (wxc-bot #67): publication dates found after a YouTube row was admitted without one (append-only).
YT_DATES_URL="https://raw.githubusercontent.com/simonzixin8166-wq/wxc-bot/main/state/youtube_published_dates.jsonl"
VERSION="1.0"

EXPECTED_WXC_AUTHORS=("BrightLine","yifan99","三心三意","我是一只井底蛙","bogbog")
EXPECTED_CHANNELS=("wenxuecity","youtube")
RECENT_DAYS=30
HOT_DAYS=7

def load(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def parse_day(value):
    try:
        ts=pd.Timestamp(str(value or ""))
        if pd.isna(ts):return None
        return ts.date()
    except Exception:return None

def store_records(store):
    """Full canonical stream (SRC-02): every stored source with its own published_at and first_fetched_at."""
    out=[]
    for x in (store or {}).get("records") or []:
        if not isinstance(x,dict) or not isinstance(x.get("record"),dict):continue
        r=dict(x["record"])
        r["published_at"]=x.get("published_at") or r.get("published_at") or ""
        r["_captured_at"]=x.get("first_fetched_at") or r.get("captured_at") or ""
        r["_online"]=x.get("source_still_online") is not False
        out.append(r)
    return out

def fetch_resolved_dates(url=YT_DATES_URL, timeout=15):
    """video_id -> resolved published_at, plus a status. Fail-soft: unavailable never breaks the audit."""
    import urllib.request
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"MyAlphaView-SourceCoverage/1.0"})
        with urllib.request.urlopen(req,timeout=timeout) as resp:
            text=resp.read().decode("utf-8")
    except Exception as exc:
        return {},f"unavailable:{type(exc).__name__}"
    out={}
    for line in text.splitlines():
        try:
            x=json.loads(line)
        except ValueError:
            continue
        if x.get("video_id") and x.get("published_at"):
            out.setdefault(str(x["video_id"]),str(x["published_at"]))
    return out,"ok"

def _video_id(row):
    m=re.search(r"[?&]v=([A-Za-z0-9_-]{11})",str(row.get("url") or ""))
    return m.group(1) if m else ""

def quality_label(value):
    """SRC-03: None means the collector never grades this source (forum/blog), not 'low quality'."""
    if value is None or str(value).strip()=="":
        return "NOT_ASSESSED"
    return str(value).upper()

def build(source, store=None, resolved_dates=None, resolved_status="not_requested"):
    """Coverage over the full canonical store when available; otherwise over the 800-row presentation window.
    The window alone hides undated records (they sort last), which made YouTube look absent (#133 6391860281)."""
    full=store_records(store) if store else []
    resolved_dates=resolved_dates or {}
    resolved_used=0
    for r in full:
        if parse_day(r.get("published_at")) is None and str(r.get("source") or "").lower()=="youtube":
            d=resolved_dates.get(_video_id(r))
            if d and parse_day(d) is not None:
                # coverage only: the row keeps its timestamp-unknown backfill class and stays non-forward
                r["published_at"]=d
                r["_date_resolved_after_admission"]=True
                resolved_used+=1
    window_rows=list(source.get("records") or [])
    rows=full or window_rows
    generated=pd.Timestamp(source.get("generated_at") or datetime.now(timezone.utc))
    if generated.tzinfo is None:generated=generated.tz_localize("UTC")
    ref_day=generated.tz_convert("UTC").date()

    def age_days(row):
        day=parse_day(row.get("published_at"))
        return None if day is None else (ref_day-day).days

    by_author=defaultdict(list);by_channel=defaultdict(list)
    role_counts=Counter();quality_counts=Counter()
    parseable=0
    multi=0;ambiguous_multi=0
    for r in rows:
        author=str(r.get("author") or "unknown")
        source_name=str(r.get("source") or "unknown").lower()
        by_author[author].append(r);by_channel[source_name].append(r)
        if parse_day(r.get("published_at")) is not None:parseable+=1
        quality_counts[quality_label(r.get("content_quality"))]+=1
        for a in r.get("symbol_attribution") or []:
            role_counts[str(a.get("role") or "unknown")]+=1
        syms=r.get("symbols") or []
        if len(syms)>1:
            multi+=1
            if not (r.get("primary_symbols") or []):ambiguous_multi+=1

    def window_count(items,days):
        out=0
        for r in items:
            age=age_days(r)
            if age is not None and 0<=age<=days:out+=1
        return out

    def captured_undated(items,days):
        out=0
        for r in items:
            if parse_day(r.get("published_at")) is not None:continue
            cap=parse_day(r.get("_captured_at"))
            if cap is not None and 0<=(ref_day-cap).days<=days:out+=1
        return out

    def latest_day(items):
        days=[parse_day(r.get("published_at")) for r in items]
        days=[d for d in days if d is not None]
        return max(days).isoformat() if days else None

    authors=[]
    missing_authors=[]
    for author in EXPECTED_WXC_AUTHORS:
        items=[r for r in by_author.get(author,[]) if str(r.get("source") or "").lower()=="wenxuecity"]
        row={
            "author":author,
            "records_in_window":len(items),
            "recent_7d":window_count(items,HOT_DAYS),
            "recent_30d":window_count(items,RECENT_DAYS),
            "latest_published_at":latest_day(items),
        }
        row["coverage_state"]="active_recent" if row["recent_30d"]>0 else ("present_stale" if items else "missing")
        if row["coverage_state"] in {"present_stale","missing"}:missing_authors.append(author)
        authors.append(row)

    channels=[]
    missing_channels=[]
    undated_channels=[]
    for channel in EXPECTED_CHANNELS:
        items=by_channel.get(channel,[])
        row={
            "source":channel,
            "records_in_window":len(items),
            "recent_7d":window_count(items,HOT_DAYS),
            "recent_30d":window_count(items,RECENT_DAYS),
            "latest_published_at":latest_day(items),
            "undated_records":sum(1 for r in items if parse_day(r.get("published_at")) is None),
            "undated_captured_30d":captured_undated(items,RECENT_DAYS),
        }
        if row["undated_captured_30d"]>0:
            # records keep arriving without a reproducible publication date: learning-only, never forward-usable
            undated_channels.append(channel)
        if row["recent_30d"]>0:
            row["coverage_state"]="active_recent"
        elif row["undated_captured_30d"]>0:
            row["coverage_state"]="active_undated"
        else:
            row["coverage_state"]="present_stale" if items else "missing"
        if row["coverage_state"] in {"present_stale","missing"}:missing_channels.append(channel)
        channels.append(row)

    timestamp_ratio=parseable/len(rows) if rows else 0.0
    ambiguity_ratio=ambiguous_multi/multi if multi else 0.0
    # This is an observability/continuity audit, not a decision gate. A missing
    # expected author/channel is attention-worthy but never mutates Production.
    state="operational" if not missing_authors and not missing_channels else "attention"
    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "reference_date":ref_day.isoformat(),
        "state":state,
        "window":{
            "records_examined":len(rows),
            "basis":"full_canonical_store" if full else "presentation_window",
            "presentation_window_records":len(window_rows),
            "source_intelligence_total_records":int((source.get("counts") or {}).get("records") or len(rows)),
            "undated_records":sum(1 for r in rows if parse_day(r.get("published_at")) is None),
            "dates_resolved_after_admission":resolved_used,
            "resolved_dates_source":resolved_status,
            "presentation_window_is_recent_newest_first":True,
        },
        "expected_coverage":{
            "wenxuecity_authors":authors,
            "channels":channels,
            "missing_or_stale_authors":missing_authors,
            "missing_or_stale_channels":missing_channels,
            "active_undated_channels":undated_channels,
        },
        "quality":{
            "published_timestamp_parseable_ratio":timestamp_ratio,
            "content_quality_counts":dict(sorted(quality_counts.items())),
            "content_quality_note":"NOT_ASSESSED = the collector does not grade this source (forum/blog); it is not a low-quality verdict",
            "text_depth":(source.get("feed_integrity") or {}).get("text_depth"),
            "symbol_role_counts":dict(sorted(role_counts.items())),
            "multi_symbol_records":multi,
            "ambiguous_multi_symbol_records":ambiguous_multi,
            "ambiguous_multi_symbol_ratio":ambiguity_ratio,
        },
        "alerts":[
            *[{"kind":"author_coverage","subject":x,"severity":"P1","message":"Expected Wenxuecity author has no source record within 30 days."} for x in missing_authors],
            *[{"kind":"channel_coverage","subject":x,"severity":"P1","message":"Expected source channel has no source record within 30 days."} for x in missing_channels],
            *[{"kind":"channel_publication_dates","subject":x,"severity":"P2","message":"Records captured within 30 days but without a reproducible publication date (learning-only, non-forward)."} for x in undated_channels],
        ],
        "production_effect":"none",
        "promotion_effect":"none",
        "guardrails":[
            "Coverage audit is observational Research/QA only.",
            "A quiet author is not treated as a collector failure by itself; the audit only raises an attention signal for review.",
            "No missing-source alert may create, suppress or alter an investment Action.",
            "No historical/backfill record is upgraded to Forward evidence by this audit.",
            "The audit never changes protected rules, positions, sizing, Promotion, or orders.",
        ],
    }

def main():
    dates,status=fetch_resolved_dates()
    out=build(load(SRC,{}),load(STORE,{}),dates,status)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"state":out["state"],"alerts":len(out["alerts"]),"window":out["window"]},ensure_ascii=False))

if __name__=="__main__":main()
