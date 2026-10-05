from pathlib import Path
import importlib.util, json

ROOT=Path(__file__).resolve().parents[1]

pi=(ROOT/"docs"/"assets"/"product-intelligence.js").read_text(encoding="utf-8")
journal=(ROOT/"docs"/"assets"/"decision-journal.js").read_text(encoding="utf-8")
guard=(ROOT/"scripts"/"private_guardrail.py").read_text(encoding="utf-8")
step=(ROOT/"scripts"/"run_research_step.py").read_text(encoding="utf-8")
privacy=(ROOT/"supabase"/"migrations"/"202610050001_private_watchlist_targets.sql").read_text(encoding="utf-8")
ledger=(ROOT/"supabase"/"migrations"/"202610050002_request_usage_ledger.sql").read_text(encoding="utf-8")
workflow=(ROOT/".github"/"workflows"/"server-action-watch.yml").read_text(encoding="utf-8")

assert "cannot_judge" in pi
assert "今日无法可靠判断" in pi
assert "opportunityAxes" in pi
assert "机会 / 风险 / 置信" in pi
assert "/100" not in pi
assert "趋势风险复核" in pi and "不能直接等同 Thesis 已失效" in pi
assert "recordOperatorDecision" in journal
assert "mavOperatorDecisionsV615" in journal
assert "data_error" in pi
assert "PUBLIC_JSON_ROOT_ALLOWLIST" in guard
assert "server_action_status.json" in guard
assert '"before_hash"' in step and 'old_record.pop("before",None)' in step
assert '[-80:]' in step
assert "stock_watchlist_authenticated_read" in privacy
assert "stock_targets_authenticated_read" in privacy
assert "using (auth.uid() is not null)" in privacy
assert "request_usage_ledger" in ledger and "No client policies" in ledger
assert 'cron: "*/30 13-22 * * 1-5"' in workflow

spec=importlib.util.spec_from_file_location("sa",ROOT/"scripts"/"server_action_engine.py")
sa=importlib.util.module_from_spec(spec);spec.loader.exec_module(sa)
assert sa.fingerprint({"status":"clear","trust":{},"event_count_48h":0,"actions":[]})
assert sa.thesis_review_actions([])==[]
src=(ROOT/"scripts"/"server_action_engine.py").read_text(encoding="utf-8")
for token in [
    "write_usage_ledger","suppressed_duplicate","MYALPHA_TG_BOT_TOKEN",
    "new evidence arrived after thesis update","sanitized public summary only",
]:
    assert token in src

assert not (ROOT/".github"/"workflows"/"v661-one-time-refresh.yml").exists()
print("PASS P0+P1+P2 frozen-plan integration contract")
