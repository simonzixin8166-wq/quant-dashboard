#!/usr/bin/env python3
"""MyAlpha V6.7 Cross-Asset Divergence Engine.

Detects when headline equity indexes remain strong while discount-rate,
bond-volatility, credit or breadth conditions deteriorate.

Research-only: no orders, no production rule mutation.
"""
from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DASH=ROOT/"docs/data.json"
MACRO=ROOT/"docs/research/macro_context.json"
OUT=ROOT/"docs/research/cross_asset_divergence.json"\nHISTORY=ROOT/"docs/research/cross_asset_divergence_history.json"

def load(p):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {}

def num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def series(macro,key):
    x=(macro.get("series") or {}).get(key) or {}
    return {
      "latest": num(((x.get("latest") or {}).get("value"))),
      "date": ((x.get("latest") or {}).get("date")),
      "chg3": num((x.get("changes") or {}).get("3")),
      "chg20": num((x.get("changes") or {}).get("20")),
      "chg60": num((x.get("changes") or {}).get("60")),
    }

def mature_history(history,dash):
    rows=list(history.get("records") or [])
    chart=((dash.get("overview_charts") or {}).get("SPY") or [])
    prices={str(x.get("d")):num(x.get("c")) for x in chart if x.get("d")}
    dates=[str(x.get("d")) for x in chart if x.get("d") and num(x.get("c")) is not None]
    idx={d:i for i,d in enumerate(dates)}
    for row in rows:
        d=str(row.get("as_of") or "")
        if d not in idx: continue
        i=idx[d]; anchor=num(row.get("anchor_spy"))
        if anchor is None: continue
        outcomes=row.setdefault("outcomes",{})
        for h in (5,20,60):
            j=i+h
            if str(h) not in outcomes and j<len(dates):
                px=prices.get(dates[j])
                if px is not None:
                    outcomes[str(h)]={"date":dates[j],"return":px/anchor-1}
    return {"version":"6.7.0","records":rows[-240:]}

def build(dash,macro):
    mkt=dash.get("market_regime") or {}
    dd=num(mkt.get("dist_52w_high"))
    breadth=mkt.get("conditions") or []
    b={x.get("key"):x for x in breadth}
    d10=series(macro,"DGS10")
    real10=series(macro,"DFII10")
    hy=series(macro,"BAMLH0A0HYM2")
    vix=series(macro,"VIXCLS")
    nfci=series(macro,"NFCI")

    signals=[]
    def add(key,label,hit,severity,value,reason):
        signals.append({"key":key,"label":label,"hit":bool(hit),"severity":severity,"value":value,"reason":reason})

    equity_near_high = dd is not None and dd >= -0.03
    add("equity_near_high","指数接近高位",equity_near_high,"context",dd,
        f"距52周高点 {dd:.1%}" if dd is not None else "缺少高点距离")

    add("rates_pressure","10年期美债收益率压力",
        d10["latest"] is not None and d10["latest"]>=4.75 and (d10["chg20"] or 0)>0,
        "high",d10,
        f"10Y={d10['latest']}，20日变化={d10['chg20']}" if d10["latest"] is not None else "缺失")
    add("real_yield_pressure","实际利率压力",
        real10["latest"] is not None and real10["latest"]>=2.25 and (real10["chg20"] or 0)>0,
        "high",real10,
        f"10Y real={real10['latest']}，20日变化={real10['chg20']}" if real10["latest"] is not None else "缺失")
    add("credit_widening","高收益信用利差走阔",
        hy["latest"] is not None and (hy["chg20"] or 0)>=0.25,
        "medium",hy,
        f"HY OAS={hy['latest']}，20日变化={hy['chg20']}" if hy["latest"] is not None else "缺失")
    add("vix_disconnect","VIX未同步确认风险",
        vix["latest"] is not None and vix["latest"]<20,
        "context",vix,
        f"VIX={vix['latest']}：股票波动仍低，不足以否定债券/信用压力" if vix["latest"] is not None else "缺失")

    w20=num((b.get("20天宽度") or {}).get("val"))
    w50=num((b.get("50天宽度") or {}).get("val"))
    w200=num((b.get("200天宽度") or {}).get("val"))
    breadth_weak = ((w20 is not None and w20<0.35) or (w50 is not None and w50<0.35) or (w200 is not None and w200<0.50))
    add("breadth_divergence","市场宽度弱于指数",
        equity_near_high and breadth_weak,
        "high",{"w20":w20,"w50":w50,"w200":w200},
        f"20/50/200日宽度={w20},{w50},{w200}")

    add("financial_conditions_cushion","金融条件仍有缓冲",
        nfci["latest"] is not None and nfci["latest"]<=-0.25,
        "offset",nfci,
        f"NFCI={nfci['latest']}，尚未进入系统性紧缩")

    risk_hits=sum(1 for x in signals if x["hit"] and x["severity"] in {"high","medium"})
    high_hits=sum(1 for x in signals if x["hit"] and x["severity"]=="high")
    if equity_near_high and high_hits>=3:
        level="high"
        label="高位跨资产背离"
    elif equity_near_high and risk_hits>=2:
        level="medium"
        label="中度跨资产背离"
    else:
        level="low"
        label="跨资产背离有限"

    thesis=[
      "股指价格趋势仍强，但折现率上升会压缩估值容忍度。",
      "若信用利差与债券波动继续上升，而指数仍由少数大盘股支撑，脆弱性会增加。",
      "若收益率回落、信用利差重新收窄且市场宽度改善，当前背离可通过基本面/流动性消化。",
    ]
    return {
      "version":"6.7.0",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "as_of":dash.get("updated"),
      "level":level,"label":label,
      "risk_hits":risk_hits,"high_hits":high_hits,
      "signals":signals,
      "thesis":thesis,
      "unknowns":[
        "MOVE 尚未进入免费官方/稳定内部数据源，当前不把外部单点数值写入 Production Brain。",
        "ERP 暂不使用非稳定网页估算；后续接入可审计盈利收益率来源后再计算。"
      ],
      "next_validation":[
        "10年期名义/实际收益率是否继续上行",
        "HY OAS 是否继续走阔",
        "20/50/200日市场宽度是否修复",
        "VIX/MOVE 是否从低波动向高波动共振",
        "等权指数是否开始追上大盘市值加权指数"
      ],
      "guardrail":"跨资产背离是风险环境标签，不是做空或卖出指令。"
    }

def main():
    dash=load(DASH); out=build(dash,load(MACRO))
    history=mature_history(load(HISTORY),dash)
    as_of=str((dash.get("index") or {}).get("SPY",{}).get("date") or dash.get("spy_date") or "")[:10]
    anchor=num(((dash.get("index") or {}).get("SPY") or {}).get("close"))
    if as_of and anchor is not None:
        records=history.get("records") or []
        snap={
          "as_of":as_of,"anchor_spy":anchor,"level":out["level"],"label":out["label"],
          "risk_hits":out["risk_hits"],"high_hits":out["high_hits"],
          "signals":out["signals"],"outcomes":{}
        }
        existing=next((x for x in records if x.get("as_of")==as_of),None)
        if existing:
            snap["outcomes"]=existing.get("outcomes") or {}
            records[records.index(existing)]=snap
        else:
            records.append(snap)
        history["records"]=records[-240:]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    HISTORY.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"level":out["level"],"risk_hits":out["risk_hits"],"high_hits":out["high_hits"],"history":len(history.get("records") or [])},ensure_ascii=False))

if __name__=="__main__":main()
