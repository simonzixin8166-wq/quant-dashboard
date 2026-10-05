import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/"docs"/"data"/"source_intelligence.json").read_text(encoding="utf-8"))
assert data["counts"]["records"]>=118
assert "BrightLine" in data["authors"]
assert "风险管理" in data["topic_groups"]
assert data["thesis_candidates"]
js=(ROOT/"docs"/"assets"/"wenxuecity.js").read_text(encoding="utf-8")
for label in ["主题研究","方法记忆","具体操作","历史观察归档","失败复盘","观点演变","来源档案"]:
    assert label in js
nav=js.split('aria-label="文学城栏目"',1)[1].split('</nav>',1)[0]
for old in ["投资助手","方法地图","博客文章","论坛与收盘复盘","方法沉淀","作者与数据状态"]:
    assert old not in nav
agent=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")
assert "Source Intelligence · 外部研究线索" in agent
assert "查看作者原文" in agent
assert data["counts"]["records"] >= 118
print("PASS source intelligence UI")

assert "research/source_outcome_validation.json" in js
assert "历史观察归档 · 旧 Outcome 5 / 20 / 60 日跟踪" in js
assert "正式证据分层" in js
assert "Forward 证据候选" in js
assert "成熟可评分证据" in js
assert "research/evidence_status.json" in js
assert "旧 Method Memory / Outcome 仅用于历史观察" in js

assert "第一档买入价" in js
assert "第二档买入价" in js
assert "卖出线" in js
assert "走势与当时方向不一致" in js
assert "entry_1" not in js.split("function humanValidationField",1)[1].split("function outcomeCard",1)[1]

assert "research/method_memory.json" in js
assert "Method Memory · 方法记忆" in js
assert "Direct" in js and "Context only" in js
assert "60日成熟 Direct" in js


status=json.loads((ROOT/"docs"/"research"/"evidence_status.json").read_text(encoding="utf-8"))
layers=status["evidence_layers"]
assert status["evaluation_spec_version"]=="1.7"
assert layers["legacy_observational_archive"]["count"]>=46
assert layers["forward_evidence_candidates"]["count"]>=0
assert layers["mature_scoreable_evidence"]["event_count_60d"]>=0
assert status["promotion"]["production_effect"]=="none"
builder=(ROOT/"scripts"/"public_research_evidence_status.py").read_text(encoding="utf-8")
assert "point_in_time_status" in builder
assert "scoreable" in builder
assert "legacy_observational_archive" in builder
assert "Method Memory and Source Outcome remain descriptive/legacy" in builder


# Source->Rule funnel is public observability only; UI must not present fake maturity progress.
assert "Source → Rule 运行漏斗" in js
assert "自上次成功运行以来" in js
assert "未开始 · 等待第一条 genuine forward" in js
builder=(ROOT/"scripts"/"public_research_evidence_status.py").read_text(encoding="utf-8")
assert "source_rule_funnel" in builder
assert "maturity_clock" in builder
assert "result_blind" in builder
print("PASS Source->Rule funnel public observability UI contract")


# Historical YouTube learning is visible but explicitly non-gating.
assert "YouTube 历史学习记忆" in js
assert "Q1/Q2 可学习" in js
assert "不把旧视频洗成今天的 Forward Evidence" in js
assert "Forward / EventScore / Promotion 均不参与" in js
print("PASS YouTube historical learning UI isolation")

# V6.15 Author Intelligence keeps historical author memory separate from forward evidence.
assert "Author Intelligence · 作者研究画像" in js
assert "research/author_intelligence.json" in js
assert "没有真实 point-in-time 样本时保持 0" in js
print("PASS V6.15 author intelligence UI")

assert "V6.15 阶段状态" in js
assert "research/v615_program_status.json" in js
assert "20/60 日不能通过回填历史视频" in js
print("PASS V6.15 program status UI")


# V6.15 research cockpit prioritizes current state -> evidence -> learning memory.
assert "研究系统已就绪，正在等待真实 Forward 样本" in js
assert "01 · CURRENT STATE" in js
assert "02 · EVIDENCE" in js
assert "03 · LEARNING MEMORY" in js
assert "展开研究闭环与主题研究" in js
css=(ROOT/"docs"/"assets"/"wenxuecity.css").read_text(encoding="utf-8")
for cls in ["wxc-cockpit-hero","wxc-cockpit-metrics","wxc-section-block","wxc-secondary-detail"]:
    assert cls in css
print("PASS V6.15 research cockpit hierarchy")
