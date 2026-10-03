#!/usr/bin/env python3
"""MyAlpha V6.8 Breadth Intelligence Engine.

Upgrades raw breadth from a display metric into a persistent research state.
It combines:
- S&P 500 participation above 20/50/200-day moving averages
- 10-day breadth slope
- cap-weighted vs equal-weight relative performance (SPY/RSP, QQQ/QQQE)
- persistent 5/20/60 trading-day outcome memory

Research-only: this layer may alter research priority, never portfolio exposure,
production thresholds, or orders by itself.
"""
from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DASH=ROOT/"docs/data.json"
OUT=ROOT/"docs/research/breadth_intelligence.json"
HISTORY=ROOT/"docs/research/breadth_intelligence_history.json"

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
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
                if px is not None:
                    outcomes[str(h)]={"date":dates[j],"return":px/anchor-1}
    return {"version":"6.8.0","records":rows[-300:]}

def proxy_gap(proxies,a,b,h="20"):
    pa=(proxies.get(a) or {}).get("returns") or {}
    pb=(proxies.get(b) or {}).get("returns") or {}
    va=num(pa.get(h)); vb=num(pb.get(h))
    return None if va is None or vb is None else va-vb

def build(dash):
    raw=dash.get("raw_breadth") or {}
    proxies=dash.get("breadth_proxies") or {}
    b20=num(raw.get("b20")); b50=num(raw.get("b50")); b200=num(raw.get("b200"))
    slope=num(raw.get("slope_10d"))
    spy_rsp=proxy_gap(proxies,"SPY","RSP","20")
    qqq_qqqe=proxy_gap(proxies,"QQQ","QQQE","20")
    ad20=num(raw.get("ad_line_20d")); ad60=num(raw.get("ad_line_60d"))
    nh52=num(raw.get("new_high_52w_pct")); near52=num(raw.get("near_high_52w_pct")); nl52=num(raw.get("new_low_52w_pct"))

    signals=[]
    def add(key,label,hit,severity,value,reason):
        signals.append({"key":key,"label":label,"hit":bool(hit),"severity":severity,"value":value,"reason":reason})

    add("b20_weak","20日参与度偏弱",b20 is not None and b20<0.40,"high",b20,
        f"仅 {b20:.0%} 成分股站上20日线" if b20 is not None else "缺失")
    add("b50_weak","50日参与度偏弱",b50 is not None and b50<0.45,"high",b50,
        f"仅 {b50:.0%} 成分股站上50日线" if b50 is not None else "缺失")
    add("b200_weak","长期参与度不足",b200 is not None and b200<0.50,"medium",b200,
        f"{b200:.0%} 成分股站上200日线" if b200 is not None else "缺失")
    add("breadth_falling","短期宽度继续恶化",slope is not None and slope<=-0.08,"medium",slope,
        f"20日宽度10日斜率 {slope:+.1%}" if slope is not None else "缺失")
    add("sp500_concentration","SPY领先RSP",spy_rsp is not None and spy_rsp>=0.025,"high",spy_rsp,
        f"20日SPY相对RSP领先 {spy_rsp:+.1%}" if spy_rsp is not None else "RSP对比待补齐")
    add("nasdaq_concentration","QQQ领先QQQE",qqq_qqqe is not None and qqq_qqqe>=0.025,"medium",qqq_qqqe,
        f"20日QQQ相对QQQE领先 {qqq_qqqe:+.1%}" if qqq_qqqe is not None else "QQQE对比待补齐")
    add("ad_pressure","A/D累计线偏弱",ad20 is not None and ad20<0,"medium",ad20,
        f"20日标准化A/D累计 {ad20:+.2f}" if ad20 is not None else "A/D待补齐")
    add("new_highs_thin","52周新高参与不足",nh52 is not None and nh52<0.10,"medium",nh52,
        f"仅 {nh52:.1%} 成分股处于52周新高" if nh52 is not None else "52周新高参与率待补齐")

    risk_hits=sum(1 for x in signals if x["hit"] and x["severity"] in {"high","medium"})
    high_hits=sum(1 for x in signals if x["hit"] and x["severity"]=="high")
    known=sum(v is not None for v in (b20,b50,b200,slope,spy_rsp,qqq_qqqe,ad20,nh52))
    score=50
    if b20 is not None: score += (b20-.50)*45
    if b50 is not None: score += (b50-.50)*30
    if b200 is not None: score += (b200-.50)*20
    if slope is not None: score += max(-12,min(12,slope*60))
    if spy_rsp is not None: score -= max(0,spy_rsp)*120
    if qqq_qqqe is not None: score -= max(0,qqq_qqqe)*80
    if ad20 is not None: score += max(-10,min(10,ad20*3))
    if nh52 is not None: score += max(-8,min(8,(nh52-.10)*40))
    participation_score=round(max(0,min(100,score)),1)

    if high_hits>=3 or (risk_hits>=4 and participation_score<40):
        level,label="fragile","参与度脆弱 · 权重股主导"
    elif risk_hits>=2 or participation_score<48:
        level,label="weakening","市场宽度走弱"
    elif participation_score>=62 and risk_hits==0:
        level,label="healthy","市场参与健康"
    else:
        level,label="mixed","市场参与分化"

    tags=[]
    if b20 is not None: tags.append("B20_LOW" if b20<.40 else "B20_OK")
    if b50 is not None: tags.append("B50_LOW" if b50<.45 else "B50_OK")
    if b200 is not None: tags.append("B200_LOW" if b200<.50 else "B200_OK")
    if slope is not None: tags.append("SLOPE_DOWN" if slope<0 else "SLOPE_UP")
    if spy_rsp is not None: tags.append("SPY_RSP_GAP" if spy_rsp>=.025 else "SPY_RSP_OK")
    if qqq_qqqe is not None: tags.append("QQQ_QQQE_GAP" if qqq_qqqe>=.025 else "QQQ_QQQE_OK")
    if ad20 is not None: tags.append("AD_NEG" if ad20<0 else "AD_POS")
    if nh52 is not None: tags.append("NH52_THIN" if nh52<.10 else "NH52_OK")

    unknowns=[]
    if raw.get("status")!="ok": unknowns.append("标普500成分股宽度当前未通过完整数据质量门。")
    if spy_rsp is None: unknowns.append("SPY/RSP 20日等权差尚未取得稳定数据。")
    if qqq_qqqe is None: unknowns.append("QQQ/QQQE 20日等权差尚未取得稳定数据。")
    if ad20 is None: unknowns.append("A/D累计参与度尚未取得稳定数据。")
    if nh52 is None: unknowns.append("52周新高参与率尚未取得稳定数据。")
    return {
      "version":"6.8.0",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "as_of":raw.get("date") or dash.get("spy_date") or dash.get("updated"),
      "level":level,"label":label,
      "participation_score":participation_score,
      "risk_hits":risk_hits,"high_hits":high_hits,"known_inputs":known,
      "metrics":{
        "b20":b20,"b50":b50,"b200":b200,"slope_10d":slope,
        "spy_minus_rsp_20d":spy_rsp,"qqq_minus_qqqe_20d":qqq_qqqe,
        "ad_net_pct":num(raw.get("ad_net_pct")),"ad_line_20d":ad20,"ad_line_60d":ad60,
        "new_high_52w_pct":nh52,"near_high_52w_pct":near52,"new_low_52w_pct":nl52,
        "coverage":raw.get("coverage"),"universe":raw.get("universe"),
      },
      "signals":signals,
      "combination_key":"|".join(tags) if tags else "INSUFFICIENT_DATA",
      "interpretation":[
        "指数上涨若伴随等权指数落后和成分股宽度下降，说明上涨参与度收窄。",
        "宽度恶化可提高风险研究优先级，但不能单独等同于顶部或卖出信号。",
        "若等权指数追上、20/50日宽度回升且斜率转正，集中度风险可被逐步消化。"
      ],
      "unknowns":unknowns,
      "next_validation":[
        "20/50日宽度是否连续修复",
        "RSP能否缩小对SPY的20日相对落后",
        "QQQE能否缩小对QQQ的20日相对落后",
        "200日宽度是否重新站上50%",
        "跨资产利率/信用压力是否与宽度恶化共振"
      ],
      "guardrail":"Breadth Intelligence 是市场参与度研究层，不是自动减仓、卖出或做空指令。"
    }

def main():
    dash=load(DASH)
    out=build(dash)
    history=mature_history(load(HISTORY),dash)
    as_of=str(out.get("as_of") or "")[:10]
    anchor=num(((dash.get("index") or {}).get("SPY") or {}).get("close"))
    if as_of and anchor is not None:
        records=history.get("records") or []
        snap={
          "as_of":as_of,"anchor_spy":anchor,"level":out["level"],"label":out["label"],
          "participation_score":out["participation_score"],"risk_hits":out["risk_hits"],
          "combination_key":out["combination_key"],"metrics":out["metrics"],"outcomes":{}
        }
        old=next((x for x in records if x.get("as_of")==as_of),None)
        if old:
            snap["outcomes"]=old.get("outcomes") or {}
            records[records.index(old)]=snap
        else: records.append(snap)
        history["records"]=records[-300:]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    HISTORY.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"level":out["level"],"score":out["participation_score"],"risk_hits":out["risk_hits"],"history":len(history.get("records") or [])},ensure_ascii=False))

if __name__=="__main__":main()
