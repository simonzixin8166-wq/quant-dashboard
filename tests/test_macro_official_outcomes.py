"""P0-A (#133 6148675138): CPI official outcome — time order, fail-closed states, same-measure surprise only,
cross-check conflict withholds the outcome, append-only checkpoint records with exact as_of. No network."""
import copy, json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import macro_official_outcomes as mo  # noqa: E402
import brightline_tranche_shadow as bl  # noqa: E402

CAL = json.loads((ROOT / "research/macro_events/event_facts_2026q4.json").read_text(encoding="utf-8"))
EV = CAL["events"]["cpi_2026_09"]
EXP = json.loads((ROOT / "research/macro_events/expectations/cpi_2026_09.json").read_text(encoding="utf-8"))
T = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))


def series(sid, pts):
    return {"seriesID": sid, "data": [{"year": k[:4], "period": "M" + k[5:], "value": str(v)} for k, v in pts.items()]}


# synthetic indices (not real data): Sep/Aug = +0.3 % SA headline, +0.2 % core; y/y 3.0 % headline, 2.5 % core
SA_H = {"2026-08": 330.000, "2026-09": 331.000}
SA_C = {"2026-08": 335.000, "2026-09": 335.670}
NSA_H = {"2025-09": 320.000, "2026-08": 329.000, "2026-09": 329.600}
NSA_C = {"2025-09": 326.000, "2026-08": 333.500, "2026-09": 334.150}
GOOD = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [series("CUSR0000SA0", SA_H), series("CUSR0000SA0L1E", SA_C),
                                                              series("CUUR0000SA0", NSA_H), series("CUUR0000SA0L1E", NSA_C)]}}
OLD = copy.deepcopy(GOOD)
for s in OLD["Results"]["series"]:
    s["data"] = [d for d in s["data"] if d["period"] != "M09"]
TEXT = ("<h2>CONSUMER PRICE INDEX – SEPTEMBER 2026</h2><p>The Consumer Price Index for All Urban Consumers (CPI-U) rose 0.3 percent "
        "on a seasonally adjusted basis in September ... Over the last 12 months, the all items index rose 3.0 percent before seasonal "
        "adjustment. ... The index for all items less food and energy rose 0.2 percent in September.</p>")

calls = []
def api(body, status=200):
    def f(url, payload, timeout=30):
        calls.append(url)
        return status, json.dumps(body).encode()
    return f
def text(body, status=200):
    return lambda url, timeout=30: (status, body.encode())
def boom(*a, **k):
    raise AssertionError("network must not be called before release")

# 1) before release: pending, no network call, outcome never filled by the date
ev, log = mo.step("cpi_2026_09", EV, T("2026-10-14T12:29:59Z"), fetch_api=boom, fetch_text=boom, expectations=EXP)
assert ev["outcome_status"] == "pending" and ev["official_outcome_recorded_at"] is None and log is None

# 2) released but API still on August → official_result_unavailable; after 24 h → stale; outcome stays null
ev, log = mo.step("cpi_2026_09", EV, T("2026-10-14T12:36:00Z"), fetch_api=api(OLD), fetch_text=boom, expectations=EXP)
assert ev["outcome_status"] == "official_result_unavailable" and ev["official_outcome_recorded_at"] is None and log["result"] == ev["outcome_status"]
assert log["latest_period_per_series"]["headline_sa"] == "2026-08"
ev, _ = mo.step("cpi_2026_09", EV, T("2026-10-15T13:00:00Z"), fetch_api=api({}, 403), fetch_text=boom, expectations=EXP)
assert ev["outcome_status"] == "stale" and ev["official_outcome_recorded_at"] is None

# 3) success + matching release text → recorded with exact one-decimal values, hash, published/captured times
ev, log = mo.step("cpi_2026_09", EV, T("2026-10-14T12:36:00Z"), fetch_api=api(GOOD), fetch_text=text(TEXT), expectations=EXP)
v = ev["official_outcome"]["values"]
assert ev["outcome_status"] == "recorded" and ev["official_outcome_recorded_at"] == "2026-10-14T12:36:00Z"
assert (v["headline_mom_sa"], v["core_mom_sa"], v["headline_yoy_nsa"], v["core_yoy_nsa"]) == (0.3, 0.2, 3.0, 2.5), v
src = ev["official_outcome"]["official_source"]
assert src["published_at"] == "2026-10-14T12:30:00Z" and src["captured_at"] == "2026-10-14T12:36:00Z" and len(src["data_sha256"]) == 64
assert ev["official_outcome"]["cross_check"]["result"] == "match" and "parsed" in ev["official_outcome"]["cross_check"]
assert "release_text" not in json.dumps(log["cross_check"]).replace('"release_text"', "")  # no text in the log

# 4) no survey consensus → consensus_unavailable, surprise unknown; reference diffs are same-measure only
assert ev["surprise"] == "unknown" and ev["official_outcome"]["consensus_status"] == "consensus_unavailable"
assert "不判定偏软/偏热" in ev["summary"]
for d in ev["official_outcome"]["reference_expectation_diffs"]:
    assert d["official"] == v[d["measure"]] and "never used" in d["note"]
hy = [d for d in ev["official_outcome"]["reference_expectation_diffs"] if d["measure"] == "headline_yoy_nsa"][0]
assert hy["expected"] == 3.7 and hy["diff_pp"] == -0.7  # y/y compared with y/y, never with m/m
# … and the state machine keeps both CPI conditions unknown (never 'unmet' from a missing consensus)
inp = {"expected_session": "2026-10-14", "macro": {"y10": {"value": 4.95, "date": "2026-10-13", "change_20": -0.1}},
       "breadth": {"b200": 0.52, "as_of": "2026-10-14"}, "events": {"events": {"cpi_2026_09": ev}},
       "core": {"QQQM": {"drawdown": -0.02, "date": "2026-10-14", "tiers": {"t1": 0.12}}}}
st = bl.evaluate(inp)
cs = [c for c in st["tranches"]["1_policy_rate"]["early"] if c["name"] == "cpi_soft"][0]
rk = [c for c in st["risk_off"]["conditions"] if c["name"] == "cpi_well_above_expectations"][0]
assert cs["status"] == "unknown" and rk["status"] == "unknown" and "consensus_unavailable" in rk["note"]

# 5) a preregistered survey consensus of the same measure sets the label; m/m and y/y never mixed
exp2 = copy.deepcopy(EXP); exp2["survey_consensus"] = {"core_mom_sa": {"value": 0.3}}
ev2, _ = mo.step("cpi_2026_09", EV, T("2026-10-14T12:36:00Z"), fetch_api=api(GOOD), fetch_text=text(TEXT), expectations=exp2)
assert ev2["surprise"] == "soft" and ev2["official_outcome"]["surprise_measure"] == "core_mom_sa" and ev2["official_outcome"]["surprise_diff_pp"] == -0.1
exp3 = copy.deepcopy(EXP); exp3["survey_consensus"] = {"headline_yoy_nsa": {"value": 2.8}}
ev3, _ = mo.step("cpi_2026_09", EV, T("2026-10-14T12:36:00Z"), fetch_api=api(GOOD), fetch_text=text(TEXT), expectations=exp3)
assert ev3["surprise"] == "hot" and ev3["official_outcome"]["surprise_measure"] == "headline_yoy_nsa"
inp["events"]["events"]["cpi_2026_09"] = ev3
assert bl.evaluate(inp)["risk_off"]["active"] and bl.evaluate(inp)["overall"] == "risk_elevated"
inp["events"]["events"]["cpi_2026_09"] = ev2
assert bl.evaluate(inp)["tranches"]["1_policy_rate"]["state"] == "candidate"  # soft CPI AND real 10Y < 5 %

# 6) release text disagrees → conflict, outcome withheld, state machine stays unknown
ev4, log4 = mo.step("cpi_2026_09", EV, T("2026-10-14T12:36:00Z"), fetch_api=api(GOOD), fetch_text=text(TEXT.replace("rose 0.3", "rose 0.5")), expectations=EXP)
assert ev4["outcome_status"] == "conflict" and ev4["official_outcome_recorded_at"] is None and log4["result"] == "conflict"
assert bl.event_fact({"events": {"cpi_2026_09": ev4}}, "cpi_2026_09") is None
# release text still showing August, or unreachable → API record kept, cross-check marked (not a conflict)
ev5, _ = mo.step("cpi_2026_09", EV, T("2026-10-14T12:36:00Z"), fetch_api=api(GOOD), fetch_text=text(TEXT.replace("SEPTEMBER", "AUGUST")), expectations=EXP)
assert ev5["outcome_status"] == "recorded" and ev5["official_outcome"]["cross_check"]["result"] == "release_text_not_for_reference_month"
ev6, _ = mo.step("cpi_2026_09", EV, T("2026-10-14T12:36:00Z"), fetch_api=api(GOOD), fetch_text=text("", 403), expectations=EXP)
assert ev6["outcome_status"] == "recorded" and ev6["official_outcome"]["cross_check"]["result"] == "unavailable"
# once recorded, later runs do not refetch (official values are immutable)
n = len(calls)
ev7, log7 = mo.step("cpi_2026_09", ev, T("2026-10-15T21:40:00Z"), fetch_api=boom, fetch_text=boom, expectations=EXP)
assert ev7 == ev and log7 is None and len(calls) == n

# 7) checkpoint records: T-1 only before release and only from data whose as_of is T-1; T+n only after recorded
mk = lambda d, q: {"as_of": d, "closes": {"QQQ": q, "QQQM": q / 2.4, "VGT": None, "VOO": 700.0}, "drawdowns": {}}
r = mo.checkpoint_records("cpi_2026_09", EV, T("2026-10-13T21:45:00Z"), market=mk("2026-10-13", 740.0), existing=[])
assert [x["checkpoint"] for x in r] == ["T-1"] and r[0]["market_as_of"] == "2026-10-13"
assert mo.checkpoint_records("cpi_2026_09", EV, T("2026-10-14T13:00:00Z"), market=mk("2026-10-13", 740.0), existing=[]) == []  # baseline after release refused
assert mo.checkpoint_records("cpi_2026_09", EV, T("2026-10-14T21:45:00Z"), market=mk("2026-10-14", 750.0), existing=r) == []  # not recorded yet
r2 = mo.checkpoint_records("cpi_2026_09", ev, T("2026-10-14T21:45:00Z"), market=mk("2026-10-14", 750.0), existing=r)
assert [x["checkpoint"] for x in r2] == ["T"] and r2[0]["vs_baseline"]["QQQ"] == round(750 / 740 - 1, 4) and r2[0]["vs_baseline"]["VGT"] is None
assert r2[0]["author_forecast_check"]["status"] == "pending" and r2[0]["used_in_decision"] is False
assert mo.checkpoint_records("cpi_2026_09", ev, T("2026-10-14T22:45:00Z"), market=mk("2026-10-14", 751.0), existing=r + r2) == []  # idempotent
r3 = mo.checkpoint_records("cpi_2026_09", ev, T("2026-10-15T21:45:00Z"), market=mk("2026-10-15", 745.0), existing=[])
assert r3[0]["checkpoint"] == "T+1" and r3[0]["vs_baseline"] is None and "baseline_unavailable" in r3[0]["baseline_status"]
# a checkpoint whose session is not exactly the market as_of is never backfilled
assert mo.checkpoint_records("cpi_2026_09", ev, T("2026-10-20T21:45:00Z"), market=mk("2026-10-20", 745.0), existing=r + r2) == []

# 8) release-text parser: signs and 'unchanged'
p = mo.parse_release_text("CONSUMER PRICE INDEX - OCTOBER 2026 (CPI-U) was unchanged on a seasonally adjusted basis ... all items index rose 2.9 percent "
                          "... index for all items less food and energy fell 0.1 percent in October")
assert p == {"reference_month": "2026-10", "headline_mom_sa": 0.0, "headline_yoy_nsa": 2.9, "core_mom_sa": -0.1}, p

# 9) committed calendar: CPI not recorded before the release; preregistration precedes it
assert EV.get("official_outcome_recorded_at") is None or (EV["outcome_status"] == "recorded" and EV["official_outcome_recorded_at"] >= EV["release"]["utc"])
assert T(EXP["preregistered_at"]) < T(EV["release"]["utc"]) and EXP["consensus_status"] == "consensus_unavailable"

# 10) BLS API blocked (GitHub runners get 403 from bls.gov) → FRED mirror of the same BLS series; provenance kept
def pts_of(body):
    return mo.series_points(body)
mirror = lambda ref: (pts_of(GOOD), {"status": "ok"})
nomirror = lambda ref: (None, {"status": "fred_error: no key"})
evm, logm = mo.step("cpi_2026_09", EV, T("2026-10-14T12:40:00Z"), fetch_api=api({}, 403), fetch_text=text("", 403), expectations=EXP, fetch_mirror=mirror)
assert evm["outcome_status"] == "recorded" and evm["official_outcome"]["official_source"]["source_used"] == "fred_mirror"
assert evm["official_outcome"]["values"] == v and logm["http_status"] == 403 and logm["mirror"]["status"] == "ok"
assert evm["official_outcome"]["official_source"]["mirror"]["headline_sa"] == "CPIAUCSL"
evb, _ = mo.step("cpi_2026_09", EV, T("2026-10-14T12:36:00Z"), fetch_api=api(GOOD), fetch_text=text(TEXT), expectations=EXP, fetch_mirror=boom)
assert evb["official_outcome"]["official_source"]["source_used"] == "bls_api"          # mirror never called when BLS works
evn, logn = mo.step("cpi_2026_09", EV, T("2026-10-14T12:40:00Z"), fetch_api=api({}, 403), fetch_text=boom, expectations=EXP, fetch_mirror=nomirror)
assert evn["outcome_status"] == "official_result_unavailable" and "FRED mirror fred_error" in evn["outcome_status_detail"]
oldm = lambda ref: (pts_of(OLD), {"status": "ok"})                                     # mirror not yet updated → still unavailable
assert mo.step("cpi_2026_09", EV, T("2026-10-14T12:40:00Z"), fetch_api=api({}, 403), fetch_text=boom, expectations=EXP, fetch_mirror=oldm)[0]["outcome_status"] == "official_result_unavailable"
evc, _ = mo.step("cpi_2026_09", EV, T("2026-10-14T12:40:00Z"), fetch_api=api({}, 403), fetch_text=text(TEXT.replace("rose 0.3", "rose 0.6")), expectations=EXP, fetch_mirror=mirror)
assert evc["outcome_status"] == "conflict" and "fred_mirror" in evc["outcome_status_detail"]
print("PASS macro official outcomes (CPI)")
