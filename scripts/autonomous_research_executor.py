#!/usr/bin/env python3
"""MyAlpha V6.2 Autonomous Research Executor.

Executes the highest-priority V6 research tasks using already-validated internal
artifacts. It produces a structured research brief with supporting evidence,
counter-evidence, unknowns and next validation. It never places orders and does
not invent missing external facts.

The executor is intentionally evidence-first. External live web/SEC/news
connectors can attach later; until then, missing official/company evidence is
explicitly marked unknown rather than guessed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from app_version import APP_VERSION

ROOT=Path(__file__).resolve().parents[1]
PATHS={
    "planner":ROOT/"docs/research/research_planner.json",
    "learning":ROOT/"docs/research/learning_engine.json",
    "evidence":ROOT/"docs/research/evidence_attribution.json",
    "method":ROOT/"docs/research/method_memory.json",
    "source":ROOT/"docs/data/source_intelligence.json",
    "modules":ROOT/"docs/research/module_intelligence.json",
    "official":ROOT/"docs/research/official_evidence.json",
    "event_windows":ROOT/"docs/research/event_window_attribution.json",
    "events":ROOT/"docs/research/event_evidence.json",
    "cross_asset":ROOT/"docs/research/cross_asset_divergence.json",
    "cross_asset_history":ROOT/"docs/research/cross_asset_divergence_history.json",
    "breadth_intelligence":ROOT/"docs/research/breadth_intelligence.json",
    "breadth_history":ROOT/"docs/research/breadth_intelligence_history.json",
    "regime_memory":ROOT/"docs/research/regime_combination_memory.json",
    "regime_history":ROOT/"docs/research/regime_combination_history.json",
    "data":ROOT/"docs/data.json",
    "previous":ROOT/"docs/research/research_execution.json",
}
OUT=ROOT/"docs/research/research_execution.json"

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def add_unique(rows,item):
    if item and item not in rows: rows.append(item)

def fmt_num(v,d=2):
    try:
        return f"{float(v):.{d}f}"
    except Exception:
        return "—"

def fmt_pct(v,d=1):
    try:
        return f"{float(v)*100:.{d}f}%"
    except Exception:
        return "—"

def fmt_bp(v,d=2):
    try:
        return f"{float(v):.{d}f}"
    except Exception:
        return "—"

def situation_map(learning):
    return {x.get("symbol"):x for x in (learning.get("situation_memory") or []) if x.get("symbol")}

def source_rows(source,symbol):
    if not symbol:return []
    return [r for r in (source.get("records") or []) if symbol in (r.get("symbols") or [])]

def failure_rows(evidence,symbol):
    rows=(evidence.get("failure_attribution") or {}).get("external_outcome_reviews") or []
    return [x for x in rows if x.get("symbol")==symbol]

def module_map(modules):
    return {m.get("id"):m for m in (modules.get("modules") or []) if m.get("id")}

def method_map(method):
    return {m.get("method"):m for m in (method.get("methods") or []) if m.get("method")}

def market_brief(task,learning,evidence,source,data,official=None,events=None):
    sym=task.get("key")
    sit=situation_map(learning).get(sym) or {}
    tp=(data.get("trend_pulse") or {}).get(sym) or {}
    support=[];counter=[];unknowns=[]
    priority=sit.get("research_priority")
    stage=sit.get("stage") or tp.get("state")
    if stage:add_unique(support,f"Trend Pulse / Situation 当前阶段：{stage}")
    if priority is not None:add_unique(support,f"Learning Engine 研究优先级：{fmt_num(priority,0)}/100")
    hist=sit.get("historical_stage_evidence") or {}
    if hist.get("n60"):add_unique(support,f"相同阶段60日历史样本：{hist.get('n60')}，中位收益 {fmt_pct(hist.get('median60'))}")
    for c in sit.get("contradictions") or []:
        add_unique(counter,str(c.get("message") or c.get("evidence") or c))
    fr=failure_rows(evidence,sym)
    if fr:add_unique(counter,f"Failure Attribution 中存在 {len(fr)} 个该标的外部研究反例/失效样本")
    sr=source_rows(source,sym)
    if sr:
        latest=sorted(sr,key=lambda x:str(x.get("published_at") or ""),reverse=True)[:3]
        add_unique(support,f"Source Intelligence 有 {len(sr)} 条与 {sym} 相关研究记录；最近 {len(latest)} 条已进入独立验证层")
    else:add_unique(unknowns,"暂无可用外部研究记录")
    official=official or {}
    sec=(official.get("symbols") or {}).get(sym) or {}
    filings=sec.get("filings") or []
    if filings:
        latest_f=filings[0]
        add_unique(support,f"SEC官方披露：最近 {latest_f.get('form')}，提交日 {latest_f.get('filing_date')}")
        if latest_f.get("excerpts"):
            add_unique(support,"SEC文档已抓取官方原文证据片段，可用于下一步事件核验")
        else:
            add_unique(unknowns,"SEC申报元数据已取得，但最新文档正文证据片段暂不可用")
    elif sym in {"QQQ","QQQM","VOO","SPY","VGT","QLD","TQQQ","SMH","IBIT","GLD","RSP"}:
        add_unique(support,"该标的是ETF/基金工具，单一公司SEC披露不适用；应使用成分股、基金文件和行业证据。")
    elif sec.get("status") in {"unmapped","error"}:
        add_unique(unknowns,f"SEC官方证据暂不可用：{sec.get('status')}")
    else:
        add_unique(unknowns,"尚未生成该标的SEC官方证据缓存")
    integ=tp.get("data_integrity") or {}
    integ_status=str(integ.get("status") or "").upper()
    if integ_status in {"OK","PASS","VALID","VERIFIED"}:
        add_unique(support,f"Trend Pulse 数据校验状态：{integ.get('label') or integ.get('status')}")
    elif integ_status:
        add_unique(counter,f"Trend Pulse 数据校验状态：{integ.get('label') or integ.get('status')}")
    if not filings and sym not in {"QQQ","QQQM","VOO","SPY","VGT","QLD","TQQQ","SMH","IBIT","GLD","RSP"}:add_unique(unknowns,"尚未完成本任务对应的最新SEC官方披露核验")
    events=events or {}
    ev=(events.get("symbols") or {}).get(sym) or {}
    news=ev.get("news") or []
    peer=ev.get("peer_context") or {}
    tier1=[n for n in news if n.get("source_priority")==1]
    if tier1:
        latest=tier1[0]
        add_unique(support,f"高优先级事件源：{latest.get('publisher') or latest.get('source_type')} · {latest.get('title')}")
    elif news:
        add_unique(unknowns,f"已读取 {len(news)} 条相关一般媒体线索，但暂无 Reuters/AP/新闻稿等高优先级事件源确认")
    else:
        add_unique(unknowns,"最近媒体事件证据暂不可用")
    if peer.get("peer_count"):
        direction=peer.get("direction")
        avg=peer.get("avg_day_change")
        if direction in {"broad_positive","broad_negative"} and peer.get("peer_count",0)>=2:
            add_unique(support,f"同业联动：{peer.get('peer_count')} 个可比标的，方向 {direction}，平均日变动 {fmt_pct(avg)}")
        else:
            add_unique(unknowns,f"同业样本已读取但未形成一致共振：{peer.get('peer_count')} 个，方向 {direction}")
    else:
        add_unique(unknowns,"行业同业联动样本暂不足")
    add_unique(unknowns,"公司IR官网全文仍待专用连接；当前已使用SEC官方披露与分级媒体事件线索")
    return support,counter,unknowns

def failure_brief(task,evidence,method,official=None,event_windows=None):
    sym=task.get("key")
    rows=failure_rows(evidence,sym)
    support=[];counter=[];unknowns=[]
    official=official or {}
    tags={}
    for r in rows:
        for t in r.get("review_tags") or r.get("tags") or []:tags[t]=tags.get(t,0)+1
    if rows:add_unique(support,f"已聚合 {len(rows)} 个 {sym} 失败/反例样本")
    if tags:
        ranked=sorted(tags.items(),key=lambda x:x[1],reverse=True)[:5]
        add_unique(support,"高频失败标签："+ "、".join(f"{k}×{v}" for k,v in ranked))
    mfail=[]
    for m in method.get("methods") or []:
        for x in m.get("failure_examples") or []:
            if x.get("symbol")==sym:mfail.append((m.get("method"),x))
    if mfail:add_unique(counter,f"Method Memory 中还有 {len(mfail)} 个跨方法反例，需要避免把单一原因解释成全部失败")
    sec=(official.get("symbols") or {}).get(sym) or {}
    filings=sec.get("filings") or []
    if filings:
        dates=", ".join(f"{f.get('form')} {f.get('filing_date')}" for f in filings[:3])
        add_unique(support,f"SEC官方时间线可用于失败归因对齐：{dates}")
        if any(f.get("excerpts") for f in filings):
            add_unique(support,"SEC官方正文片段已缓存，可继续检查失败窗口内是否存在公司事件或风险披露")
    event_windows=event_windows or {}
    aligned=[x for x in (event_windows.get("rows") or []) if x.get("symbol")==sym]
    if aligned:
        near_sec=sum(1 for x in aligned if (x.get("nearest_sec") or {}).get("distance_band") in {"very_near","near","week"})
        near_evt=sum(1 for x in aligned if (x.get("nearest_event") or {}).get("distance_band") in {"very_near","near","week"})
        add_unique(support,f"事件窗口已自动对齐 {len(aligned)} 个失败样本；7日内SEC {near_sec}，7日内分级事件 {near_evt}")
        add_unique(counter,"事件时间接近仅生成复盘假设，不代表事件造成失败")
    else:
        add_unique(unknowns,"尚未完成每个失败样本的公司事件/财报/宏观时间线对齐")
    add_unique(unknowns,"若存在期权策略，当前公开结果不能替代真实期权P&L")
    return support,counter,unknowns

def method_gap_brief(task,method):
    name=task.get("key")
    m=method_map(method).get(name) or {}
    support=[];counter=[];unknowns=[]
    direct=m.get("direct_validated_events") or 0
    context=m.get("context_validated_events") or 0
    add_unique(support,f"{name}：Context {context}，Direct {direct}")
    if context>direct:add_unique(counter,f"仍有 {context-direct} 个上下文事件不能直接归因到该方法")
    if m.get("performance") is None:add_unique(counter,"当前不展示方法绩效，避免把上下文相关性误当方法有效性")
    add_unique(unknowns,"需要更多明确触发条件、动作字段和后续结果才能扩大Direct样本")
    return support,counter,unknowns

def method_validation_brief(task,method):
    name=task.get("key")
    m=method_map(method).get(name) or {}
    support=[];counter=[];unknowns=[]
    if not m:
        return support,counter,["Method Memory 中未找到该方法"]

    direct=int(m.get("direct_validated_events") or 0)
    context=int(m.get("context_validated_events") or 0)
    evidence=m.get("evidence_maturity") or {}
    state=evidence.get("state") or m.get("status") or "context_only"
    add_unique(support,f"{name}：证据状态 {state}；Direct {direct}，Context {context}")

    perf=m.get("performance") or {}
    for h in ("5","20","60"):
        row=perf.get(h) or {}
        n=int(row.get("n") or 0)
        if not n:
            add_unique(unknowns,f"{h}日直接结果尚无成熟样本")
            continue
        rate=row.get("alignment_rate")
        ret=row.get("avg_return")
        excess=row.get("avg_excess_vs_qqq")
        msg=f"{h}日直接样本 {n}"
        if isinstance(rate,(int,float)):msg+=f"，方向一致率 {rate:.0%}"
        if isinstance(ret,(int,float)):msg+=f"，平均收益 {ret:+.1%}"
        if isinstance(excess,(int,float)):msg+=f"，相对QQQ {excess:+.1%}"
        add_unique(support,msg)

    failures=m.get("failure_examples") or []
    if failures:
        add_unique(counter,f"已保留 {len(failures)} 个直接反例/不利结果用于复盘")
        for x in failures[:2]:
            add_unique(counter,f"{x.get('symbol') or '—'} · {x.get('horizon') or '—'}日 · return {fmt_pct(x.get('return'))} · {x.get('alignment') or '未评分'}")

    if state=="outcome_challenging":
        add_unique(counter,"当前直接结果偏挑战；优先检查环境、时点和归因，不自动修改正式规则")
    elif state=="outcome_mixed":
        add_unique(counter,"当前结果混合；需要按市场环境/动作类型分层，不能用单一平均值下结论")
    elif state=="outcome_supportive":
        add_unique(unknowns,"当前为支持状态，仍需主动寻找跨环境反例，避免确认偏误")
    elif state in {"direct_early","direct_developing"}:
        add_unique(unknowns,"证据仍在积累期；样本不足时不得晋级为稳定方法")

    return support,counter,unknowns

def module_brief(task,modules):
    m=module_map(modules).get(task.get("key")) or {}
    support=[];counter=[];unknowns=[]
    if m:
        add_unique(support,f"模块存在目的：{m.get('why_it_exists')}")
        add_unique(support,f"当前学习模式：{m.get('learning')}")
        add_unique(support,"输入："+"、".join(m.get("inputs") or []))
        add_unique(support,"输出："+"、".join(m.get("outputs") or []))
        add_unique(counter,f"学习边界：{m.get('guardrail')}")
        if m.get("learning") in {"candidate","shadow_only","private_shadow"}:
            add_unique(unknowns,"仍需用可验证结果标签证明该模块值得扩大自学习范围")
    else:add_unique(unknowns,"模块注册表中未找到该模块")
    return support,counter,unknowns

def cross_asset_brief(task,cross_asset,history):
    cross_asset=cross_asset or {}
    history=history or {}
    support=[];counter=[];unknowns=[]
    for s in cross_asset.get("signals") or []:
        if not s.get("hit"): continue
        msg=f"{s.get('label')}：{s.get('reason')}"
        if s.get("severity")=="offset" or any(k in msg for k in ("缓冲","宽松","改善","回落","收窄")):
            add_unique(counter,msg)
        else:
            add_unique(support,msg)
    if cross_asset.get("level") in {"medium","high"}:
        add_unique(support,f"当前状态：{cross_asset.get('label')}；风险信号 {cross_asset.get('risk_hits',0)} 项，其中高等级 {cross_asset.get('high_hits',0)} 项")
    for x in cross_asset.get("thesis") or []:
        text=str(x)
        if any(k in text for k in ("缓冲","否定","消化","回落","收窄","改善")):
            add_unique(counter,text)
        else:
            add_unique(support,text)
    mature={"5":[],"20":[],"60":[]}
    for row in history.get("records") or []:
        if row.get("level") not in {"medium","high"}: continue
        for h in mature:
            v=((row.get("outcomes") or {}).get(h) or {}).get("return")
            if isinstance(v,(int,float)): mature[h].append(v)
    for h,vals in mature.items():
        if vals:
            avg=sum(vals)/len(vals)
            pos=sum(1 for v in vals if v>0)/len(vals)
            add_unique(support,f"历史同类背离 {h} 日成熟样本 {len(vals)}：平均收益 {avg:+.1%}，正收益比例 {pos:.0%}")
        else:
            add_unique(unknowns,f"跨资产背离 {h} 日成熟样本仍不足")
    for x in cross_asset.get("unknowns") or []: add_unique(unknowns,x)
    return support,counter,unknowns


def breadth_brief(task,breadth,history):
    breadth=breadth or {}; history=history or {}
    support=[];counter=[];unknowns=[]
    metrics=breadth.get("metrics") or {}
    for sig in breadth.get("signals") or []:
        if not sig.get("hit"): continue
        msg=f"{sig.get('label')}：{sig.get('reason')}"
        add_unique(support,msg)
    score=breadth.get("participation_score")
    if score is not None:add_unique(support,f"市场参与度评分：{score}/100")
    if breadth.get("combination_key"):add_unique(support,f"宽度组合状态：{breadth.get('combination_key')}")
    mature={"5":[],"20":[],"60":[]}
    for row in history.get("records") or []:
        if row.get("level") not in {"fragile","weakening"}: continue
        for h in mature:
            v=((row.get("outcomes") or {}).get(h) or {}).get("return")
            if isinstance(v,(int,float)): mature[h].append(v)
    for h,vals in mature.items():
        if vals:
            add_unique(support,f"历史弱宽度 {h} 日成熟样本 {len(vals)}：平均SPY收益 {sum(vals)/len(vals):+.1%}")
        else:add_unique(unknowns,f"弱宽度 {h} 日成熟样本仍不足")
    for x in breadth.get("unknowns") or []:add_unique(unknowns,x)
    return support,counter,unknowns

def regime_brief(task,regime,history):
    regime=regime or {}; history=history or {}
    support=[];counter=[];unknowns=[]
    state=regime.get("state_id")
    if state:add_unique(support,f"当前组合状态：{state}")
    b=regime.get("breadth") or {}; c=regime.get("cross_asset") or {}; v=regime.get("vix") or {}
    add_unique(support,f"跨资产层：{c.get('label') or c.get('level')}；风险信号 {c.get('risk_hits','—')}")
    add_unique(support,f"宽度层：{b.get('label') or b.get('level')}；参与度评分 {fmt_num(b.get('participation_score'),1)}")
    if v.get("value") is not None:
        msg=f"VIX={fmt_num(v.get('value'),2)}，分区 {v.get('zone')}"
        if str(v.get("zone")).lower() in {"low","normal"}: add_unique(counter,msg+"；波动率尚未确认风险升级")
        else: add_unique(support,msg)
    matched=[x for x in history.get("records") or [] if x.get("state_id")==state]
    for h in ("5","20","60"):
        vals=[((x.get("outcomes") or {}).get(h) or {}).get("return") for x in matched]
        vals=[x for x in vals if isinstance(x,(int,float))]
        if vals:
            add_unique(support,f"同组合 {h} 日成熟样本 {len(vals)}：平均收益 {sum(vals)/len(vals):+.1%}，最差 {min(vals):+.1%}")
        else:add_unique(unknowns,f"同组合 {h} 日成熟样本仍不足")
    if regime.get("level")=="high":add_unique(support,"跨资产压力与脆弱宽度当前同时出现，应优先验证是否继续共振")
    return support,counter,unknowns

def leverage_rebound_brief(task,data):
    row=(data or {}).get("leverage_rebound") or {}
    support=[];counter=[];unknowns=[]
    for x in row.get("supporting_evidence") or []: add_unique(support,x)
    for x in row.get("counter_evidence") or []: add_unique(counter,x)
    for x in row.get("unknowns") or []: add_unique(unknowns,x)
    if row.get("drawdown252") is not None:
        add_unique(support,f"QQQ 252日回撤：{row.get('drawdown252'):+.1%}")
    if row.get("status"):
        add_unique(support,f"回调情境状态：{row.get('label') or row.get('status')}")
    src=row.get("source_method") or {}
    if src.get("title"):
        add_unique(support,f"Source Hypothesis：{src.get('author')} · {src.get('title')}，仅作待验证方法来源")
    if row.get("status")=="risk":
        add_unique(counter,"深熊/二次下探风险优先，现有TQQQ正式降险规则不得被外部方法覆盖")
    return support,counter,unknowns

def execute_task(task,artifacts):
    kind=task.get("kind")
    if kind in {"market_anomaly","discovery"}:
        support,counter,unknowns=market_brief(task,artifacts["learning"],artifacts["evidence"],artifacts["source"],artifacts["data"],artifacts.get("official"),artifacts.get("events"))
    elif kind=="cross_asset_divergence":
        support,counter,unknowns=cross_asset_brief(task,artifacts.get("cross_asset"),artifacts.get("cross_asset_history"))
    elif kind=="breadth_intelligence":
        support,counter,unknowns=breadth_brief(task,artifacts.get("breadth_intelligence"),artifacts.get("breadth_history"))
    elif kind=="regime_combination":
        support,counter,unknowns=regime_brief(task,artifacts.get("regime_memory"),artifacts.get("regime_history"))
    elif kind=="leverage_rebound":
        support,counter,unknowns=leverage_rebound_brief(task,artifacts.get("data"))
    elif kind=="failure_review":
        support,counter,unknowns=failure_brief(task,artifacts["evidence"],artifacts["method"],artifacts.get("official"),artifacts.get("event_windows"))
    elif kind=="method_evidence_gap":
        support,counter,unknowns=method_gap_brief(task,artifacts["method"])
    elif kind=="method_validation":
        support,counter,unknowns=method_validation_brief(task,artifacts["method"])
    elif kind in {"module_learning_review","architecture_gap"}:
        support,counter,unknowns=module_brief(task,artifacts["modules"])
    else:
        support,counter,unknowns=[],[],["当前执行器尚未定义此任务类型的证据适配器"]

    score=min(100,20+12*len(support)+8*len(counter)-10*len(unknowns))
    if not support:score=min(score,30)
    confidence="low" if score<40 else "medium" if score<70 else "high"
    if counter:
        conclusion="证据存在分歧，保持研究状态并优先验证反证。"
    elif support and unknowns:
        conclusion="已有初步支持证据，但关键外部事实仍缺失，暂不升级为结论。"
    elif support:
        conclusion="内部证据较一致，但仍只作为研究结论，不产生自动交易动作。"
    else:
        conclusion="证据不足，维持观察并等待更多可验证信息。"

    return {
      "task_id":task.get("task_id"),"kind":kind,"key":task.get("key"),"title":task.get("title"),
      "priority":task.get("priority"),"research_status":"analyzed",
      "supporting_evidence":support[:8],"counter_evidence":counter[:8],"unknowns":unknowns[:8],
      "evidence_score":max(0,score),"confidence":confidence,"provisional_conclusion":conclusion,
      "next_validation":(task.get("questions") or [])[:4],
      "source_requirements":task.get("evidence_sources") or [],
      "guardrail":"该研究结果不能自动下单；未知项不得由模型猜测补全。"
    }

def build(planner,artifacts,previous):
    tasks=(planner.get("today") or [])[:8]
    # If the live queue is short, include the highest-value non-live research tasks.
    if len(tasks)<8:
        existing={x.get("task_id") for x in tasks}
        for t in planner.get("queue") or []:
            if t.get("task_id") in existing:continue
            tasks.append(t)
            if len(tasks)>=8:break
    rows=[execute_task(t,artifacts) for t in tasks]
    old={x.get("task_id"):x for x in (previous.get("results") or [])}
    now=datetime.now(timezone.utc).isoformat()
    for x in rows:
        prior=old.get(x["task_id"]) or {}
        x["analysis_runs"]=(prior.get("analysis_runs") or 0)+1
        x["first_analyzed_at"]=prior.get("first_analyzed_at") or now
        x["last_analyzed_at"]=now
    return {
      "version":APP_VERSION,"generated_at":now,"planner_version":planner.get("version"),
      "results":rows,
      "summary":{
        "analyzed":len(rows),
        "high_confidence":sum(x["confidence"]=="high" for x in rows),
        "medium_confidence":sum(x["confidence"]=="medium" for x in rows),
        "low_confidence":sum(x["confidence"]=="low" for x in rows),
        "with_counter_evidence":sum(bool(x["counter_evidence"]) for x in rows),
        "with_unknowns":sum(bool(x["unknowns"]) for x in rows),
      },
      "policy":{
        "required_fields":["supporting_evidence","counter_evidence","unknowns","next_validation"],
        "no_hallucinated_fill":True,
        "automatic_orders":False,
        "production_rule_mutation":False
      }
    }

def main():
    d={k:load(v) for k,v in PATHS.items()}
    artifacts={k:d[k] for k in ("learning","evidence","method","source","modules","official","event_windows","events","cross_asset","cross_asset_history","breadth_intelligence","breadth_history","regime_memory","regime_history","data")}
    out=build(d["planner"],artifacts,d["previous"])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["summary"],ensure_ascii=False))
if __name__=="__main__":main()
