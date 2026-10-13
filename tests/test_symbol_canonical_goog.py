"""SYM-01 (#133, owner 2026-10-13): GOOGL is folded into GOOG everywhere new symbols are produced; history is not rewritten."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import source_intelligence_engine as si  # noqa: E402
import symbol_registry as reg  # noqa: E402

assert si.canonical_symbol("GOOGL") == "GOOG" and si.canonical_symbol("goog") == "GOOG" and si.canonical_symbol("NVDA") == "NVDA"
assert si.CANONICAL_SYMBOL == reg.CANONICAL_SYMBOL == {"GOOGL": "GOOG"}
syms = si.symbols("谷歌 GOOGL 与 GOOG 以及 NVDA 财报")
assert "GOOGL" not in syms and syms.count("GOOG") == 1 and "NVDA" in syms, syms
d = si.sanitize_declared_symbols(["GOOGL", "GOOG", "NVDA"], "GOOGL GOOG NVDA")
assert d == ["GOOG", "NVDA"], d
rep = reg.build()
assert "GOOGL" not in rep["symbols"], "registry must not carry a separate GOOGL row"
print("test_symbol_canonical_goog OK")
