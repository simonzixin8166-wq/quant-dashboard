from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("dla",ROOT/"scripts"/"data_learning_coverage_audit.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

out=m.build()
rows={x["domain"]:x for x in out["domains"]}
assert "blog_forum_video_sources" in rows
assert "official_sec_filings" in rows
assert "financial_fundamentals_xbrl" in rows
assert "news_event_evidence" in rows
assert "market_price_history" in rows
assert "options_opportunity" in rows

assert "auto_thesis_revision_memory" in rows
assert "candidate_shadow_forward" in rows
assert "production_playbook_forward_replay" in rows
assert "operational_system_learning" in rows
assert "regional_cn_hk_learning" in rows
assert "curated_knowledge_base" in rows
# The row keeps its counts under "evidence" (reading "counts" silently yielded 0 until the first real
# Forward outcome matured on 2026-10-16 and broke Daily). Only 20/60/120-session maturity is verified.
fwd=rows["production_playbook_forward_replay"]
mature=(fwd.get("evidence") or {}).get("mature_total") or {}
any_n,verified_n=m.forward_mature_counts(mature)
assert fwd["learning_status"]==("learning_active" if verified_n>0 else "partial_learning")
assert fwd["outcome_feedback"] is (any_n>0)
assert m.forward_mature_counts({"5":1,"20":0,"60":0})==(1,0)
assert m.forward_mature_counts({"5":2,"20":1,"60":0})==(3,1)
assert m.forward_mature_counts({"120":"2","5":None})==(2,2)
assert m.forward_mature_counts(None)==(0,0) and m.forward_mature_counts({"5":"x"})==(0,0)
assert rows["regional_cn_hk_learning"]["learning_status"]=="context_only"
assert rows["financial_fundamentals_xbrl"]["learning_status"] in {"not_implemented","partial_learning","learning_active"}
if rows["financial_fundamentals_xbrl"]["collected"]:
    assert rows["financial_fundamentals_xbrl"]["learning_status"] in {"partial_learning","learning_active"}
if rows["financial_fundamentals_xbrl"]["learning_status"]=="learning_active":
    assert rows["financial_fundamentals_xbrl"]["outcome_feedback"] is True
assert rows["official_sec_filings"]["learning_status"] in {"partial_learning","learning_active"}
assert "canonical_storage" in out["required_contract"]
assert "reconciliation" in out["required_contract"]
assert "reconciliation" in out
rec=out["reconciliation"]
# Same definition as the audit (and its hard gate): an explicit backlog is reported, but it is not balanced.
expected=(
    rec["captured"]>0
    and rec["canonical"]>=rec["captured"]
    and rec["processed"]>=rec["canonical"]
    and rec["backlog"]==0
    and rec["errors"]==0
)
assert rec["balanced"] is expected
# The static checked-in artifacts may be intentionally stale before this
# workflow rebuilds Source Reading. The executable audit later in the same
# pipeline is the hard gate and must finish balanced=true.

# Regression: first real Forward maturity (5-session only) must not break the contract nor count as verified.
def _build_with(mature_total):
    orig=m.load
    def fake(path):
        d=orig(path)
        if str(path).endswith("playbook_outcome_shadow.json"):
            d=dict(d or {});d["mature_total"]=mature_total
        return d
    m.load=fake
    try:return {x["domain"]:x for x in m.build()["domains"]}["production_playbook_forward_replay"]
    finally:m.load=orig
r5=_build_with({"5":1,"20":0,"60":0})
assert r5["learning_status"]=="partial_learning" and r5["outcome_feedback"] is True
assert r5["evidence"]["mature_any"]==1 and r5["evidence"]["mature_verified_20_60_120"]==0
r20=_build_with({"5":3,"20":1,"60":0})
assert r20["learning_status"]=="learning_active" and r20["outcome_feedback"] is True
assert r20["evidence"]["mature_verified_20_60_120"]==1
r0=_build_with({"5":0,"20":0,"60":0})
assert r0["learning_status"]=="partial_learning" and r0["outcome_feedback"] is False
# Regression: an explicit backlog is never reported as balanced.
rb=m.reconciliation(1931,1938,{"counts":{"source_records":1918},"text_enrichment":{"text_unavailable_records":0}},{"fetch_status":"ok"})
assert rb["backlog"]==20 and rb["balanced"] is False
rok=m.reconciliation(1931,1938,{"counts":{"source_records":1938},"text_enrichment":{"text_unavailable_records":0}},{"fetch_status":"ok"})
assert rok["backlog"]==0 and rok["balanced"] is True
print("PASS whole-site data learning coverage audit")
