#!/usr/bin/env python3
"""Bootstrap missing replay dependencies into the local history archive.

Free-first policy:
- Uses yfinance only for missing replay dependencies (VIX, SMH, TQQQ).
- Does not redownload existing multi-year history on every Daily run.
- Writes into the same STOOQ-style local archive so downstream engines reuse one store.
"""
from __future__ import annotations
import io, json, zipfile
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/"data"/"history"/"stooq_watchlist.zip"
TARGETS={
    "VIX":"^VIX",
    "SMH":"SMH",
    "TQQQ":"TQQQ",
}
PERIOD="max"

def symbol_from_member(name):
    base=Path(name).name.lower()
    return base[:-9].upper() if base.endswith("_us_d.csv") else None

def existing_symbols():
    if not ARCHIVE.exists():return set()
    out=set()
    with zipfile.ZipFile(ARCHIVE,"r") as z:
        for name in z.namelist():
            s=symbol_from_member(name)
            if s:out.add(s)
    return out

def normalize(df):
    if df is None or df.empty:return None
    if isinstance(df.columns,pd.MultiIndex):
        df=df.droplevel(1,axis=1) if len(df.columns.levels)>1 else df
    cols={str(c).lower():c for c in df.columns}
    need=["open","high","low","close","volume"]
    if not all(x in cols for x in need):return None
    x=df[[cols[n] for n in need]].copy()
    x.columns=need
    x=x.reset_index()
    x.columns=["date","open","high","low","close","volume"]
    x["date"]=pd.to_datetime(x["date"],errors="coerce").dt.tz_localize(None)
    for c in need:x[c]=pd.to_numeric(x[c],errors="coerce")
    x=x.dropna(subset=["date","open","high","low","close"])
    x=x[(x[["open","high","low","close"]]>0).all(axis=1)]
    x=x.sort_values("date").drop_duplicates("date",keep="last")
    return x

def csv_bytes(df):
    y=df.copy()
    y["date"]=pd.to_datetime(y["date"]).dt.strftime("%Y-%m-%d")
    out=io.StringIO()
    y.columns=["Date","Open","High","Low","Close","Volume"]
    y.to_csv(out,index=False,lineterminator="\n")
    return out.getvalue().encode("utf-8")

def bootstrap():
    have=existing_symbols()
    missing={k:v for k,v in TARGETS.items() if k not in have}
    result={"existing":sorted(have),"requested":sorted(missing),"added":[],"failed":[]}
    if not missing:return result

    downloads={}
    for symbol,ticker in missing.items():
        try:
            raw=yf.download(ticker,period=PERIOD,interval="1d",auto_adjust=False,progress=False,threads=False)
            norm=normalize(raw)
            if norm is None or len(norm)<205:
                result["failed"].append({"symbol":symbol,"reason":"insufficient_history","rows":0 if norm is None else len(norm)})
                continue
            downloads[symbol]=norm
        except Exception as exc:
            result["failed"].append({"symbol":symbol,"reason":str(exc)[:160]})

    if not downloads:return result

    ARCHIVE.parent.mkdir(parents=True,exist_ok=True)
    tmp=ARCHIVE.with_suffix(".bootstrap.tmp.zip")
    with zipfile.ZipFile(tmp,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zout:
        if ARCHIVE.exists():
            with zipfile.ZipFile(ARCHIVE,"r") as zin:
                for name in zin.namelist():
                    if symbol_from_member(name) in downloads:continue
                    zout.writestr(name,zin.read(name))
        for symbol,df in sorted(downloads.items()):
            zout.writestr(f"{symbol.lower()}_us_d.csv",csv_bytes(df))
            result["added"].append({
                "symbol":symbol,
                "rows":len(df),
                "first_date":df["date"].min().date().isoformat(),
                "last_date":df["date"].max().date().isoformat(),
                "source":"Yahoo Finance / yfinance one-time bootstrap",
            })
    tmp.replace(ARCHIVE)
    return result

if __name__=="__main__":
    print(json.dumps(bootstrap(),ensure_ascii=False))
