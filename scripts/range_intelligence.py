#!/usr/bin/env python3
"""V6.10b research-only Market Location Research.

Legacy filename retained for compatibility. This is not the planned structural
Range Engine / volume-profile / support-resistance state machine.

This module is deliberately outside the production Playbook state machine.
It does not write the Forward Ledger, change CP-01/02/03, size positions,
or emit orders. Its four-state output is descriptive decision context only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data.json"
PLAYBOOK = ROOT / "docs" / "research" / "playbook_status.json"
OUT = ROOT / "docs" / "research" / "range_intelligence.json"
VERSION = "6.10b.0"

ASSETS = ("QQQM", "VGT", "QLD", "QQQ", "SMH", "TQQQ")


def load(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def asset_row(data, symbol):
    for bucket in ("core", "index", "stocks"):
        row = (data.get(bucket) or {}).get(symbol)
        if row:
            return row
    return {}


def classify(row):
    """Classify market location without changing any production trigger.

    Thresholds are research heuristics, versioned here, and must not be reused
    by the production Playbook during the V6.10a stabilization window.
    """
    try:
        rsi = float(row.get("rsi"))
        dd = float(row.get("strategy_drawdown"))
        d200 = float(row.get("dist_200ma"))
    except (TypeError, ValueError):
        return "UNDETERMINED", "数据不足，保持观察，不形成决策提示。"

    if dd <= -0.15 or d200 <= -0.08:
        return "RANGE_STRESS", "压力区：只做风险复核；不得由本模块触发交易。"
    if dd <= -0.06 or rsi <= 40:
        return "RANGE_PULLBACK", "回撤区：准备研究清单，等待正式 Playbook 独立确认。"
    if rsi >= 70 or d200 >= 0.22:
        return "RANGE_EXTENDED", "扩张区：避免追价，等待价格/基本面重新形成更好赔率。"
    return "RANGE_BALANCED", "均衡区：维持观察，按既有 Playbook 与长期计划执行。"


def build(data=None, playbook=None, now=None):
    data = load(DATA) if data is None else data
    playbook = load(PLAYBOOK) if playbook is None else playbook
    now = now or datetime.now(timezone.utc)
    market_date = str(data.get("spy_date") or data.get("updated") or "")[:10] or None
    rows = []
    for symbol in ASSETS:
        row = asset_row(data, symbol)
        state, prompt = classify(row)
        rows.append({
            "symbol": symbol,
            "market_date": market_date,
            "state": state,
            "decision_prompt": prompt,
            "metrics": {
                "rsi14": row.get("rsi"),
                "drawdown": row.get("strategy_drawdown"),
                "distance_200ma": row.get("dist_200ma"),
            },
            "research_only": True,
            "scoreable": False,
            "ledger_write": False,
        })
    payload = {
        "version": VERSION,
        "display_name": "Market Location Research",
        "legacy_module_name": "Range Intelligence",
        "capability_scope": "RSI + drawdown + distance-to-200MA market-location classifier; not structural Range Engine",
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "market_date": market_date,
        "mode": "research_only",
        "production_playbook_version": playbook.get("version"),
        "production_semantics_frozen": True,
        "states": ["RANGE_EXTENDED", "RANGE_BALANCED", "RANGE_PULLBACK", "RANGE_STRESS"],
        "guardrails": [
            "No Forward Ledger writes.",
            "No order, position-size, or account action.",
            "No mutation of CP-01/CP-02/CP-03 thresholds or state semantics.",
            "UNDETERMINED is never promoted to a decision state.",
        ],
        "assets": rows,
    }
    return payload


def main():
    payload = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"version": VERSION, "mode": payload["mode"], "assets": len(payload["assets"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
