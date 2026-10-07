#!/usr/bin/env python3
"""MyAlpha Support & Volatility Intelligence.

Research-only evidence engine for the focused opportunity universe.
It converts price/volume history into:
- adaptive Volume Profile support/resistance across 90D/1Y/2Y/3Y windows;
- realized volatility (20D/60D);
- GARCH(1,1) 20-session volatility forecast when the optional arch package is available.

This engine never emits trade actions and never changes Production Rules.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"research"/"support_volatility_intelligence.json"
DEFAULT_UNIVERSE=["QQQ","SOFI","LITE","IREN","NVDA","TSLA"]
WINDOWS=((90,"90D"),(252,"1Y"),(504,"2Y"),(756,"3Y"))


def adaptive_bin_size(price: float) -> float:
    """About 1% of spot, snapped to a human-readable price interval."""
    if not np.isfinite(price) or price<=0:
        return 1.0
    raw=price*0.01
    steps=(0.05,0.10,0.25,0.50,1.0,2.0,5.0,10.0,20.0)
    return min(steps,key=lambda x:abs(x-raw))


def compute_volume_profile(df: pd.DataFrame, bin_size: float, lookback_days: int) -> pd.DataFrame:
    data=df.tail(lookback_days).copy()
    if data.empty:
        return pd.DataFrame(columns=["bin_low","bin_high","volume","strength"])
    lo=float(data["Low"].min()); hi=float(data["High"].max())
    start=math.floor(lo/bin_size)*bin_size
    stop=math.ceil(hi/bin_size)*bin_size+bin_size
    bins=np.arange(start,stop,bin_size,dtype=float)
    if len(bins)<2:
        bins=np.array([start,start+bin_size],dtype=float)
    vol=np.zeros(len(bins)-1,dtype=float)
    for row in data.itertuples(index=False):
        day_lo=float(row.Low); day_hi=float(row.High); day_vol=float(row.Volume)
        if not np.isfinite(day_vol) or day_vol<=0:
            continue
        if day_hi<=day_lo:
            idx=int(np.clip(np.searchsorted(bins,float(row.Close),side="right")-1,0,len(vol)-1))
            vol[idx]+=day_vol
            continue
        left=np.maximum(bins[:-1],day_lo)
        right=np.minimum(bins[1:],day_hi)
        overlap=np.maximum(0.0,right-left)
        vol+=day_vol*(overlap/(day_hi-day_lo))
    out=pd.DataFrame({"bin_low":bins[:-1],"bin_high":bins[1:],"volume":vol})
    rank=out["volume"].rank(pct=True,method="average")
    out["strength"]=np.select(
        [rank>=.90,rank>=.75,rank>=.50],
        ["超强","强","中"],
        default="小",
    )
    return out


def merge_adjacent(profile: pd.DataFrame) -> pd.DataFrame:
    if profile.empty:
        return pd.DataFrame(columns=["low","high","volume","strength"])
    rows=profile.sort_values("bin_low").to_dict("records")
    merged=[]; cur=None
    for r in rows:
        if cur is None:
            cur={"low":float(r["bin_low"]),"high":float(r["bin_high"]),"volume":float(r["volume"]),"strength":r["strength"]}
        elif r["strength"]==cur["strength"] and abs(float(r["bin_low"])-cur["high"])<1e-9:
            cur["high"]=float(r["bin_high"]); cur["volume"]+=float(r["volume"])
        else:
            merged.append(cur); cur={"low":float(r["bin_low"]),"high":float(r["bin_high"]),"volume":float(r["volume"]),"strength":r["strength"]}
    if cur is not None: merged.append(cur)
    return pd.DataFrame(merged)


def split_at_price(levels: pd.DataFrame, current: float) -> pd.DataFrame:
    rows=[]
    for r in levels.to_dict("records"):
        lo=float(r["low"]); hi=float(r["high"]); vol=float(r["volume"])
        if lo<current<hi and hi>lo:
            frac=(current-lo)/(hi-lo)
            rows.append({**r,"low":lo,"high":current,"volume":vol*frac})
            rows.append({**r,"low":current,"high":hi,"volume":vol*(1-frac)})
        else:
            rows.append(r)
    return pd.DataFrame(rows)


def support_snapshot(df: pd.DataFrame) -> dict:
    current=float(df["Close"].iloc[-1])
    bin_size=adaptive_bin_size(current)
    windows=[]
    all_support=[]; all_resistance=[]
    for lookback,label in WINDOWS:
        if len(df)<min(60,lookback):
            continue
        profile=compute_volume_profile(df,bin_size,min(lookback,len(df)))
        levels=split_at_price(merge_adjacent(profile),current)
        levels=levels[levels["strength"].isin(["中","强","超强"])].copy()
        supports=levels[levels["high"]<=current].sort_values("high",ascending=False)
        resistance=levels[levels["low"]>=current].sort_values("low",ascending=True)
        def pack(row):
            return {
                "low":round(float(row["low"]),4),
                "high":round(float(row["high"]),4),
                "strength":str(row["strength"]),
                "distance_pct":round(((float(row["high"] if row["high"]<=current else row["low"])/current)-1)*100,2),
            }
        s=[pack(r) for _,r in supports.head(5).iterrows()]
        rr=[pack(r) for _,r in resistance.head(5).iterrows()]
        for x in s: all_support.append({**x,"window":label})
        for x in rr: all_resistance.append({**x,"window":label})
        windows.append({"window":label,"lookback":min(lookback,len(df)),"support":s,"resistance":rr})
    nearest_support=min(all_support,key=lambda x:abs(x["distance_pct"])) if all_support else None
    nearest_resistance=min(all_resistance,key=lambda x:abs(x["distance_pct"])) if all_resistance else None
    return {
        "current_price":round(current,4),
        "adaptive_bin_size":bin_size,
        "windows":windows,
        "nearest_support":nearest_support,
        "nearest_resistance":nearest_resistance,
    }


def realized_volatility(df: pd.DataFrame) -> dict:
    ret=np.log(df["Close"]/df["Close"].shift(1)).dropna()
    def rv(n):
        x=ret.tail(n)
        return round(float(x.std(ddof=1)*np.sqrt(252)*100),2) if len(x)>=max(10,n//2) else None
    return {"rv20_ann_pct":rv(20),"rv60_ann_pct":rv(60)}


def garch_forecast(df: pd.DataFrame, horizon: int=20) -> dict:
    ret=(100*np.log(df["Close"]/df["Close"].shift(1))).dropna()
    if len(ret)<120:
        return {"status":"insufficient_history","horizon":horizon}
    try:
        from arch import arch_model
        model=arch_model(ret,vol="GARCH",p=1,q=1,mean="Constant",rescale=False)
        fitted=model.fit(update_freq=0,disp="off",show_warning=False)
        forecast=fitted.forecast(horizon=horizon,reindex=False)
        var=np.asarray(forecast.variance.iloc[-1],dtype=float)
        ann=np.sqrt(var)*np.sqrt(252)
        return {
            "status":"ok",
            "horizon":horizon,
            "ann_vol_pct_avg":round(float(np.mean(ann)),2),
            "ann_vol_pct_day1":round(float(ann[0]),2),
            "ann_vol_pct_day20":round(float(ann[-1]),2),
            "omega":round(float(fitted.params.get("omega",np.nan)),8),
            "alpha1":round(float(fitted.params.get("alpha[1]",np.nan)),8),
            "beta1":round(float(fitted.params.get("beta[1]",np.nan)),8),
        }
    except ImportError:
        return {"status":"arch_dependency_unavailable","horizon":horizon}
    except Exception as exc:
        return {"status":"model_failed","horizon":horizon,"error":type(exc).__name__}


def fetch_history(symbol: str, period: str="3y") -> pd.DataFrame:
    import yfinance as yf
    frame=yf.download(symbol,period=period,interval="1d",auto_adjust=False,progress=False,threads=False)
    if frame is None or frame.empty:
        raise RuntimeError("no_history")
    if isinstance(frame.columns,pd.MultiIndex):
        frame.columns=[c[0] for c in frame.columns]
    need=["Open","High","Low","Close","Volume"]
    frame=frame[need].dropna(subset=["High","Low","Close"]).copy()
    frame["Volume"]=pd.to_numeric(frame["Volume"],errors="coerce").fillna(0)
    return frame


def build(universe=None, fetcher=fetch_history, now=None) -> dict:
    universe=list(universe or DEFAULT_UNIVERSE)
    now=now or datetime.now(timezone.utc)
    rows={}
    for symbol in universe:
        try:
            df=fetcher(symbol)
            rows[symbol]={
                "status":"ok",
                "as_of":str(pd.Timestamp(df.index[-1]).date()),
                "history_rows":int(len(df)),
                "support_resistance":support_snapshot(df),
                "volatility":{
                    **realized_volatility(df),
                    "garch20":garch_forecast(df,20),
                },
                "decision_effect":"research_only",
                "trade_action":None,
            }
        except Exception as exc:
            rows[symbol]={
                "status":"unavailable",
                "error":type(exc).__name__,
                "decision_effect":"fail_closed",
                "trade_action":None,
            }
    return {
        "version":"support-volatility-intelligence-1",
        "generated_at":now.isoformat(),
        "universe":universe,
        "methodology":{
            "support":"Volume Profile; adaptive bin approximately 1% of spot; 90D/1Y/2Y/3Y windows",
            "volatility":"20D/60D realized volatility plus GARCH(1,1) 20-session forecast",
            "guardrail":"Research evidence only. No automatic entry, sizing, Production Rule mutation, or order.",
        },
        "records":rows,
    }


def main():
    universe=[x.strip().upper() for x in os.getenv("MAV_OPTION_UNIVERSE",",".join(DEFAULT_UNIVERSE)).split(",") if x.strip()]
    out=build(universe)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    ok=sum(1 for x in out["records"].values() if x.get("status")=="ok")
    print(json.dumps({"universe":len(universe),"ok":ok,"output":str(OUT.relative_to(ROOT))},ensure_ascii=False))


if __name__=="__main__":
    main()
