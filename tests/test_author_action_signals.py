"""Author action signals export: headline priority, plans labelled 非成交, research-signal notice."""
import importlib.util, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("sie_a", ROOT / "scripts" / "source_intelligence_engine.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
recs = [{"author": "麻你", "published_at": "2026-09-11", "url": "u1", "title": "t",
         "author_actions": [{"symbol": "VGT", "action_type": "HOLD", "allocation_pct": {"VGT": 87.0, "SGOV": 13.0}},
                            {"symbol": "VGT", "action_type": "SELL_PLANNED", "size_pct": 4.0, "price": 117.57}]},
        {"author": "麻你", "published_at": "2026-09-25", "url": "u2", "title": "t2",
         "author_actions": [{"symbol": "VGT", "action_type": "HOLD", "allocation_pct": {"VGT": 87.0, "SGOV": 13.0}}]},
        {"author": "bogbog", "author_actions": []}]
out = m.author_action_signals(recs)
assert [r["url"] for r in out["records"]] == ["u2", "u1"]                     # newest first
assert out["records"][1]["headline"] == {"symbol": "VGT", "action_type": "SELL_PLANNED", "kind": "planned", "text": "VGT：计划减仓（非成交） 4% @ 117.57"}
assert out["records"][0]["headline"]["text"] == "VGT：继续持有 VGT 87% / SGOV 13%"
assert m.author_headline([{"symbol": "VGT", "action_type": "SELL_EXECUTED", "size_pct": 4.0}])["kind"] == "executed"
assert "不是 MyAlpha 的操作建议" in out["notice"] and "计划/挂单不等于成交" in out["notice"]
print("PASS author action signals export")
