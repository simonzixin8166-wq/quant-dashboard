#!/usr/bin/env python3
"""Historical event study for V5.2 market alert thresholds.

This validates the underlying-market behavior after alert transitions. It does NOT
pretend to backtest option premiums, IV crush, assignment or spread execution.
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf

LEVELS = {
    'watch': {'label':'观察级', 'rank':1},
    'fear': {'label':'大跌级', 'rank':2},
    'panic': {'label':'极端级', 'rank':3},
}

def classify(ixic_ret, spx_ret, vix):
    if (pd.notna(ixic_ret) and ixic_ret <= -0.04) or (pd.notna(spx_ret) and spx_ret <= -0.035) or (pd.notna(vix) and vix >= 35): return 'panic'
    if (pd.notna(ixic_ret) and ixic_ret <= -0.025) or (pd.notna(spx_ret) and spx_ret <= -0.02) or (pd.notna(vix) and vix >= 28): return 'fear'
    if (pd.notna(ixic_ret) and ixic_ret <= -0.015) or (pd.notna(spx_ret) and spx_ret <= -0.0125) or (pd.notna(vix) and vix >= 25): return 'watch'
    return 'normal'

def val(x):
    return None if x is None or (isinstance(x,float) and (math.isnan(x) or math.isinf(x))) else float(x)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--period',default='5y');ap.add_argument('--out',default='docs/research/assistant_rule_validation.json');ap.add_argument('--skip-if-no-new-data',action='store_true');args=ap.parse_args()
    tickers=['^IXIC','^GSPC','^VIX','QQQ']
    raw=yf.download(tickers,period=args.period,auto_adjust=True,progress=False,group_by='column',threads=True)
    if raw.empty: raise SystemExit('No market data returned')
    def close(t):
        if isinstance(raw.columns,pd.MultiIndex): return raw['Close'][t].dropna()
        return raw['Close'].dropna()
    ixic,spx,vix,qqq=[close(t) for t in tickers]
    df=pd.concat({'ixic':ixic,'spx':spx,'vix':vix,'qqq':qqq},axis=1).dropna(subset=['ixic','spx','vix','qqq'])
    df['ixic_ret']=df.ixic.pct_change();df['spx_ret']=df.spx.pct_change();df['level']=[classify(a,b,c) for a,b,c in zip(df.ixic_ret,df.spx_ret,df.vix)]
    as_of=df.index[-1].strftime('%Y-%m-%d');out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    if args.skip_if_no_new_data and out.exists():
        try:
            old=json.loads(out.read_text());
            if old.get('as_of')==as_of:
                print('No new completed market day; skip assistant validation');return
        except Exception: pass
    rank={'normal':0,'watch':1,'fear':2,'panic':3};events=[]
    prev='normal'
    for i,(dt,row) in enumerate(df.iterrows()):
        level=row.level
        # Record only a transition upward into an alert state, matching UI de-noising.
        if level!='normal' and rank[level]>rank.get(prev,0):
            e={'date':dt.strftime('%Y-%m-%d'),'level':level,'ixic_ret':val(row.ixic_ret),'spx_ret':val(row.spx_ret),'vix':val(row.vix),'qqq':val(row.qqq),'forward':{}}
            for h in (5,20,60):
                if i+h<len(df): e['forward'][str(h)]=val(df.qqq.iloc[i+h]/row.qqq-1)
            future=df.qqq.iloc[i+1:min(len(df),i+21)]
            e['mae20']=val(future.min()/row.qqq-1) if len(future) else None
            events.append(e)
        prev=level
    groups=[]
    for level,meta in LEVELS.items():
        es=[e for e in events if e['level']==level]
        fwd={}
        for h in ('5','20','60'):
            vals=[e['forward'].get(h) for e in es if e['forward'].get(h) is not None]
            fwd[h]={'n':len(vals),'avg':val(sum(vals)/len(vals)) if vals else None,'median':val(pd.Series(vals).median()) if vals else None,'positive_rate':val(sum(x>0 for x in vals)/len(vals)) if vals else None}
        maes=[e['mae20'] for e in es if e['mae20'] is not None]
        groups.append({'level':level,'label':meta['label'],'events':len(es),'forward':fwd,'mae20_avg':val(sum(maes)/len(maes)) if maes else None})
    payload={'version':'5.3.0','generated_at':datetime.now(timezone.utc).isoformat(),'as_of':as_of,'period':args.period,'method':'state-transition event study; QQQ forward returns after market alert escalation','groups':groups,'events':events[-80:],'limitations':['This is an underlying-market event study, not an options premium backtest.','No transaction costs, IV changes, assignment or bid/ask spreads are modeled.','Thresholds are research alerts, not automated trading instructions.']}
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    print(f'Wrote {out} with {len(events)} transition events through {as_of}')
if __name__=='__main__': main()
