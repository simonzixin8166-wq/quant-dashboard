#!/usr/bin/env python3
"""Maintain a bounded market-history cache for external-source validation only.

Core Trend Pulse history remains STOOQ-backed and untouched.
If a symbol appears in Source Intelligence but is absent from the core archive,
this script downloads free daily OHLCV with yfinance into a separate cache:
data/history/source_validation_history.zip

This cache is only used to validate externally sourced research ideas. It never
feeds production Trend Pulse thresholds or automatic trading rules.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "data" / "source_intelligence.json"
CACHE = ROOT / "data" / "history" / "source_validation_history.zip"

import sys
sys.path.insert(0, str(ROOT / "scripts"))
from local_history_agent import read_archive  # noqa: E402

def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def read_cache() -> dict[str, pd.DataFrame]:
    out={}
    if not CACHE.exists():
        return out
    with zipfile.ZipFile(CACHE,"r") as z:
        for name in z.namelist():
            if not name.endswith(".csv"): continue
            sym=Path(name).stem.upper()
            try:
                df=pd.read_csv(io.BytesIO(z.read(name)))
                df.columns=[str(c).strip().lower() for c in df.columns]
                if not {"date","open","high","low","close","volume"}.issubset(df.columns):
                    continue
                df["date"]=pd.to_datetime(df["date"],errors="coerce")
                for c in ["open","high","low","close","volume"]:
                    df[c]=pd.to_numeric(df[c],errors="coerce")
                df=df.dropna(subset=["date","open","high","low","close"])
                df=df.sort_values("date").drop_duplicates("date",keep="last").set_index("date")
                out[sym]=df
            except Exception as exc:
                print("WARNING cache read",sym,exc)
    return out

def write_cache(store: dict[str,pd.DataFrame]):
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    tmp=CACHE.with_suffix(".tmp.zip")
    with zipfile.ZipFile(tmp,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for sym,df in sorted(store.items()):
            x=df.copy().reset_index()
            x.columns=["Date","Open","High","Low","Close","Volume"]
            x["Date"]=pd.to_datetime(x["Date"]).dt.strftime("%Y-%m-%d")
            buf=io.StringIO();x.to_csv(buf,index=False,lineterminator="\n")
            z.writestr(f"{sym}.csv",buf.getvalue())
    tmp.replace(CACHE)

def required_symbols(source: dict) -> dict[str,str]:
    earliest={}
    for rec in source.get("operation_cases") or []:
        day=str(rec.get("published_at") or "")[:10]
        if not day: continue
        for op in rec.get("operations") or []:
            if op.get("attribution")=="third_party_example":
                continue
            for sym in op.get("symbols") or rec.get("symbols") or []:
                if sym and (sym not in earliest or day < earliest[sym]):
                    earliest[sym]=day
    return earliest

def normalize_yf(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    df=raw.copy()
    if isinstance(df.columns,pd.MultiIndex):
        # yf.download may return either (field,ticker) or (ticker,field).
        try:
            if symbol in df.columns.get_level_values(-1):
                df=df.xs(symbol,axis=1,level=-1,drop_level=True)
            elif symbol in df.columns.get_level_values(0):
                df=df.xs(symbol,axis=1,level=0,drop_level=True)
        except Exception:
            pass
    df.columns=[str(c).strip().lower().replace(" ","_") for c in df.columns]
    if "adj_close" in df.columns and "close" not in df.columns:
        df["close"]=df["adj_close"]
    need=["open","high","low","close"]
    if not all(c in df.columns for c in need):
        return pd.DataFrame()
    if "volume" not in df.columns: df["volume"]=0
    df=df[["open","high","low","close","volume"]].copy()
    df.index=pd.to_datetime(df.index).tz_localize(None)
    for c in df.columns: df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.dropna(subset=need)
    df=df[(df[need]>0).all(axis=1)]
    return df.sort_index().drop_duplicates()

def fetch_symbol(symbol: str, start: str) -> pd.DataFrame:
    start_ts=pd.Timestamp(start)-pd.Timedelta(days=45)
    end_ts=pd.Timestamp(datetime.now(timezone.utc).date())+pd.Timedelta(days=2)
    raw=yf.download(
        symbol,
        start=start_ts.date().isoformat(),
        end=end_ts.date().isoformat(),
        auto_adjust=False,
        progress=False,
        threads=False,
        actions=False,
    )
    return normalize_yf(raw,symbol)

def main():
    source=load(SOURCE,{})
    required=required_symbols(source)
    core=read_archive()
    cache=read_cache()
    result={"required":len(required),"core":0,"cached":0,"downloaded":[],"failed":[]}
    changed=False
    for sym,start in sorted(required.items()):
        if sym in core:
            result["core"]+=1; continue
        old=cache.get(sym)
        # Refresh if missing or does not reach the latest recent trading window.
        stale=old is None or old.empty or (pd.Timestamp(datetime.now().date())-old.index.max()).days>7
        if not stale:
            result["cached"]+=1; continue
        try:
            df=fetch_symbol(sym,start)
            if df.empty:
                result["failed"].append({"symbol":sym,"reason":"empty"})
                continue
            # Keep only the bounded range needed for research validation.
            lower=pd.Timestamp(start)-pd.Timedelta(days=45)
            df=df[df.index>=lower]
            cache[sym]=df
            result["downloaded"].append({"symbol":sym,"rows":len(df),"from":df.index.min().date().isoformat(),"to":df.index.max().date().isoformat()})
            changed=True
        except Exception as exc:
            result["failed"].append({"symbol":sym,"reason":str(exc)[:160]})
    if changed:
        write_cache(cache)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if not result["failed"] else 0

if __name__=="__main__":
    raise SystemExit(main())
