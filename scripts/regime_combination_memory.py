#!/usr/bin/env python3
"""MyAlpha V6.8 Cross-Asset + Breadth Regime Combination Memory.

Persists joint market states so the Agent can learn whether a particular
combination (for example high cross-asset pressure + fragile breadth) historically
resolved through drawdown, sideways digestion, or breadth repair.

Research memory only. No automatic position or order changes.
"""
from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"docs/data.json"
CROSS=ROOT/"docs/research/cross_asset_divergence.json"
BREADTH=ROOT/"docs/research/breadth_intelligence.json"
OUT=ROOT/"docs/research/regime_combination_memory.json"
HISTORY=ROOT/"docs/research/regime_combination_history.json"

def load(p):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {}

def num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def mature_history(history,dash):
    rows=list(history.get("records") or [])
    chart=((dash.get("overview_charts") or {}).get("SPY") or [])
    prices={str(x.get("d")):num(x.get("c")) for x in chart if x.get("d")}
    dates=[str(x.get("d")) for x in chart if x.get("d") and num(x.get("c")) is not None]
    idx={d:i for i,d in enumerate(dates)}
    for row in rows:
        d=str(row.get("as_of") or "")
        if d not in idx: continue
        anchor=num(row.get("anchor_spy"))
        if anchor is None: continue
        i=idx[d]; outcomes=row.setdefault("outcomes",{})
        for h in (5,20,60):
            j=i+h
            if str(h) not in outcomes and j<len(dates):
                px=prices.get(dates[j])
                path_px=[prices.get(dates[k]) for k in range(i+1,j+1)]
                path_px=[v for v in path_px if v is not None]
                if px is not None and path_px:
                    outcomes[str(h)]={
                      "date":dates[j],"return":px/anchor-1,
                      "mae":min(path_px)/anchor-1,"mfe":max(path_px)/anchor-1
                    }
    return {"version":"6.8.0","records":rows[-360:]}

def build(dash,cross,breadth,history=None):
    cross_level=str(cross.get("level") or "unknown")
    breadth_level=str(breadth.get("level") or "unknown")
    vix=num(((dash.get("market_indicators") or {}).get("vix") or {}).get("close"))
    if vix is None:
        vix_zone="unknown"
    elif vix<15:vix_zone="calm"
    elif vix<20:vix_zone="low"
    elif vix<25:vix_zone="alert"
    else:vix_zone="stress"
    state_id=f"CROSS_{cross_level.upper()}|BREADTH_{breadth_level.upper()}|VIX_{vix_zone.upper()}"

    severe = cross_level=="high" and breadth_level=="fragile"
    elevated = severe or cross_level in {"high","medium"} or breadth_level in {"fragile","weakening"}
    if severe:
        level,label="high","跨资产压力 + 宽度脆弱共振"
    elif elevated:
        level,label="medium","风险环境存在组合分化"
    else:
        level,label="low","组合环境未见明显共振"

    matched=[]
    for row in (history or {}).get("records") or []:
        if row.get("state_id")!=state_id: continue
        matched.append(row)
    mature={}
    for h in ("5","20","60"):
        vals=[((r.get("outcomes") or {}).get(h) or {}).get("return") for r in matched]
        vals=[v for v in vals if isinstance(v,(int,float))]
        if vals:
            mature[h]={
              "n":len(vals),"avg_return":sum(vals)/len(vals),
              "positive_rate":sum(1 for v in vals if v>0)/len(vals),
              "worst_return":min(vals),"best_return":max(vals)
            }
        else:mature[h]={"n":0}

    return {
      "version":"6.8.0","generated_at":datetime.now(timezone.utc).isoformat(),
      "as_of":dash.get("spy_date") or breadth.get("as_of") or cross.get("as_of"),
      "level":level,"label":label,"state_id":state_id,
      "cross_asset":{"level":cross_level,"label":cross.get("label"),"risk_hits":cross.get("risk_hits")},
      "breadth":{"level":breadth_level,"label":breadth.get("label"),"participation_score":breadth.get("participation_score"),"combination_key":breadth.get("combination_key")},
      "vix":{"value":vix,"zone":vix_zone},
      "historical_matches":{"total":len(matched),"mature":mature},
      "interpretation":[
        "组合记忆只比较同类环境，不把单一指标历史结果外推成确定预测。",
        "高跨资产压力与脆弱宽度同时出现时，提高验证优先级，重点观察信用、利率与参与度是否继续共振。",
        "如果宽度快速修复或利率/信用压力消退，组合状态可降级而不需要价格先大跌。"
      ],
      "next_validation":[
        "Breadth Intelligence 是否从 fragile/weakening 向 mixed/healthy 修复",
        "Cross-Asset Divergence 是否从 high/medium 降级",
        "VIX 是否由低波动补涨进入风险确认，或继续保持背离",
        "相同组合状态的20/60日成熟样本是否形成稳定模式"
      ],
      "guardrail":"Regime Combination Memory 只影响研究优先级与情境解释，不自动调整仓位、杠杆或下单。"
    }

def main():
    dash=load(DATA); cross=load(CROSS); breadth=load(BREADTH)
    history=mature_history(load(HISTORY),dash)
    out=build(dash,cross,breadth,history)
    as_of=str(out.get("as_of") or "")[:10]
    anchor=num(((dash.get("index") or {}).get("SPY") or {}).get("close"))
    if as_of and anchor is not None:
        records=history.get("records") or []
        snap={
          "as_of":as_of,"anchor_spy":anchor,"state_id":out["state_id"],"level":out["level"],"label":out["label"],
          "cross_asset":out["cross_asset"],"breadth":out["breadth"],"vix":out["vix"],"outcomes":{}
        }
        old=next((x for x in records if x.get("as_of")==as_of),None)
        if old:
            snap["outcomes"]=old.get("outcomes") or {}
            records[records.index(old)]=snap
        else: records.append(snap)
        history["records"]=records[-360:]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    HISTORY.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"state_id":out["state_id"],"level":out["level"],"history":len(history.get("records") or [])},ensure_ascii=False))

if __name__=="__main__":main()
