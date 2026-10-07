#!/usr/bin/env python3
"""V6.14 Source Reading Memory (research-only, free-first).

Transforms already-collected Source Intelligence into structured propositions:
- fact: directly represented source facts/actions/declared levels
- author_view: attributable opinion/judgment
- trigger: explicit condition that can activate a plan
- invalidation: explicit exit/failure/invalidating condition
- testable_rule: a source-derived rule with enough structure for later validation
- non_testable_view: useful context that is not yet objectively testable

This module does not use a paid LLM API. It operates only on source text and
existing structured fields. It does not infer hidden intent, invent thresholds,
or change production trading rules.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"docs"/"data"/"source_intelligence.json"
OUT=ROOT/"docs"/"research"/"source_reading_memory.json"
VERSION="6.14.7"

VIEW_HINTS=(
    "认为","觉得","看好","看坏","可能","应该","预计","预期","判断","猜","倾向",
    "i think","i believe","could","should","expect","likely","maybe","probably",
)
INVALID_HINTS=(
    "止损","失效","跌破","卖出线","退出","清仓","砍掉","break below","invalidate",
    "stop loss","exit if","close if","sell if","clear if","market breakdown",
)
TRIGGER_HINTS=(
    "突破","站上","跌破","回踩","如果","若","当","才考虑","触发","breakout","hold above",
    "above ma","below ma","if ","when ","entry",
)

PROSE_CONDITION_PATTERNS=(
    ("price_above_ma50", r"(?:股价|价格|price)?.{0,12}(?:站上|突破|above).{0,8}ma\s*50", True),
    ("price_below_ma50", r"(?:股价|价格|price)?.{0,16}(?:跌破|跌回|回落到|below).{0,10}ma\s*50", True),
    ("ma50_hold_two_sessions", r"(?:连续\s*(?:两|2)\s*(?:个)?(?:交易日|天).{0,16}(?:站上|守住|高于).{0,8}ma\s*50|ma\s*50.{0,24}连续\s*(?:两|2)\s*(?:个)?(?:交易日|天).{0,12}(?:站上|守住|高于|不破)?)", True),
    ("supertrend_bullish", r"supertrend.{0,16}(?:翻多|转多|bull)", True),
    ("macd_hist_positive", r"(?:macd.{0,12}(?:柱|hist)|(?:柱状图|histogram).{0,12}macd).{0,16}(?:转正|正值|positive)", True),
    ("ppo_above_signal", r"ppo.{0,20}(?:上穿|高于|超过|cross(?:es|ed)?\s+above).{0,12}signal", False),
    ("ppo_hist_positive", r"(?:ppo.{0,12}(?:柱|histogram)|histogram.{0,12}ppo).{0,16}(?:转正|正值|positive)", False),
    ("tcds_cross_zero", r"tcds.{0,28}(?:由负(?:值)?(?:转正|回升)|回到\s*(?:0|零)|转正|cross(?:es|ed)?\s+(?:0|zero))", False),
)

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def clean_text(value,limit=260):
    text=re.sub(r"\s+"," ",str(value or "")).strip()
    return text[:limit]

def prop_id(source_id,kind,text):
    raw=f"{source_id}|{kind}|{text}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:18]
def extractor_input_payload(row):
    """Exact normalized fields consumed by record_memory()."""
    return {
        "id":row.get("id"),
        "url":row.get("url"),
        "title":row.get("title"),
        "excerpt":row.get("excerpt"),
        "source":row.get("source"),
        "source_kind":row.get("source_kind"),
        "author":row.get("author"),
        "published_at":row.get("published_at"),
        "symbols":row.get("symbols") or [],
        "primary_symbols":row.get("primary_symbols") or [],
        "symbol_attribution":row.get("symbol_attribution") or [],
        "topics":row.get("topics") or [],
        "operations":row.get("operations") or [],
        "portfolio_rules":row.get("portfolio_rules") or [],
        "lessons":row.get("lessons") or [],
        "method_signals":row.get("method_signals") or [],
        "content_quality":row.get("content_quality"),
        "content_provider":row.get("content_provider"),
        "content_origin":row.get("content_origin"),
        "rule_candidate_allowed":row.get("rule_candidate_allowed"),
    }

def extractor_input_hash(row):
    raw=json.dumps(extractor_input_payload(row),ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def add(props,source_id,kind,text,confidence="medium",testable=False,evidence=None):
    text=clean_text(text)
    if not text:return
    key=(kind,text)
    if any((x["kind"],x["text"])==key for x in props):return
    props.append({
        "proposition_id":prop_id(source_id,kind,text),
        "kind":kind,
        "text":text,
        "confidence":confidence,
        "testable":bool(testable),
        "evidence":evidence or {},
    })

def sentence_candidates(text):
    if not text:return []
    parts=re.split(r"(?<=[。！？!?;；])\s*|\n+",str(text))
    return [clean_text(x,300) for x in parts if clean_text(x,300)]

def explicit_method_candidates(op,row=None):
    """Map a structured operation to method categories using operation semantics.

    Article topics are intentionally ignored here. One structured operation may
    map to multiple methods only when its own fields/actions/conditions prove it.
    """
    row=row or {}
    actions={str(x).lower() for x in (op.get("actions") or [])}
    conditions=" ".join(str(x).lower() for x in (op.get("conditions") or []))
    text=" ".join([
        str(op.get("strategy") or "").lower(),
        str(op.get("option_type") or "").lower(),
        str(row.get("title") or "").lower(),
    ])
    out=[]
    if "sell_put" in actions or op.get("sell_put_strike") is not None:
        out.append("Sell Put")
    sizing={"buy","add","trim","trim_half","sell","clear","planned_buy","planned_sell"}
    has_plan_level=any(op.get(k) is not None for k in ("entry_1","entry_2","entry_below","exit_line","target_range"))
    if actions & sizing or has_plan_level:
        out.append("仓位与加减仓")
    if "leap" in text or any("leap" in x for x in actions):
        out.append("LEAPS")
    if any(k in conditions for k in ("trend","breakout","ma20","ma21","ma50","tcds","supertrend")):
        out.append("趋势确认")
    return out


def condition_semantic_role(condition_id, evidence_text, article_text=""):
    """Classify only explicit temporal/lifecycle language from the source.

    This does not invent a lookback window. It preserves whether a condition is
    described as a prior observation, current invalidation/failure, or future
    confirmation so downstream replay cannot flatten them into one AND clause.
    """
    text=(" ".join([str(evidence_text or ""),str(article_text or "")])).lower()
    if condition_id=="price_below_ma50" and any(k in text for k in ("随后","又跌回","重新回到偏弱","false break","假突破","失败")):
        return "invalidation"
    if condition_id in {"price_above_ma50","supertrend_bullish","macd_hist_positive","ppo_above_signal","ppo_hist_positive","tcds_cross_zero"} and any(k in text for k in ("前几天","此前","一度","曾经")):
        return "prior_observation"
    if condition_id in {"price_above_ma50","ma50_hold_two_sessions","supertrend_bullish","macd_hist_positive","ppo_above_signal","ppo_hist_positive","tcds_cross_zero"} and any(k in text for k in ("如果接下来","若接下来","接下来","必须重新","才算","才考虑","等待确认","确认")):
        return "confirmation"
    return "unspecified"

def prose_candidate_rule(row, sentences):
    """Build a source-derived candidate rule from bounded structured signals + prose.

    Upstream method_signals are extracted from full source text before the public
    excerpt is truncated. They remain Research/Shadow evidence only. This layer
    never invents thresholds, periods, or indicator definitions.
    """
    if row.get("rule_candidate_allowed") is False:
        return None
    declared_primary=[str(x) for x in (row.get("primary_symbols") or []) if str(x)]
    all_symbols=[str(x) for x in (row.get("symbols") or []) if str(x)]
    symbols=declared_primary if declared_primary else (all_symbols if len(all_symbols)==1 else [])
    if len(symbols)!=1:
        return None
    found=[]
    raw=[]
    upstream_state=None
    for sig in row.get("method_signals") or []:
        if not isinstance(sig,dict) or not sig.get("condition_id"):
            continue
        cid=str(sig.get("condition_id"))
        if cid not in [x["condition_id"] for x in found]:
            found.append({"condition_id":cid,"machine_ready":bool(sig.get("machine_ready"))})
        snippet=clean_text(sig.get("evidence_excerpt"),180)
        if snippet:raw.append(snippet)
        if not upstream_state and sig.get("state_hint"):
            upstream_state=str(sig.get("state_hint"))
    for sent in sentences:
        low=sent.lower()
        for cid,pattern,machine_ready in PROSE_CONDITION_PATTERNS:
            if re.search(pattern,low,re.I):
                if cid not in [x["condition_id"] for x in found]:
                    found.append({
                        "condition_id":cid,
                        "machine_ready":bool(machine_ready),
                    })
                raw.append(sent)
    if not found:
        return None
    article_text=" ".join(sentences)
    for item in found:
        cid=item["condition_id"]
        matching=[x for x in raw if cid.replace("_"," ")[:8] in str(x).lower()]
        # Pattern-specific matching is more reliable than token matching for MA50.
        if "ma50" in cid:
            matching=[x for x in raw if re.search(r"ma\s*50",str(x),re.I)]
        evidence_text=" ".join(matching or raw)
        item["semantic_role"]=condition_semantic_role(cid,evidence_text,article_text)
    state_hint=upstream_state
    prose=article_text.lower()
    if "false break" in prose or "假突破" in prose or "early entry 失败" in prose:
        state_hint="RISK"
    elif not state_hint and ("early entry" in prose or "早期介入" in prose or "早期阶段" in prose):
        state_hint="EARLY_ENTRY"
    elif not state_hint and ("confirmed entry" in prose or "趋势确认" in prose or "确认突破" in prose):
        state_hint="CONFIRMATION"
    elif not state_hint and "失效" in prose:
        state_hint="RISK"
    unsupported=[x["condition_id"] for x in found if not x["machine_ready"]]
    readiness="machine_ready" if not unsupported else "partial_needs_definition"
    return {
        "symbols":symbols,
        "conditions":found,
        "state_hint":state_hint,
        "machine_readiness":readiness,
        "needs_definition":unsupported,
        "raw_evidence":list(dict.fromkeys(raw))[:6],
        "source_derived_only":True,
    }

def explicit_rule_from_operation(op):
    fields={}
    for k in ("entry_1","entry_2","entry_below","exit_line","sell_put_strike"):
        if op.get(k) is not None:fields[k]=op.get(k)
    if op.get("target_range"):fields["target_range"]=op.get("target_range")
    conditions=[clean_text(x,180) for x in (op.get("conditions") or []) if clean_text(x,180)]
    actions=[str(x) for x in (op.get("actions") or []) if str(x)]
    if not fields and not conditions and not actions:return None
    return {"fields":fields,"conditions":conditions,"actions":actions}

def record_memory(row):
    sid=str(row.get("id") or row.get("url") or row.get("title") or "source")
    props=[]
    operations=row.get("operations") or []

    # Structured operations are the highest-confidence source-derived evidence.
    for i,op in enumerate(operations):
        owner=op.get("attribution") or "unconfirmed_author_context"
        symbols=op.get("symbols") or row.get("symbols") or []
        sym="/".join(symbols) if symbols else "未指明标的"
        actions=op.get("actions") or []
        if actions:
            add(props,sid,"fact",f"{sym}：来源记录动作 {' / '.join(map(str,actions))}",
                "high" if owner in {"author_action","author_plan"} else "medium",
                False,{"operation_index":i,"attribution":owner})
        for key,label in (
            ("entry_1","第一档"),("entry_2","第二档"),("entry_below","条件价"),
            ("exit_line","退出线"),("sell_put_strike","Sell Put 行权价"),
        ):
            if op.get(key) is not None:
                add(props,sid,"fact",f"{sym}：{label} {op.get(key)}","high",True,
                    {"operation_index":i,"field":key,"attribution":owner})
        if op.get("target_range"):
            add(props,sid,"fact",f"{sym}：目标区间 {op.get('target_range')}","high",True,
                {"operation_index":i,"field":"target_range","attribution":owner})

        for cond in op.get("conditions") or []:
            cond=clean_text(cond,220)
            if cond:
                add(props,sid,"trigger",f"{sym}：{cond}","high",True,
                    {"operation_index":i,"attribution":owner})

        if op.get("exit_line") is not None:
            add(props,sid,"invalidation",f"{sym}：触及/越过退出线 {op.get('exit_line')}","high",True,
                {"operation_index":i,"field":"exit_line","attribution":owner})

        rule=explicit_rule_from_operation(op)
        source_rule_allowed = row.get("rule_candidate_allowed") is not False
        if rule and owner in {"author_action","author_plan"} and source_rule_allowed:
            method_candidates=explicit_method_candidates(op,row)
            add(props,sid,"testable_rule",f"{sym}：结构化操作规则 {json.dumps(rule,ensure_ascii=False,sort_keys=True)}",
                "high",True,{
                    "operation_index":i,
                    "attribution":owner,
                    "rule":rule,
                    "method_candidates":method_candidates,
                })

    # Portfolio rules / lessons are preserved as source claims, not automatically
    # converted into performance evidence.
    for x in row.get("portfolio_rules") or []:
        add(props,sid,"author_view",f"组合规则：{x}","high",False,{"source_field":"portfolio_rules"})
    for x in row.get("lessons") or []:
        add(props,sid,"author_view",f"复盘经验：{x}","high",False,{"source_field":"lessons"})

    # Prose extraction is intentionally conservative. It never creates numeric
    # thresholds unless they already appear in structured operations above.
    prose="\n".join([str(row.get("title") or ""),str(row.get("excerpt") or "")])
    prose_sentences=sentence_candidates(prose)
    for sent in prose_sentences:
        low=sent.lower()
        classified=False
        if any(k in low for k in INVALID_HINTS):
            add(props,sid,"invalidation",sent,"medium",False,{"source_field":"prose","classification":"explicit_invalidation_language"})
            classified=True
        elif any(k in low for k in TRIGGER_HINTS) and re.search(r"\b(?:ma\d+|rsi|supertrend|breakout|support|resistance)\b|均线|突破|跌破|站上|回踩",low,re.I):
            add(props,sid,"trigger",sent,"medium",False,{"source_field":"prose","classification":"explicit_trigger_language"})
            classified=True
        elif any(k in low for k in VIEW_HINTS):
            add(props,sid,"author_view",sent,"medium",False,{"source_field":"prose","classification":"author_judgment_language"})
            classified=True
        if not classified:
            # Preserve residual source meaning without pretending it is objective
            # evidence. This is intentionally not a testable_rule and never
            # receives invented thresholds or hidden intent.
            add(props,sid,"non_testable_view",sent,"low",False,{"source_field":"prose","classification":"residual_context"})

    candidate=prose_candidate_rule(row,prose_sentences)
    if candidate:
        evidence_text=" / ".join(candidate.get("raw_evidence") or [])
        add(props,sid,"candidate_rule",
            f"{'/'.join(candidate['symbols'])}：来源叙述形成候选规则 {evidence_text}",
            "medium",False,{"candidate_rule":candidate})

    testable=[x for x in props if x["kind"]=="testable_rule"]
    candidates=[x for x in props if x["kind"]=="candidate_rule"]
    return {
        "source_id":sid,
        "extractor_input_hash":extractor_input_hash(row),
        "extractor_input_scope":"exact_fields_consumed_by_source_reading_memory",
        "source":row.get("source"),
        "source_kind":row.get("source_kind"),
        "author":row.get("author"),
        "published_at":row.get("published_at"),
        "title":row.get("title"),
        "url":row.get("url"),
        "symbols":row.get("symbols") or [],
        "primary_symbols":row.get("primary_symbols") or [],
        "symbol_attribution":row.get("symbol_attribution") or [],
        "topics":row.get("topics") or [],
        "content_quality":row.get("content_quality"),
        "content_provider":row.get("content_provider"),
        "content_origin":row.get("content_origin"),
        "rule_candidate_allowed":row.get("rule_candidate_allowed"),
        "propositions":props,
        "testable_rule_count":len(testable),
        "candidate_rule_count":len(candidates),
        "reading_state":"testable" if testable else ("candidate_rule" if candidates else ("structured_context" if props else "insufficient_content")),
    }

def build(source):
    memories=[record_memory(r) for r in (source.get("records") or [])]
    kind_counts=Counter()
    author_counts=Counter()
    topic_counts=Counter()
    testable_by_topic=defaultdict(int)
    testable_by_method=defaultdict(int)
    for m in memories:
        for p in m["propositions"]:
            kind_counts[p["kind"]]+=1
            if p.get("kind")=="testable_rule":
                for method in ((p.get("evidence") or {}).get("method_candidates") or []):
                    testable_by_method[method]+=1
        if m["testable_rule_count"]:
            author_counts[m.get("author") or "unknown"]+=m["testable_rule_count"]
            # Topic association is descriptive context only; downstream Method
            # Memory must never treat this as method attribution.
            for t in m.get("topics") or []:testable_by_topic[t]+=m["testable_rule_count"]
        for t in m.get("topics") or []:topic_counts[t]+=1

    return {
        "version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "mode":"research_only_free_first",
        "source_intelligence_version":source.get("version"),
        "counts":{
            "source_records":len(memories),
            "records_with_testable_rules":sum(1 for m in memories if m["testable_rule_count"]),
            "testable_rules":sum(m["testable_rule_count"] for m in memories),
            "records_with_candidate_rules":sum(1 for m in memories if m.get("candidate_rule_count")),
            "candidate_rules":sum(m.get("candidate_rule_count",0) for m in memories),
            "propositions":sum(len(m["propositions"]) for m in memories),
            "by_kind":dict(kind_counts),
        },
        "testable_by_author":dict(author_counts),
        "testable_by_topic":dict(testable_by_topic),
        "testable_by_method":dict(testable_by_method),
        "topic_record_counts":dict(topic_counts),
        "records":memories[:800],
        "guardrails":[
            "No paid LLM API is used by this module.",
            "Only source text and existing structured fields are transformed.",
            "Article topic alone never becomes a testable rule.",
            "Only explicit structured operations owned by the author can create testable_rule records.",
            "Sources explicitly marked rule_candidate_allowed=false can never create testable_rule records.",
            "Prose candidate rules are source-derived Research/Shadow artifacts only; they never enter Rule Registry or Promotion until separately compiled and validated.",
            "Unsupported indicators such as source-specific TCDS/PPO definitions remain needs_definition and cannot be treated as machine-ready conditions.",
            "Prose triggers, invalidations and views remain context until later structured validation.",
            "Unclassified source prose is preserved as non_testable_view instead of being discarded or promoted.",
            "Every source record carries a hash of the exact normalized fields consumed by this extractor.",
            "No proposition can change production rules, positions, allocations or orders.",
        ],
    }

def main():
    source=load(SRC,{"records":[]})
    out=build(source)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"version":out["version"],"counts":out["counts"]},ensure_ascii=False))

if __name__=="__main__":
    main()
