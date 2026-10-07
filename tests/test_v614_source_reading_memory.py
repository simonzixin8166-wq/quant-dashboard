import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import source_reading_memory as srm
import method_memory_engine as mm
import system_status_center as ssc

source={
 "version":2,
 "records":[
  {
   "id":"r1","source":"wenxuecity","source_kind":"forum","author":"A","published_at":"2026-10-01",
   "title":"我准备分两档买入 QQQ","url":"u1","symbols":["QQQ"],"topics":["仓位与加减仓"],
   "excerpt":"如果站上MA20再考虑第二档；跌破退出线就离场。",
   "operations":[{
      "symbols":["QQQ"],"actions":["planned_buy"],"entry_1":700,"entry_2":680,"exit_line":650,
      "conditions":["站上 MA20 再考虑第二档"],"attribution":"author_plan"
   }],
   "portfolio_rules":[],"lessons":[]
  },
  {
   "id":"r2","source":"wenxuecity","source_kind":"forum","author":"B","published_at":"2026-10-01",
   "title":"谈 Sell Put","url":"u2","symbols":["NVDA"],"topics":["Sell Put"],
   "excerpt":"我觉得NVDA长期不错。",
   "operations":[],
   "portfolio_rules":[],"lessons":[]
  },
  {
   "id":"r3","source":"wenxuecity","source_kind":"forum","author":"C","published_at":"2026-10-01",
   "title":"第三方例子","url":"u3","symbols":["TSLA"],"topics":["仓位与加减仓"],
   "excerpt":"",
   "operations":[{
      "symbols":["TSLA"],"actions":["buy"],"entry_1":300,"attribution":"third_party_example"
   }],
   "portfolio_rules":[],"lessons":[]
  },
  {
   "id":"r4","source":"wenxuecity","source_kind":"forum","author":"D","published_at":"2026-10-01",
   "title":"趋势修复","url":"u4","symbols":["AMD"],"topics":["趋势确认"],
   "excerpt":"如果突破MA50，可能进入趋势修复。",
   "operations":[],"portfolio_rules":[],"lessons":[]
  },
  {
   "id":"r5","source":"youtube","source_kind":"video","author":"老李玩钱","published_at":"2026-10-05",
   "title":"第三方结构化摘要","url":"u5","symbols":["QQQ"],"topics":["仓位与加减仓"],
   "excerpt":"摘要声称QQQ分两档建仓。",
   "content_quality":"Q3","content_provider":"stockvoice.cmoney.tw",
   "content_origin":"structured_summary","rule_candidate_allowed":False,
   "operations":[{
      "symbols":["QQQ"],"actions":["planned_buy"],"entry_1":700,"entry_2":680,
      "attribution":"author_plan"
   }],
   "portfolio_rules":[],"lessons":[]
  }
 ]
}

out=srm.build(source)
assert out["version"]=="6.14.7"
assert out["mode"]=="research_only_free_first"
assert out["counts"]["source_records"]==5
assert out["counts"]["records_with_testable_rules"]==1
assert out["counts"]["testable_rules"]==1

r1=next(x for x in out["records"] if x["source_id"]=="r1")
kinds=[x["kind"] for x in r1["propositions"]]
assert "fact" in kinds
assert "trigger" in kinds
assert "invalidation" in kinds
assert "testable_rule" in kinds
rule=next(x for x in r1["propositions"] if x["kind"]=="testable_rule")
assert rule["testable"] is True
assert rule["evidence"]["attribution"]=="author_plan"
assert rule["evidence"]["rule"]["fields"]["entry_1"]==700
assert rule["evidence"]["rule"]["fields"]["exit_line"]==650
assert set(rule["evidence"]["method_candidates"])=={"仓位与加减仓","趋势确认"}
assert out["testable_by_method"]["仓位与加减仓"]==1
assert out["testable_by_method"]["趋势确认"]==1
assert out["testable_by_method"].get("Sell Put",0)==0
# Topic association is retained only as descriptive context.
assert out["testable_by_topic"]["仓位与加减仓"]==1

# Topic alone never creates a direct/testable rule.
r2=next(x for x in out["records"] if x["source_id"]=="r2")
assert r2["testable_rule_count"]==0
assert not any(x["kind"]=="testable_rule" for x in r2["propositions"])

# A third-party structured example may be preserved as facts but cannot become
# an author-owned testable rule.
r3=next(x for x in out["records"] if x["source_id"]=="r3")
assert any(x["kind"]=="fact" for x in r3["propositions"])
assert r3["testable_rule_count"]==0

# Prose technical condition can remain a contextual trigger, but it is not
# silently promoted to a testable rule.
r4=next(x for x in out["records"] if x["source_id"]=="r4")
tr=next(x for x in r4["propositions"] if x["kind"]=="trigger")
assert tr["testable"] is False
assert r4["testable_rule_count"]==0
assert r4["candidate_rule_count"]==1
cand=next(x for x in r4["propositions"] if x["kind"]=="candidate_rule")
assert cand["testable"] is False
cr=cand["evidence"]["candidate_rule"]
assert cr["symbols"]==["AMD"]
assert any(x["condition_id"]=="price_above_ma50" and x["machine_ready"] for x in cr["conditions"])
assert cr["machine_readiness"]=="machine_ready"

# A Q3/Q4/Q5 source explicitly marked rule_candidate_allowed=false remains
# context-only even if an upstream feed accidentally supplies an author_plan operation.
r5=next(x for x in out["records"] if x["source_id"]=="r5")
assert any(x["kind"]=="fact" for x in r5["propositions"])
assert r5["testable_rule_count"]==0
assert not any(x["kind"]=="testable_rule" for x in r5["propositions"])
assert r5["content_quality"]=="Q3"
assert r5["content_provider"]=="stockvoice.cmoney.tw"
assert r5["rule_candidate_allowed"] is False

# Source Reading candidates flow into Method Memory as candidates only, never
# as direct performance before an eligible triggered outcome exists.
method_source={
 "counts":{"records":1},
 "records":[{"url":"u1","author":"A","topics":["仓位与加减仓"],"title":"计划","excerpt":""}]
}
method_validation={"events":[]}
method=mm.build(method_source,method_validation,histories={},evidence={},reading=out)
position=next(x for x in method["methods"] if x["method"]=="仓位与加减仓")
assert method["version"]=="6.14.2"
assert method["counts"]["source_reading_testable_rules"]==1
assert position["source_reading"]["testable_rule_candidates"]==1
trend=next(x for x in method["methods"] if x["method"]=="趋势确认")
assert trend["source_reading"]["testable_rule_candidates"]==1
assert position["source_reading"]["state"]=="candidate_rules_available"
assert position["direct_validated_events"]==0
assert position["performance"] is None
assert position["status"]=="context_only"

# Public artifact contains no production mutation path.
blob=json.dumps(out,ensure_ascii=False).lower()
for forbidden in ("automatic_order","position_size_change","production_threshold_change"):
    assert forbidden not in blob

# Status Center classification remains research-only.
from tempfile import TemporaryDirectory
with TemporaryDirectory() as td:
    p=Path(td)/"source_reading_memory.json"
    p.write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat()}),encoding="utf-8")
    h=ssc.artifact_health("source_reading_memory",p,datetime.now(timezone.utc))
    assert h["decision_eligible"] is False
    assert h["participation"]=="research_only"

ui=(ROOT/"docs"/"assets"/"knowledge.js").read_text(encoding="utf-8")
assert "research/source_reading_memory.json" in ui
assert "来源阅读记忆" in ui
assert "可验证规则" in ui
assert "Research Only，不自动改变交易规则。" in ui

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.14 Source Reading Memory" in workflow
assert workflow.index("Build Source Intelligence Learning") < workflow.index("Build V6.14 Source Reading Memory")
assert workflow.index("Build V6.14 Source Reading Memory") < workflow.index("Validate External Source Outcomes")
assert "module_failure_marker.py source_reading_memory" in workflow

manifest=(ROOT/"scripts/generate_build_manifest.py").read_text(encoding="utf-8")
assert "research/source_reading_memory.json" in manifest

# Narrative methods become explicit candidate rules without inventing the
# source-specific indicator definition. They remain Research/Shadow only.
narrative=srm.record_memory({
 "id":"n1","source":"wenxuecity","source_kind":"blog","author":"yifan99",
 "published_at":"2026-10-06","title":"AMZN趋势形成","url":"n1","symbols":["AMZN"],
 "topics":["趋势确认"],
 "excerpt":"TCDS由负值回升并转正，PPO上穿Signal，价格站上MA50。仍处于Early Entry，等待确认。",
 "operations":[],"portfolio_rules":[],"lessons":[]
})
nc=next(x for x in narrative["propositions"] if x["kind"]=="candidate_rule")
nr=nc["evidence"]["candidate_rule"]
ids={x["condition_id"] for x in nr["conditions"]}
assert {"tcds_cross_zero","ppo_above_signal","price_above_ma50"} <= ids
assert nr["machine_readiness"]=="partial_needs_definition"
assert set(nr["needs_definition"])=={"tcds_cross_zero","ppo_above_signal"}
assert nr["state_hint"]=="EARLY_ENTRY"
assert narrative["testable_rule_count"]==0
assert narrative["candidate_rule_count"]==1

# Full-text method_signals can supply later article conditions even when the
# public excerpt ends before PPO/MA50. They remain candidate_rule only.
bounded=srm.record_memory({
 "id":"n2","source":"wenxuecity","source_kind":"blog","author":"yifan99",
 "published_at":"2026-10-06","title":"Amazon，要突破了？","url":"n2","symbols":["AMZN"],
 "topics":["趋势确认"],"excerpt":"TCDS终于回到0","operations":[],"portfolio_rules":[],"lessons":[],
 "method_signals":[
   {"condition_id":"tcds_cross_zero","machine_ready":False,"evidence_excerpt":"TCDS 从负值持续回升到 0","evidence_hash":"a"*64,"source_derived_only":True,"state_hint":"EARLY_ENTRY"},
   {"condition_id":"ppo_above_signal","machine_ready":False,"evidence_excerpt":"PPO 向上交叉 Signal","evidence_hash":"b"*64,"source_derived_only":True,"state_hint":"EARLY_ENTRY"},
   {"condition_id":"ppo_hist_positive","machine_ready":False,"evidence_excerpt":"Histogram 从负值转正","evidence_hash":"c"*64,"source_derived_only":True,"state_hint":"EARLY_ENTRY"},
   {"condition_id":"price_above_ma50","machine_ready":True,"evidence_excerpt":"价格站上 MA50","evidence_hash":"d"*64,"source_derived_only":True,"state_hint":"EARLY_ENTRY"},
   {"condition_id":"ma50_hold_two_sessions","machine_ready":True,"evidence_excerpt":"连续两个交易日守住 MA50","evidence_hash":"e"*64,"source_derived_only":True,"state_hint":"EARLY_ENTRY"},
 ]
})
bc=next(x for x in bounded["propositions"] if x["kind"]=="candidate_rule")
br=bc["evidence"]["candidate_rule"]
bids={x["condition_id"] for x in br["conditions"]}
assert {"tcds_cross_zero","ppo_above_signal","ppo_hist_positive","price_above_ma50","ma50_hold_two_sessions"} <= bids
assert set(br["needs_definition"]) >= {"tcds_cross_zero","ppo_above_signal","ppo_hist_positive"}
assert br["state_hint"]=="EARLY_ENTRY"
assert any("PPO 向上交叉 Signal" in x for x in br["raw_evidence"])
assert bounded["testable_rule_count"]==0

print("PASS V6.14.7 source reading propositions / bounded full-text signals / research-only")


# False Break prose must preserve lifecycle roles instead of flattening prior,
# current invalidation, and future confirmation into one simultaneous AND rule.
false_break=srm.record_memory({
 "id":"fb1","source":"wenxuecity","source_kind":"blog","author":"yifan99",
 "published_at":"2026-09-29","title":"AMZN 一次向上 False Break（假突破）","url":"fb1","symbols":["AMZN"],
 "topics":["趋势确认"],
 "excerpt":"前几天价格一度重新站上 MA50，随后没有形成持续上攻，反而又跌回 MA50 下方。如果接下来价格重新站上 MA50，而且能够连续两天守住，才算重新确认。",
 "operations":[],"portfolio_rules":[],"lessons":[]
})
fc=next(x for x in false_break["propositions"] if x["kind"]=="candidate_rule")
fr=fc["evidence"]["candidate_rule"]
roles={x["condition_id"]:x.get("semantic_role") for x in fr["conditions"]}
assert fr["state_hint"]=="RISK"
assert roles["price_below_ma50"]=="invalidation"
assert roles["ma50_hold_two_sessions"]=="confirmation"
assert roles["price_above_ma50"]=="prior_observation"
print("PASS false-break temporal roles preserved")


# Multi-symbol prose uses only Source Intelligence primary_subject scope.
multi=srm.record_memory({
 "id":"multi1","source":"wenxuecity","source_kind":"forum","author":"A",
 "published_at":"2026-10-07","title":"AMZN 与 QQQ 对比","url":"multi1",
 "symbols":["AMZN","QQQ"],"primary_symbols":["AMZN"],
 "symbol_attribution":[
   {"symbol":"AMZN","role":"primary_subject","confidence":"high"},
   {"symbol":"QQQ","role":"comparison_peer","confidence":"medium"}
 ],
 "topics":["趋势确认"],
 "excerpt":"AMZN 价格站上 MA50，相比 QQQ 仍偏弱。",
 "operations":[],"portfolio_rules":[],"lessons":[]
})
mc=next(x for x in multi["propositions"] if x["kind"]=="candidate_rule")
mr=mc["evidence"]["candidate_rule"]
assert mr["symbols"]==["AMZN"]
assert multi["primary_symbols"]==["AMZN"]

# Ambiguous multi-symbol prose without a primary stays context-only.
amb=srm.record_memory({
 "id":"multi2","source":"wenxuecity","source_kind":"forum","author":"A",
 "published_at":"2026-10-07","title":"AMZN QQQ 趋势","url":"multi2",
 "symbols":["AMZN","QQQ"],"primary_symbols":[],
 "topics":["趋势确认"],"excerpt":"价格站上 MA50。","operations":[],"portfolio_rules":[],"lessons":[]
})
assert amb["candidate_rule_count"]==0
print("PASS primary-subject-scoped prose candidates")


# Parameterized indicators unlock only from explicit source-authored parameters
# plus calculation basis. Defaults are never substituted.
explicit=srm.record_memory({
 "id":"param1","source":"wenxuecity","source_kind":"blog","author":"A",
 "published_at":"2026-10-07","title":"明确参数","url":"param1","symbols":["AAA"],
 "topics":["趋势确认"],
 "excerpt":"MACD(12,26,9) 使用 EMA，柱状图转正；PPO(12,26,9) 使用 EMA，上穿 Signal；Supertrend 采用 ATR10、3倍、Wilder，当前翻多。",
 "operations":[],"portfolio_rules":[],"lessons":[]
})
pc=next(x for x in explicit["propositions"] if x["kind"]=="candidate_rule")
pr=pc["evidence"]["candidate_rule"]
defs={x["condition_id"]:x.get("explicit_definition") for x in pr["conditions"]}
assert defs["macd_hist_positive"]["formula_id"]=="ema_macd"
assert defs["macd_hist_positive"]["fast_period"]==12
assert defs["ppo_above_signal"]["formula_id"]=="ema_ppo"
assert defs["supertrend_bullish"]["formula_id"]=="supertrend_atr_band"
assert defs["supertrend_bullish"]["atr_smoothing"]=="Wilder_RMA"
assert pr["machine_readiness"]=="machine_ready"

no_basis=srm.record_memory({
 "id":"param2","source":"wenxuecity","source_kind":"blog","author":"A",
 "published_at":"2026-10-07","title":"只有参数","url":"param2","symbols":["AAA"],
 "topics":["趋势确认"],"excerpt":"MACD(12,26,9) 柱状图转正。","operations":[],"portfolio_rules":[],"lessons":[]
})
nc=next(x for x in no_basis["propositions"] if x["kind"]=="candidate_rule")
nr=nc["evidence"]["candidate_rule"]
macd=next(x for x in nr["conditions"] if x["condition_id"]=="macd_hist_positive")
assert macd.get("explicit_definition") is None
assert macd["machine_ready"] is False
assert "macd_hist_positive" in nr["needs_definition"]
print("PASS explicit-only parameterized indicator parsing")
