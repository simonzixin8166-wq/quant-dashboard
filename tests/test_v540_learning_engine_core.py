import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from learning_engine_core import build_engine, technical_similarity
from update_fred_macro import build_regime


macro_series = {
    "DFF": {"latest": {"value": 4.5}, "changes": {"20": 0, "3": 0}},
    "DGS10": {"latest": {"value": 4.2}, "changes": {"20": -0.3}},
    "T10Y2Y": {"latest": {"value": 0.1}, "changes": {}},
    "DFII10": {"latest": {"value": 1.7}, "changes": {"20": -0.2}},
    "CPIAUCSL": {"yoy": 0.028},
    "CPILFESL": {"yoy": 0.03},
    "UNRATE": {"latest": {"value": 4.2}, "changes": {"3": 0.1}},
    "BAMLH0A0HYM2": {"latest": {"value": 3.0}, "changes": {}},
    "NFCI": {"latest": {"value": -0.2}, "changes": {}},
}

regime = build_regime(macro_series)
assert 0 <= regime["macro_risk_score"] <= 100
assert regime["credit_regime"] == "EASY"

current = {"symbol": "AAA", "stage": "二次启动", "score": 80, "weekly": "多头", "zone": None}
event = {"symbol": "BBB", "stage": "二次启动", "score": 75, "weekly": "多头", "zone": None}
assert technical_similarity(current, event) > 90

history = {
    "profiles": {
        "二次启动": {
            "evidence": {"label": "历史表现偏正", "research_adjustment": 4},
            "horizons": {"60": {"n": 100, "median": 0.08, "positive_rate": 0.63}},
        }
    },
    "recent_events": [
        {
            "symbol": "BBB",
            "date": "2025-01-01",
            "stage": "二次启动",
            "score": 75,
            "weekly": "多头",
            "outcomes": {"60": {"return": 0.1, "mae": -0.04}},
        }
    ],
}

data = {
    "updated": "2026-09-29",
    "market_regime": {"tier_label": "正常"},
    "stocks": {"AAA": {"close": 100, "rsi": 60, "window_drawdown": -0.05}},
    "trend_pulse": {
        "AAA": {
            "available": True,
            "date": "2026-09-29",
            "score": 80,
            "state": "二次启动",
            "weekly": "多头",
            "rsi": 60,
            "structure": "HH/HL",
            "supertrend": "多头",
            "confidence": "高",
        }
    },
}

engine = build_engine(data, history, {"regime": regime})
assert engine["version"] == "5.4.0"
assert engine["quality"]["situations"] == 1
assert engine["situation_memory"][0]["symbol"] == "AAA"
assert engine["opportunity_queue"][0]["rank"] == 1

print("PASS V5.4 Learning Engine Core")
