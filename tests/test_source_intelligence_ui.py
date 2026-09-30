import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/"docs"/"data"/"source_intelligence.json").read_text(encoding="utf-8"))
assert data["counts"]["records"]==118
assert data["authors"]==["BrightLine"]
assert "风险管理" in data["topic_groups"]
assert data["thesis_candidates"]
js=(ROOT/"docs"/"assets"/"wenxuecity.js").read_text(encoding="utf-8")
for label in ["主题研究","具体操作","验证结果","失败复盘","观点演变","来源档案"]:
    assert label in js
nav=js.split('aria-label="文学城栏目"',1)[1].split('</nav>',1)[0]
for old in ["投资助手","方法地图","博客文章","论坛与收盘复盘","方法沉淀","作者与数据状态"]:
    assert old not in nav
agent=(ROOT/"docs"/"assets"/"autonomous-agent.js").read_text(encoding="utf-8")
assert "Source Intelligence · 外部研究线索" in agent
assert "查看作者原文" in agent
print("PASS source intelligence UI")

assert "research/source_outcome_validation.json" in js
assert "5 / 20 / 60 交易日跟踪" in js

assert "第一档买入价" in js
assert "第二档买入价" in js
assert "卖出线" in js
assert "走势与当时方向不一致" in js
assert "entry_1" not in js.split("function humanValidationField",1)[1].split("function outcomeCard",1)[1]
