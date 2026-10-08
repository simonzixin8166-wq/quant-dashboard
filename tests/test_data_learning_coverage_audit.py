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
mature=(rows["production_playbook_forward_replay"].get("counts") or {}).get("mature_total") or {}
mature_n=sum(int(v or 0) for v in mature.values()) if isinstance(mature,dict) else 0
assert rows["production_playbook_forward_replay"]["learning_status"]==("learning_active" if mature_n>0 else "partial_learning")
assert rows["production_playbook_forward_replay"]["outcome_feedback"] is (mature_n>0)
assert rows["regional_cn_hk_learning"]["learning_status"]=="context_only"
assert rows["financial_fundamentals_xbrl"]["learning_status"] in {"not_implemented","partial_learning"}
if rows["financial_fundamentals_xbrl"]["collected"]:
    assert rows["financial_fundamentals_xbrl"]["learning_status"]=="partial_learning"
assert rows["official_sec_filings"]["learning_status"] in {"partial_learning","learning_active"}
assert "canonical_storage" in out["required_contract"]
assert "reconciliation" in out["required_contract"]
assert "reconciliation" in out
assert out["reconciliation"]["balanced"] is True
assert out["reconciliation"]["processed"] + out["reconciliation"]["backlog"] >= out["reconciliation"]["captured"]
print("PASS whole-site data learning coverage audit")
