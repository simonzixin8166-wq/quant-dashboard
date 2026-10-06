import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("le",ROOT/"scripts"/"learning_evaluation_engine.py")
le=importlib.util.module_from_spec(spec);spec.loader.exec_module(le)

execution={
  "results":[
    {"confidence":"high","counter_evidence":["x"],"unknowns":["SEC官方证据暂不可用","行业同业联动样本暂不足"]},
    {"confidence":"medium","counter_evidence":["x"],"unknowns":["同组合 20 日成熟样本仍不足"]},
  ]
}
planner={"counts":{"open":4,"high_priority":2}}
learning={"quality":{"situations":12}}
method={"counts":{"source_records":100,"eligible_triggered_events":6,"direct_method_links":0,"mature60_eligible_events":0},
        "methods":[{"method":"LEAPS","direct_validated_events":0},{"method":"Sell Put","direct_validated_events":9,"performance":{"20":{"alignment_rate":0.66}}}]}
evidence={"failure_attribution":{"external_outcome_reviews":[{"failure_tags":["underperformed_qqq"]},{"failure_tags":["underperformed_qqq","late_signal"]}]}}
history={"summary":{"symbols":21,"events":3890,"mature_20":2000,"mature_60":1800,"mature_120":1500}}
self_improvement={"candidate_brain":{"count":2},"shadow_brain":{"eligible_for_review":[]},"production_brain":{"mode":"locked"}}

auto_thesis={"symbols":{"IREN":{"sources":{"official":[{"evidence_class":"direct_company"}]}}}}
event_window={"summary":{"reviews":5,"with_sec":1,"with_ranked_event":2}}
server_action={"positions_checked":3,"quote_failures":0,"action_counts":{"unknown":0},"option_learning":{"observations":3,"mature_outcomes":1}}
forward_feedback={"counts":{"forward_mature20":0,"forward_mature60":0,"attribution_reviews":0}}
out=le.build(execution,planner,learning,method,evidence,history,self_improvement,auto_thesis,event_window,server_action,forward_feedback)
assert out["version"]=="6.13.2"
assert out["research_scorecard"]["analyzed"]==2
assert out["research_scorecard"]["situation_memory"]==12
assert out["outcome_memory"]["mature_60"]==1800
assert out["method_validation"]["source_records"]==100
assert out["method_validation"]["methods_with_direct_validation"]==1
assert out["evidence_gaps"][0]["count"]>=1
assert out["shadow_status"]["production_brain"]=="locked"
assert out["learning_health"]["score"] <= 100
eq=out["engine_quality"]
assert set(eq)=={"market","fundamental","event","options","decision","principle"}
assert eq["market"]["validation_state"]=="forward_unproven"
assert eq["fundamental"]["evidence_state"]=="direct_company_ready"
assert eq["fundamental"]["validation_state"]=="outcome_link_missing"
assert eq["event"]["validation_state"]=="descriptive_context_only"
assert eq["options"]["validation_state"]=="outcome_maturing"
assert eq["options"]["state_observations"]==3
assert eq["options"]["mature_outcomes"]==1
assert eq["decision"]["validation_state"]=="partial_local_loop"
assert out["lessons"]
assert any("证据缺口" in x or "直接验证" in x or "历史库" in x for x in out["lessons"])

agent=(ROOT/"docs/assets/autonomous-agent.js").read_text(encoding="utf-8")
assert "V6.9 Learning Evaluation · 自我评估中心" in agent
assert "research/learning_evaluation.json" in agent
assert "当前最需要补什么" in agent
assert "Five Learning Engines · 学习质量闭环" in agent
assert "Evidence → Validation → Feedback" in agent

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.9 Learning Evaluation" in workflow
assert "test_v690_learning_evaluation.py" in workflow

print("PASS V6.9 learning evaluation")
