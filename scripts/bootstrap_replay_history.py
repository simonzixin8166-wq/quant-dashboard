#!/usr/bin/env python3
"""Bootstrap missing replay dependencies into the local history archive.

Free-first policy:
- Uses yfinance only for missing replay dependencies (VIX, SMH, TQQQ).
- Does not redownload existing multi-year history on every Daily run.
- Writes into the same STOOQ-style local archive so downstream engines reuse one store.
"""
from __future__ import annotations
import io, json, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import trading_calendar as tc  # noqa: E402
ARCHIVE=ROOT/"data"/"history"/"stooq_watchlist.zip"
CORRECTIONS=ROOT/"data"/"history"/"corrections.jsonl"
RESTATE_WINDOW=2  # most recent archived sessions a refresh may restate (logged); older differences are never overwritten
TARGETS={
    "VIX":"^VIX",
    "SMH":"SMH",
    "TQQQ":"TQQQ",
}
PERIOD="max"
REFRESH_SYMBOLS={"VIX":"^VIX"}

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

def merge_refresh(existing,recent,expected_session):
    """P0-2 (#133 6183848571): merge a short Yahoo refresh into the archive without unfinished or silent changes.

    - bars for sessions after the latest completed NYSE session are dropped (never an intraday bar as final);
    - a different value for one of the RESTATE_WINDOW most recent archived sessions is applied and returned as a
      revision for data/history/corrections.jsonl (Yahoo restates the latest bars; the old bar may have been
      captured before the session was final);
    - a different value for an older archived session is NOT applied (returned with applied=False);
    - new sessions are appended. Returns (merged, revisions, dropped_dates)."""
    exp=pd.Timestamp(str(expected_session))
    dropped=[d.date().isoformat() for d in recent["date"] if d>exp]
    recent=recent[recent["date"]<=exp]
    ex=existing.set_index("date").sort_index()
    window=set(ex.index[-RESTATE_WINDOW:])
    revisions=[]
    cols=["open","high","low","close","volume"]
    for _,r in recent.iterrows():
        d=r["date"]
        if d in ex.index:
            old=[float(ex.loc[d,c]) for c in cols]; new=[float(r[c]) for c in cols]
            if any(abs(a-b)>1e-6*max(1.0,abs(a)) for a,b in zip(old,new)):
                applied=d in window
                revisions.append({"date":d.date().isoformat(),"old":old,"new":new,"applied":applied})
                if applied:
                    ex.loc[d,cols]=new
        else:
            ex.loc[d,cols]=[float(r[c]) for c in cols]
    merged=ex.sort_index().reset_index()[["date"]+cols]
    return merged,revisions,dropped

def log_corrections(symbol,revisions):
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    with CORRECTIONS.open("a",encoding="utf-8") as f:
        for r in revisions:
            f.write(json.dumps({"applied_at":now,"symbol":symbol,"date":r["date"],"old":r["old"],"new":r["new"],
                                "applied":r["applied"],"source":"Yahoo Finance / yfinance 10d refresh",
                                "reason":("restated recent bar (old bar may predate session finality)" if r["applied"]
                                          else "difference on an older archived session — not applied, logged only")},
                               sort_keys=True)+"\n")

def csv_bytes(df):
    y=df.copy()
    y["date"]=pd.to_datetime(y["date"]).dt.strftime("%Y-%m-%d")
    out=io.StringIO()
    y.columns=["Date","Open","High","Low","Close","Volume"]
    y.to_csv(out,index=False,lineterminator="\n")
    return out.getvalue().encode("utf-8")

def read_member(symbol):
    if not ARCHIVE.exists():return None
    name=f"{symbol.lower()}_us_d.csv"
    try:
        with zipfile.ZipFile(ARCHIVE,"r") as z:
            raw=z.read(name)
        df=pd.read_csv(io.BytesIO(raw))
        df.columns=[str(x).lower() for x in df.columns]
        df["date"]=pd.to_datetime(df["date"],errors="coerce")
        for col in ("open","high","low","close","volume"):
            df[col]=pd.to_numeric(df[col],errors="coerce")
        return df.dropna(subset=["date","open","high","low","close"]).sort_values("date").drop_duplicates("date",keep="last")
    except Exception:
        return None

def bootstrap():
    have=existing_symbols()
    missing={k:v for k,v in TARGETS.items() if k not in have}
    result={"existing":sorted(have),"requested":sorted(missing),"added":[],"refreshed":[],"failed":[]}

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

    # VIX is not part of docs/data.json, so refresh only a short recent window
    # after the one-time bootstrap. SMH/TQQQ continue to receive normal local
    # archive appends from docs/data.json.
    for symbol,ticker in REFRESH_SYMBOLS.items():
        if symbol in missing or symbol not in have:
            continue
        try:
            recent=normalize(yf.download(ticker,period="10d",interval="1d",auto_adjust=False,progress=False,threads=False))
            existing=read_member(symbol)
            if recent is None or recent.empty or existing is None or existing.empty:
                continue
            before=existing["date"].max()
            merged,revisions,dropped=merge_refresh(existing,recent,tc.expected_latest_completed_session())
            if dropped:
                result.setdefault("not_final_dropped",[]).append({"symbol":symbol,"dates":dropped})
            if revisions:
                log_corrections(symbol,[r for r in revisions if r["applied"]])  # older differences: reported here only, never logged daily
                result.setdefault("restated",[]).append({"symbol":symbol,"dates":[r["date"] for r in revisions if r.get("applied")],
                                                        "not_applied":[r["date"] for r in revisions if not r.get("applied")]})
            if merged["date"].max()>before or any(r.get("applied") for r in revisions):
                downloads[symbol]=merged
                result["refreshed"].append({
                    "symbol":symbol,
                    "from":before.date().isoformat(),
                    "to":merged["date"].max().date().isoformat(),
                    "source":"Yahoo Finance / yfinance 10d incremental refresh",
                })
        except Exception as exc:
            result["failed"].append({"symbol":symbol,"reason":"refresh:"+str(exc)[:140]})

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
            if symbol in missing:
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
