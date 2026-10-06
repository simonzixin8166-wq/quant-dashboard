#!/usr/bin/env python3
"""Build evidence-grounded Auto Thesis drafts without external calls.

The engine never overwrites private user notes. It converts already-fetched
official/event evidence into a public draft artifact that the browser may use
to prefill only empty research-card fields.
"""
from __future__ import annotations
import hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OFFICIAL=ROOT/"docs"/"research"/"official_evidence.json"
EVENTS=ROOT/"docs"/"research"/"event_evidence.json"
OUT=ROOT/"docs"/"research"/"auto_thesis_drafts.json"
VERSION="6.15.1"

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def clean(s,n=260):
    s=re.sub(r"\s+"," ",str(s or "")).strip()
    return s[:n]

def digest(obj):
    raw=json.dumps(obj,ensure_ascii=False,sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]

def build_symbol(symbol,off,event):
    filings=(off or {}).get("filings") or []
    news=(event or {}).get("news") or []
    latest_filings=filings[:3]
    latest_news=news[:4]
    official_bits=[]
    catalysts=[]
    risks=[]
    for f in latest_filings:
        form=f.get("form") or "filing";date=f.get("filing_date") or ""
        official_bits.append(f"{form} {date}".strip())
        excerpt=" ".join(f.get("excerpts") or [])
        lo=excerpt.lower()
        if form=="8-K" and ("results of operations" in lo or "reported results" in lo):
            catalysts.append(f"最新 {form} 涉及经营/财务结果披露（{date}），需结合原文核验是否改变增长路径。")
        if form=="10-K":
            if "risk factors" in lo: risks.append(f"最新 10-K（{date}）包含 Risk Factors，系统建议在重大事件后复核具体风险条目。")
            if "liquidity" in lo or "cash and cash equivalents" in lo: official_bits.append("官方年报包含流动性/现金信息")
    for x in latest_news:
        title=clean(x.get("title"),180);pub=x.get("publisher") or "media"
        if title: catalysts.append(f"{pub}: {title}")
    peer=(event or {}).get("peer_context") or {}
    peer_note=""
    if peer.get("peer_count"):
        peer_note=f"同业当日方向：{peer.get('direction','unknown')}，样本 {peer.get('peer_count')}。"
    thesis="；".join(official_bits[:4]) or "尚无可用官方证据"
    plan="下一次自动核验：出现新的 10-Q/10-K/8-K、重大事件新闻或观察池新增时重建；不因普通盘中波动重算。"
    invalidation="自动草稿不替代投资判断：若后续官方披露与当前增长/事件叙事冲突，或核心风险显著升级，应重新评估 Thesis。"
    return {
      "symbol":symbol,
      "evidence_hash":digest({"filings":[(x.get("accession"),x.get("filing_date")) for x in latest_filings],"news":[x.get("uuid") for x in latest_news]}),
      "evidence_summary":thesis,
      "catalysts":"\n".join(catalysts[:5]),
      "risks":"\n".join(dict.fromkeys(risks)) if risks else "当前自动证据未提取出可安全概括的具体风险条目；保留为空白优于补猜。",
      "invalidation":invalidation,
      "valuation_note":peer_note,
      "plan":plan,
      "sources":{
        "official":[{"form":x.get("form"),"date":x.get("filing_date"),"url":x.get("url"),"evidence_class":"direct_company"} for x in latest_filings],
        "events":[{"title":clean(x.get("title"),180),"publisher":x.get("publisher"),"published_at":x.get("published_at"),"url":x.get("url"),"evidence_class":"media","source_type":x.get("source_type")} for x in latest_news],
        "peer_context":{"evidence_class":"peer","direction":peer.get("direction"),"peer_count":peer.get("peer_count",0)}
      },
      "evidence_policy":"Only direct_company evidence may directly trigger thesis review; media/peer/sector/macro remain supporting context.",
      "guardrail":"Evidence-grounded draft only. Never overwrites user notes; missing evidence stays explicit.",
    }

def build():
    official=load(OFFICIAL);events=load(EVENTS)
    symbols=sorted(set((official.get("symbols") or {}))|set((events.get("symbols") or {})))
    rows={}
    for s in symbols:
        rows[s]=build_symbol(s,(official.get("symbols") or {}).get(s,{}),(events.get("symbols") or {}).get(s,{}))
    return {
      "version":VERSION,
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "mode":"evidence_grounded_autofill_draft",
      "external_requests":0,
      "symbols":rows,
      "counts":{"symbols":len(rows)},
      "guardrails":[
        "Uses only already-fetched official/event evidence.",
        "Never overwrites private user research notes.",
        "Only fills empty fields in the browser.",
        "Rebuild on evidence changes; ordinary intraday price moves do not trigger research regeneration."
      ]
    }

def main():
    out=build();OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
