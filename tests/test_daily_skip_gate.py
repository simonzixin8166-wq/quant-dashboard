"""daily_skip_gate: skip only a late duplicate US-close Daily; every doubt runs the Daily (fail-open)."""
import json, os, pathlib, sys, tempfile
from datetime import datetime, timezone
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import daily_skip_gate as g

S = "2026-10-30"
TIERS = {"t1": 0.12}


def data(spy=S, dates=(S, S)):
    return {"spy_date": spy, "core": {"QQQM": {"date": dates[0], "tiers": TIERS},
                                      "VGT": {"date": dates[1], "tiers": TIERS},
                                      "NOTIER": {"date": "2020-01-01"}}}


def server(ok=True, asof=S):
    return {"data_trust": {"ok": ok, "market_as_of": asof}}


# published + trusted → skip
assert g.decide(data(), server(), S) == (True, f"already_published({S})")
# every doubt → run
assert g.decide(data(spy="2026-10-29"), server(), S)[0] is False
assert g.decide(data(dates=(S, "2026-10-29")), server(), S) == (False, "core_rows_stale(VGT)")
assert g.decide(data(), server(ok=False), S) == (False, "data_trust_not_ok")
assert g.decide(data(), server(ok=None), S)[0] is False
assert g.decide(data(), server(asof="2026-10-29"), S)[0] is False
assert g.decide(None, server(), S) == (False, "inputs_unavailable")
assert g.decide(data(), None, S) == (False, "inputs_unavailable")
assert g.decide({"spy_date": S, "core": {}}, server(), S) == (False, "core_rows_unavailable")
assert g.decide(data(), {"data_trust": "garbled"}, S)[0] is False

# main(): session from the NYSE calendar, GITHUB_OUTPUT written, garbled files fail open
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    (root / "docs" / "research").mkdir(parents=True)
    (root / "docs" / "data.json").write_text(json.dumps(data()), encoding="utf-8")
    (root / "docs" / "research" / "server_action_status.json").write_text(json.dumps(server()), encoding="utf-8")
    out = root / "gh_out"
    os.environ["GITHUB_OUTPUT"] = str(out)
    # Sat 2026-10-31 00:56Z = Fri 10/30 20:56 ET → latest completed session 10/30 → skip
    assert g.main(datetime(2026, 10, 31, 0, 56, tzinfo=timezone.utc), root) == (True, f"already_published({S})")
    assert "skip=true" in out.read_text()
    # Mon 2026-11-02 22:00Z (EST, after close) → session 11/02 not yet published → run
    assert g.main(datetime(2026, 11, 2, 22, 0, tzinfo=timezone.utc), root)[0] is False
    (root / "docs" / "data.json").write_text("{not json", encoding="utf-8")
    assert g.main(datetime(2026, 10, 31, 0, 56, tzinfo=timezone.utc), root) == (False, "inputs_unavailable")
    del os.environ["GITHUB_OUTPUT"]

# workflow wiring: gate only on the US-close cron, update job honours it and still runs otherwise
wf = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
assert "github.event.schedule == '30 21 * * 1-5'" in wf
assert "needs: gate" in wf and "needs.gate.outputs.skip != 'true'" in wf
assert "!cancelled()" in wf  # a skipped gate job (dispatch / 08:15 / push) must not skip the update job
print("PASS daily skip gate (decide 10 cases, main 3 cases, workflow wiring)")
