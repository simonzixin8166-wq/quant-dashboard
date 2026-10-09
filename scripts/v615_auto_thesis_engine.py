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
THESIS_ARCHIVE=ROOT/"research"/"archive"/"thesis_revisions"
OUT=ROOT/"docs"/"research"/"auto_thesis_drafts.json"
VERSION="6.15.2"

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def clean(s,n=260):
    s=re.sub(r"\s+"," ",str(s or "")).strip()
    return s[:n]

def digest(obj):
    raw=json.dumps(obj,ensure_ascii=False,sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]

ALIASES={"SPCX":["spacex"],"GOOG":["google","alphabet"],"GOOGL":["google","alphabet"],"META":["meta","facebook"],
         "AMZN":["amazon"],"TSLA":["tesla"],"NBIS":["nebius"],"CRWV":["coreweave"],"NOW":["servicenow"],"MU":["micron"],
         "INTC":["intel"],"LITE":["lumentum"],"IREN":["iren"],"SOFI":["sofi"],"MSFT":["microsoft"]}


def news_relevance(symbol,company_name,title):
    """'direct' only when the headline names the company/ticker; Yahoo related_tickers tagging
    alone (e.g. an AMD-vs-ASML piece tagged MSFT) is not evidence about this company."""
    raw=f" {str(title or '')} "
    # Ticker must appear in upper case (NOW/MU/META are ordinary words in lower case).
    if re.search(rf"(?<![A-Za-z0-9]){re.escape(symbol.upper())}(?![A-Za-z0-9])",raw):return "direct"
    # Company names must be capitalised as proper nouns ("Meta", not "the meta trade").
    t=raw
    names={n[:1].upper()+n[1:] for n in ALIASES.get(symbol,[])}
    first=str(company_name or "").split(" ")[0]
    if len(first)>=4 and first.lower() not in {"the","first","global","american","united"}:names.add(first[:1].upper()+first[1:].lower())
    return "direct" if any(re.search(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])",t,flags=0) or
                           re.search(rf"(?<![A-Za-z0-9]){re.escape(n.upper())}(?![A-Za-z0-9])",t) for n in names) else "tagged_only"


def readiness(symbol,latest_filings,direct_news,excluded_news,risks,today=None):
    """Per-symbol 'what we have / what is missing' for an explainable WATCH (never a verified Thesis)."""
    today=today or datetime.now(timezone.utc).date()
    have,missing=[],[]
    periodic=[f for f in latest_filings if f.get("form") in ("10-Q","10-K")]
    if latest_filings:
        f=latest_filings[0];have.append(f"官方披露 {f.get('form')} {f.get('filing_date')}")
    else:
        missing.append("任何官方披露（未进入自动研究覆盖）")
    recent_periodic=None
    for f in periodic:
        try:
            age=(today-datetime.fromisoformat(str(f.get("filing_date"))).date()).days
        except Exception:
            continue
        recent_periodic=(f,age);break
    if recent_periodic and recent_periodic[1]<=120:
        have.append(f"本季/年度业务数据（{recent_periodic[0].get('form')} {recent_periodic[0].get('filing_date')}）")
    else:
        missing.append("近 120 天内的季报/年报业务数据")
    if risks:have.append("年报含 Risk Factors（尚未提炼成具体风险条目）")
    missing.append("具体风险条目（需从原文提炼）")
    missing.append("失效条件（何种情况证明上涨理由错误，需你确认）")
    if direct_news:have.append(f"直接相关新闻 {len(direct_news)} 条")
    else:missing.append("直接相关的近期催化剂")
    dates=[str(f.get("filing_date") or "") for f in latest_filings]+[str(x.get("published_at") or "")[:10] for x in direct_news]
    return {"verified":False,"status":"draft_only" if latest_filings else "no_coverage","have":have,"missing":missing,
            "last_evidence_date":max([d for d in dates if d] or [None]) if dates else None,
            "excluded_tagged_only_news":len(excluded_news),
            "next_trigger":"新的 10-Q/10-K/8-K、直接相关重大新闻，或你写入/更新研究卡"}


def build_symbol(symbol,off,event):
    filings=(off or {}).get("filings") or []
    news=(event or {}).get("news") or []
    latest_filings=filings[:3]
    company=(off or {}).get("company_name") or ""
    tagged=[(x,news_relevance(symbol,company,x.get("title"))) for x in news]
    direct_news=[x for x,r in tagged if r=="direct"]
    excluded_news=[x for x,r in tagged if r!="direct"]
    latest_news=direct_news[:4]
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
      "readiness":readiness(symbol,latest_filings,direct_news,excluded_news,risks),
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

def append_thesis_revisions(out):
    THESIS_ARCHIVE.mkdir(parents=True,exist_ok=True)
    added=0
    for symbol,row in (out.get("symbols") or {}).items():
        path=THESIS_ARCHIVE/f"{symbol}.jsonl"
        prior=[]
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:prior.append(json.loads(line))
                except Exception:continue
        last=prior[-1] if prior else None
        if last and last.get("evidence_hash")==row.get("evidence_hash"):
            continue
        revision={
          "symbol":symbol,
          "revision_at":out.get("generated_at"),
          "evidence_hash":row.get("evidence_hash"),
          "previous_evidence_hash":(last or {}).get("evidence_hash"),
          "evidence_summary":row.get("evidence_summary"),
          "catalysts":row.get("catalysts"),
          "risks":row.get("risks"),
          "invalidation":row.get("invalidation"),
          "valuation_note":row.get("valuation_note"),
          "change_reason":"initial_thesis" if not last else "evidence_hash_changed",
          "source_urls":[
            x.get("url") for bucket in ("official","events")
            for x in ((row.get("sources") or {}).get(bucket) or []) if x.get("url")
          ],
          "production_effect":"none",
        }
        with path.open("a",encoding="utf-8") as f:
            f.write(json.dumps(revision,ensure_ascii=False,sort_keys=True)+"\n")
        added+=1
    return added

def main():
    out=build();OUT.parent.mkdir(parents=True,exist_ok=True)
    out["revision_history_added"]=append_thesis_revisions(out)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({**out["counts"],"revision_history_added":out["revision_history_added"]},ensure_ascii=False))

if __name__=="__main__":main()
