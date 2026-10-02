#!/usr/bin/env python3
"""MyAlpha V6.1 Module Intelligence Graph.

Audits every first-level website module and major cross-cutting engine so each
component has a declared purpose, evidence inputs, learning policy and outputs.
The graph is deliberately explicit: modules may be learning-enabled, private-
learning-only, observational, or intentionally non-learning.

This file does not read private Supabase positions and does not alter trading
rules.
"""
from __future__ import annotations

import json, re
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/"docs"/"index.html"
OUT=ROOT/"docs"/"research"/"module_intelligence.json"

def artifact(path:str):
    p=ROOT/path
    return {"path":path,"available":p.exists()}

MODULES=[
    {
      "id":"tab-overview","name":"市场与风险驾驶舱","role":"decision_hub",
      "purpose":"把市场环境、核心ETF、个股、期权风险和 Agent 优先级压缩成今日入口。",
      "inputs":["docs/data.json","learning_engine","autonomous_agent","research_planner","system_status"],
      "outputs":["research_planner","decision_journal"],
      "learning":"derived_learning",
      "learns_from":["Situation Memory","Agent attention changes","Decision outcomes"],
      "why_it_exists":"减少用户在多个页面之间寻找今日重点；作为全站研究结论的汇合层。",
      "guardrail":"展示研究优先级，不把高优先级直接解释为买卖信号。"
    },
    {
      "id":"tab-engine","name":"核心策略信号","role":"policy_monitor",
      "purpose":"监控核心ETF回撤档位、TQQQ X2与LEAPS候选条件，保持正式规则可审计。",
      "inputs":["docs/data.json","trend_pulse_backtest","assistant_rule_validation"],
      "outputs":["research_planner","decision_journal","failure_attribution"],
      "learning":"shadow_only",
      "learns_from":["historical rule outcomes","false triggers","missed opportunities"],
      "why_it_exists":"把长期核心配置和战术策略从主观判断中分离出来，并提供可回测规则。",
      "guardrail":"Production阈值锁定；V7只能提出Shadow候选，不能静默修改正式规则。"
    },
    {
      "id":"tab-system-health","name":"系统自检","role":"reliability",
      "purpose":"检查数据、自动化、部署和学习产物是否真实运行，避免坏数据进入研究链。",
      "inputs":["system_status","build_manifest","autonomous_qa"],
      "outputs":["research_planner","operator_attention"],
      "learning":"operational_learning",
      "learns_from":["workflow failures","artifact freshness","deployment mismatch"],
      "why_it_exists":"自主Agent必须先知道自己是否健康；数据链异常时应降级而不是继续自信输出。",
      "guardrail":"健康状态只影响可信度和提醒，不修改交易规则。"
    },
    {
      "id":"tab-wenxuecity","name":"方法研究中心","role":"external_research",
      "purpose":"把外部作者观点转换成可验证事件、方法样本、反例与历史结果。",
      "inputs":["source_intelligence","source_outcomes","evidence_attribution","method_memory"],
      "outputs":["method_memory","failure_attribution","research_planner","self_improvement"],
      "learning":"continuous",
      "learns_from":["author actions","5/20/60-day outcomes","MAE/MFE","counterexamples"],
      "why_it_exists":"外部观点只有经过独立验证后才成为MyAlpha经验，而不是直接复制博主结论。",
      "guardrail":"外部来源永远是证据源，不是交易权威。"
    },
    {
      "id":"tab-knowledge","name":"投资知识与方法","role":"knowledge_base",
      "purpose":"保存长期有效的概念、方法说明和研究框架，为Agent与用户提供统一术语。",
      "inputs":["research_methods","method_memory","evidence_attribution"],
      "outputs":["research_planner","explanation_layer"],
      "learning":"curated_learning",
      "learns_from":["validated method evidence","failure lessons"],
      "why_it_exists":"把知识和实时信号分开，避免短期行情改变长期定义。",
      "guardrail":"只有经验证的新知识进入正式知识层；论坛观点不能直接覆盖基础方法。"
    },
    {
      "id":"tab-journal","name":"Decision Journal · 决策复盘","role":"outcome_memory",
      "purpose":"记录当时判断并在20/60/120交易日后回看结果，形成错误记忆和学习证据。",
      "inputs":["historical_journal","autonomous_agent","research_planner"],
      "outputs":["learning_engine","failure_attribution","self_improvement"],
      "learning":"continuous",
      "learns_from":["decision outcomes","missed opportunities","false positives","noise"],
      "why_it_exists":"没有当时快照就无法判断Agent是真正进步还是事后解释。",
      "guardrail":"结果复盘区分研究质量与市场随机性，不以单样本重写规则。"
    },
    {
      "id":"tab-index","name":"指数、行业与另类资产","role":"market_context",
      "purpose":"提供核心指数、行业卫星和另类资产的统一市场背景与策略距离。",
      "inputs":["docs/data.json","trend_pulse"],
      "outputs":["learning_engine","research_planner"],
      "learning":"continuous",
      "learns_from":["trend regimes","drawdowns","cross-asset confirmation"],
      "why_it_exists":"个股与期权判断需要先知道宽基、行业和风险资产处于什么环境。",
      "guardrail":"跨资产相关性用于环境判断，不自动推导个股方向。"
    },
    {
      "id":"tab-cn-hk","name":"A股港股 & 红利低波","role":"regional_context",
      "purpose":"补充中国/香港市场、红利和跨境ETF环境，避免MyAlpha只理解美股。",
      "inputs":["docs/data.json","market_live"],
      "outputs":["research_planner","future_cross_market_memory"],
      "learning":"candidate",
      "learns_from":["future cross-market regime samples"],
      "why_it_exists":"为人民币资产、港股与跨市场风险提供独立背景。",
      "guardrail":"当前学习样本不足时只做观察层，不把相关性当领先指标。"
    },
    {
      "id":"tab-stocks","name":"个股观察池","role":"company_research",
      "purpose":"把价格、Trend Pulse、策略距离、基本面研究卡和事件风险汇总到单股层。",
      "inputs":["docs/data.json","learning_engine","autonomous_agent","SEC/IR","company_news"],
      "outputs":["research_planner","decision_journal","options_context"],
      "learning":"continuous",
      "learns_from":["company situations","event outcomes","trend transitions","research results"],
      "why_it_exists":"将市场级判断落到具体公司，形成可持续的Company Memory。",
      "guardrail":"观察池优先级不等于推荐；事件与基本面必须独立验证。"
    },
    {
      "id":"tab-options","name":"期权持仓与风险监控","role":"private_position_risk",
      "purpose":"按账户管理真实期权、剩余Edge、Delta/IV/DTE、事件风险和展期纪律。",
      "inputs":["Supabase private positions","Alpaca indicative options","market_events","stock_context"],
      "outputs":["private_decision_memory","decision_journal","research_planner"],
      "learning":"private_only",
      "learns_from":["closed-trade outcomes","roll outcomes","premium capture","assignment/near-assignment cases"],
      "why_it_exists":"期权风险取决于真实仓位和合约结构，不能只由公开行情模块替代。",
      "guardrail":"真实持仓不写入公开docs；自动学习不得跨账户合并，也不自动下单。"
    },
    {
      "id":"tab-finance-tools","name":"理财工具","role":"calculator",
      "purpose":"做现金流、定投、收益率与期限情景计算，支持长期规划。",
      "inputs":["browser local user assumptions"],
      "outputs":["user_planning_only"],
      "learning":"intentionally_static",
      "learns_from":[],
      "why_it_exists":"这是确定性规划工具，不应把用户随手输入的假设当成市场训练数据。",
      "guardrail":"本机计算；不把目标金额、资产或试算参数送入Agent学习。"
    },
    {
      "id":"tab-trend-pulse","name":"趋势脉冲","role":"technical_state",
      "purpose":"把多指标、多周期价格结构压缩为可验证的趋势状态机。",
      "inputs":["docs/data.json","stooq_history","trend_pulse_backtest"],
      "outputs":["learning_engine","autonomous_agent","research_planner","failure_attribution"],
      "learning":"continuous",
      "learns_from":["state transitions","5/20/60-day outcomes","false breaks","market regime"],
      "why_it_exists":"为策略、个股、期权提供统一趋势语言，并允许历史验证。",
      "guardrail":"Trend Pulse是证据层，不是单独交易信号。"
    },
    {
      "id":"tab-sandbox","name":"期权决策台","role":"scenario_lab",
      "purpose":"在不影响真实持仓的情况下测试期权情景、Greeks和目标价格。",
      "inputs":["browser scenario inputs","indicative option data"],
      "outputs":["private_decision_memory","future_shadow_policy"],
      "learning":"private_shadow",
      "learns_from":["saved scenarios only when explicitly committed","later realized outcomes"],
      "why_it_exists":"把假设实验与真实仓位隔离，允许V7测试方法而不污染Production。",
      "guardrail":"未保存的临时情景不进入长期记忆；任何结果不自动下单。"
    },
    {
      "id":"tab-archive","name":"历史归档与管理","role":"memory_store",
      "purpose":"保存历史买点、账户隔离、展期记录和管理入口，为后续复盘提供原始事实。",
      "inputs":["Supabase private records","historical events","roll history"],
      "outputs":["decision_journal","method_memory","private_learning"],
      "learning":"source_memory",
      "learns_from":["closed records","historical actions","roll histories"],
      "why_it_exists":"学习系统需要不可随意改写的历史事实作为训练样本。",
      "guardrail":"事实记录与AI解释分层；原始成交记录不可被模型重写。"
    },
]

SERVICES=[
 {"id":"investment-assistant","name":"AI投资助手","role":"attention_router","inputs":["market regime","events","positions"],"outputs":["overview","options","research_planner"],"learning":"continuous"},
 {"id":"autonomous-agent","name":"Autonomous Agent Brain","role":"orchestrator","inputs":["learning_engine","evidence","research_planner","research_execution","self_improvement"],"outputs":["overview","research_planner","decision_journal"],"learning":"continuous"},
 {"id":"research-executor","name":"Autonomous Research Executor","role":"evidence_synthesis","inputs":["research_planner","learning_engine","evidence_attribution","method_memory","source_intelligence","module_intelligence"],"outputs":["self_improvement","overview","decision_journal"],"learning":"continuous"},
 {"id":"opportunity-radar","name":"Opportunity Radar","role":"discovery","inputs":["market data","strategy distances","trend states"],"outputs":["research_planner"],"learning":"shadow_only"},
 {"id":"roll-manager","name":"Roll Manager","role":"private_execution_support","inputs":["private option positions","Delta/IV/DTE","events"],"outputs":["private_decision_memory","decision_journal"],"learning":"private_only"},
 {"id":"core-execution","name":"Core Execution","role":"policy_execution_support","inputs":["core strategy states"],"outputs":["decision_journal"],"learning":"shadow_only"},
 {"id":"research-methods","name":"Research Methods","role":"method_reference","inputs":["curated knowledge","method memory"],"outputs":["knowledge","research_planner"],"learning":"curated_learning"},
 {"id":"market-live","name":"Market Live","role":"freshness_layer","inputs":["live/near-live quotes"],"outputs":["overview","stocks","options"],"learning":"none"},
 {"id":"autonomous-qa","name":"Autonomous QA","role":"safety_reliability","inputs":["site build","browser checks"],"outputs":["system_health"],"learning":"operational_learning"},
]

ARTIFACTS={
 "learning_engine":"docs/research/learning_engine.json",
 "autonomous_agent":"docs/research/autonomous_agent.json",
 "research_planner":"docs/research/research_planner.json",
 "research_execution":"docs/research/research_execution.json",
 "self_improvement":"docs/research/self_improvement.json",
 "method_memory":"docs/research/method_memory.json",
 "failure_attribution":"docs/research/evidence_attribution.json",
 "historical_journal":"docs/research/historical_journal.json",
 "system_status":"docs/research/system_status.json",
 "trend_pulse_backtest":"docs/research/trend_pulse_backtest.json",
 "source_intelligence":"docs/data/source_intelligence.json",
 "source_outcomes":"docs/research/source_outcome_validation.json",
 "assistant_rule_validation":"docs/research/assistant_rule_validation.json",
}

def page_tabs():
    if not INDEX.exists(): return []
    text=INDEX.read_text(encoding="utf-8",errors="ignore")
    return sorted(set(re.findall(r'<div id="(tab-[^"]+)" class="tab-pane',text)))

def build():
    declared={m["id"] for m in MODULES}
    actual=set(page_tabs())
    missing=sorted(actual-declared)
    stale=sorted(declared-actual)
    edges=[]
    for m in MODULES:
        for target in m.get("outputs",[]):
            edges.append({"from":m["id"],"to":target,"type":"feeds"})
    for s in SERVICES:
        for target in s.get("outputs",[]):
            edges.append({"from":s["id"],"to":target,"type":"feeds"})
    learn_counts={}
    for m in MODULES:
        learn_counts[m["learning"]]=learn_counts.get(m["learning"],0)+1
    return {
      "version":"6.1.0",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "mission":"每个模块必须有存在目的、证据输入、学习策略和下游关系；没有这些字段的模块视为架构债务。",
      "audit":{
        "actual_tabs":len(actual),"declared_tabs":len(declared),
        "coverage_ok":not missing and not stale,
        "missing_registry_entries":missing,"stale_registry_entries":stale,
        "learning_modes":learn_counts,
        "orphan_modules":[m["id"] for m in MODULES if not m.get("inputs") or not m.get("outputs")],
      },
      "modules":MODULES,
      "services":SERVICES,
      "artifacts":{k:artifact(v) for k,v in ARTIFACTS.items()},
      "edges":edges,
      "agent_loop":[
        "market/live + macro + external sources",
        "Trend Pulse / Market Context / Company & Options Context",
        "Learning Engine / Situation Memory",
        "V6 Research Planner",
        "V6.2 Research Executor",
        "research execution + Decision Journal",
        "Outcome Validation / Failure Attribution / Method Memory",
        "V7 Candidate + Shadow Brain",
        "Promotion Gate",
        "Production Brain"
      ],
      "principles":[
        "不是所有模块都应该学习；确定性计算器与临时输入必须避免污染训练记忆。",
        "任何学习模块都必须有可回看的结果标签，否则只能算自动化而不是学习。",
        "私有持仓学习留在受保护层，不导出到账户外的公开静态文件。",
        "模块之间通过显式证据和记忆连接，不允许同一事实在多个模块被重复解释成独立证据。",
        "V7可以优化研究过程和排序，但不能未经批准修改正式交易阈值或下单。"
      ]
    }

def main():
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["audit"],ensure_ascii=False))
    if not out["audit"]["coverage_ok"]:
        raise SystemExit("module registry does not cover every first-level tab")
if __name__=="__main__": main()
