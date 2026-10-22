"""FWD-01 L0: the pre-registered forward scoring contract is frozen (hash pinned), covers every decision the
forward engine can emit, and its hit rules behave as approved by the Owner on 2026-10-22.
Reads code and config only - never the live ledgers - so new data can never break this test."""
import hashlib
import json
import operator
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward_observation_engine as foe

c = json.loads((ROOT / "config" / "forward_scoring_contract.json").read_text(encoding="utf-8"))
rules = c["rules"]
digest = hashlib.sha256(json.dumps(rules, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
# Pinned: editing 'rules' needs a new contract_id approved by the Owner, then a new pin here.
assert (c["contract_id"], digest) == ("fsc-1.0", "3eb0efc58e3eba8b"), (c["contract_id"], digest)

# every decision label the engine can produce is mapped (labels come from code, not data)
labels = {lab for _, lab in foe.RULES["decision"]}
assert labels == set(rules["classes"]), (labels, set(rules["classes"]))
for s in ("趋势退潮", "二次启动", "高位钝化", "震荡观察"):
    for mode in ("fear", "normal"):
        assert foe.decision(s, mode) in rules["classes"]

# horizons extend the engine's (20/60/120) with 180, same benchmark
assert set(foe.HORIZONS) <= set(rules["horizons_sessions"]) and 180 in rules["horizons_sessions"]
assert rules["benchmark"] == foe.BENCHMARK == "QQQ"
assert rules["min_n_for_rate"] == 20

OPS = {">": operator.gt, "<": operator.lt, "<=": operator.le, ">=": operator.ge}


def hit(decision, excess):
    rule = rules["classes"].get(decision)
    if rule is None:
        return "unscored_unmapped"
    if rule["hit_if"] is None:
        return "abstain"
    if excess is None:
        return "unavailable"
    h = rule["hit_if"]
    return OPS[h["op"]](excess, h["value"])


# approved table (#133 audit part 2 §7)
assert hit("修复候选", 0.01) is True and hit("修复候选", 0.0) is False and hit("修复候选", -0.02) is False
assert hit("大跌机会候选", 0.03) is True and hit("大跌机会候选", -0.01) is False
assert hit("等待修复", -0.01) is True and hit("等待修复", 0.0) is False
assert hit("高位观察", 0.0) is True and hit("高位观察", -0.05) is True and hit("高位观察", 0.02) is False
assert hit("继续观察", 0.5) == "abstain"
assert hit("新标签", 0.1) == "unscored_unmapped"
assert hit("修复候选", None) == "unavailable"
assert {"genuine_forward with promoted", "different horizons"} <= set(rules["never_pool"])
print(f"PASS forward scoring contract {c['contract_id']} hash {digest}: {len(labels)} decision classes mapped, hit rules as approved")
