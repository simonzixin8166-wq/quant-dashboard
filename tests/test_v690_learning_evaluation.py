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

out=le.build(execution,planner,learning,method,evidence,history,self_improvement)
assert out["version"]=="6.9.0"
assert out["research_scorecard"]["analyzed"]==2
assert out["research_scorecard"]["situation_memory"]==12
assert out["outcome_memory"]["mature_60"]==1800
assert out["method_validation"]["source_records"]==100
assert out["method_validation"]["methods_with_direct_validation"]==1
assert out["evidence_gaps"][0]["count"]>=1
assert out["shadow_status"]["production_brain"]=="locked"
assert out["learning_health"]["score"] <= 100
assert out["lessons"]
assert any("证据缺口" in x or "直接验证" in x or "历史库" in x for x in out["lessons"])

agent=(ROOT/"docs/assets/autonomous-agent.js").read_text(encoding="utf-8")
assert "V6.9 Learning Evaluation · 自我评估中心" in agent
assert "research/learning_evaluation.json" in agent
assert "当前最需要补什么" in agent

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Build V6.9 Learning Evaluation" in workflow
assert "test_v690_learning_evaluation.py" in workflow

print("PASS V6.9 learning evaluation")
