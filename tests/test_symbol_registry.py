"""D-04/D-07: three universes stay separate; hidden symbols remain collected; missing history counted as securities."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import symbol_registry as r  # noqa: E402

rep = r.build()
u = rep["universes"]
disp, res, col = set(u["display_watchlist"]), set(u["research_universe"]), set(u["data_collection_universe"])
assert res <= col and (disp - set(r.NON_SECURITY)) <= col
assert r.BENCHMARKS <= col and r.OWNER_REQUESTED <= col
# a security not shown on the website is still collected (AAPL is not in the display list)
assert "AAPL" in col and "AAPL" not in disp
# non-securities are never collection targets
assert not (set(r.NON_SECURITY) & col)
# identity is never guessed
assert rep["symbols"]["DRAM"]["identity"] == "unverified"
# missing history is reported per security, separately from event rows
mh = rep["missing_historical_symbols"]
assert rep["counts"]["missing_history_securities"] == len(mh) == len({m["symbol"] for m in mh})
assert all(not rep["symbols"][m["symbol"]]["in_archive"] for m in mh)
assert "event_rows_without_history" in rep["counts"] and "not securities" in rep["note"]
assert rep["read_only"] is True
print("test_symbol_registry OK")
