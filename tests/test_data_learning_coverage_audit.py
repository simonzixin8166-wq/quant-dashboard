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
assert rows["financial_fundamentals_xbrl"]["learning_status"]=="not_implemented"
assert rows["official_sec_filings"]["learning_status"] in {"partial_learning","learning_active"}
assert "canonical_storage" in out["required_contract"]
assert "reconciliation" in out["required_contract"]
print("PASS whole-site data learning coverage audit")
