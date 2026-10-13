#!/usr/bin/env python3
"""P0-A (#133 6148675138) — official macro-event outcomes, fetched after release, never before. Read-only Shadow.

CPI handler (cpi_2026_09). Source of truth: BLS Public Data API v1 (official, free, no key, no account):
  CUSR0000SA0 / CUSR0000SA0L1E  seasonally adjusted index  → headline / core month-over-month
  CUUR0000SA0 / CUUR0000SA0L1E  not seasonally adjusted    → headline / core 12-month (BLS convention)
Cross-check (optional): the BLS news-release text cpi.nr0.htm — only a hash, the HTTP status and the parsed
one-decimal percents are kept; the release text is never stored.

States written to event_facts (outcome_status), in time order:
  pending                      now < official release time (no network call is made)
  official_result_unavailable  released, but the API failed or still shows an older reference month
  stale                        still unavailable more than 24 h after release
  conflict                     API and release text disagree, or a later fetch changed recorded values
  recorded                     official values captured; official_outcome_recorded_at is set ONLY here
Only `recorded` lets the BrightLine Shadow state machine read the outcome; everything else stays unknown.
A surprise label needs a preregistered survey consensus of the same measure (expectations/<event>.json);
without one: consensus_unavailable → surprise unknown. Nothing here is an order; production_use=false.

After `recorded`, one append-only Shadow checkpoint record is written per completed checkpoint
(T-1 baseline, T, T+1, T+3, T+5, T+10) with the real market as_of; preregistered hypotheses are never rewritten.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402
import brightline_tranche_shadow as bl  # noqa: E402

EVENTS = ROOT / "research" / "macro_events" / "event_facts_2026q4.json"
EXPECT = ROOT / "research" / "macro_events" / "expectations"
LOG = ROOT / "research" / "macro_events" / "official_fetch_log.jsonl"
RECORDS = ROOT / "research" / "macro_events" / "event_outcome_records"
DATA = ROOT / "docs" / "data.json"
API = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
RELEASE_TEXT = "https://www.bls.gov/news.release/cpi.nr0.htm"
UA = os.getenv("BLS_USER_AGENT", "MyAlphaView/6.9 research-agent myalphaview.com")
SERIES = {"headline_sa": "CUSR0000SA0", "core_sa": "CUSR0000SA0L1E", "headline_nsa": "CUUR0000SA0", "core_nsa": "CUUR0000SA0L1E"}
CPI_EVENTS = {"cpi_2026_09": {"reference": "2026-09"}}
STALE_AFTER = timedelta(hours=24)
CHECKPOINTS = ("T-1", "T", "T+1", "T+3", "T+5", "T+10")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def _load(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


# ---------------------------------------------------------------- network (replaceable in tests) ----------
def http_post_json(url, payload, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:  # network / DNS / TLS
        return None, str(e).encode()[:200]


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return None, str(e).encode()[:200]


# ---------------------------------------------------------------- pure computation ------------------------
def series_points(api_json):
    """{key: {'YYYY-MM': float}} from a BLS API v1 response."""
    out = {}
    rev = {v: k for k, v in SERIES.items()}
    for s in ((api_json.get("Results") or {}).get("series") or []):
        k = rev.get(s.get("seriesID"))
        if not k:
            continue
        pts = {}
        for d in s.get("data") or []:
            p = d.get("period", "")
            if re.fullmatch(r"M(0[1-9]|1[0-2])", p):
                try:
                    pts[f"{d['year']}-{p[1:]}"] = float(d["value"])
                except (KeyError, ValueError):
                    pass
        out[k] = pts
    return out


def prev_month(ym, n=1):
    y, m = map(int, ym.split("-"))
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def pct(a, b):
    return round((a / b - 1) * 100, 1)


def compute(points, ref):
    """One-decimal percents as BLS publishes them; None when any index is missing."""
    try:
        return {
            "reference_month": ref,
            "headline_mom_sa": pct(points["headline_sa"][ref], points["headline_sa"][prev_month(ref)]),
            "core_mom_sa": pct(points["core_sa"][ref], points["core_sa"][prev_month(ref)]),
            "headline_yoy_nsa": pct(points["headline_nsa"][ref], points["headline_nsa"][prev_month(ref, 12)]),
            "core_yoy_nsa": pct(points["core_nsa"][ref], points["core_nsa"][prev_month(ref, 12)]),
            "index": {k: points[k][ref] for k in SERIES},
        }
    except (KeyError, ZeroDivisionError):
        return None


def parse_release_text(html):
    """Headline/core percents and reference month from the BLS release text (first paragraphs only)."""
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", txt)
    out = {}
    m = re.search(r"CONSUMER PRICE INDEX\s*[–-]\s*([A-Z]+)\s+(\d{4})", txt, re.I)
    if m and m.group(1).capitalize() in MONTHS:
        out["reference_month"] = f"{m.group(2)}-{MONTHS.index(m.group(1).capitalize()) + 1:02d}"

    def signed(verb, num):
        v = float(num)
        return -v if verb.lower() in ("fell", "declined", "decreased") else v
    m = re.search(r"\(CPI-U\)\s+(?:(rose|increased|fell|declined|decreased)\s+([\d.]+)\s+percent|(was unchanged))", txt)
    if m:
        out["headline_mom_sa"] = 0.0 if m.group(3) else signed(m.group(1), m.group(2))
    m = re.search(r"all items index (rose|increased|fell|declined|decreased)\s*([\d.]+)\s*percent", txt)
    if m:
        out["headline_yoy_nsa"] = signed(m.group(1), m.group(2))
    m = re.search(r"index for all items less food and energy (?:(rose|increased|fell|declined|decreased)\s+([\d.]+)\s+percent|(was unchanged))", txt)
    if m:
        out["core_mom_sa"] = 0.0 if m.group(3) else signed(m.group(1), m.group(2))
    return out


def surprise(values, expectations):
    """Label from a survey consensus of the same measure only; otherwise unknown + consensus_unavailable."""
    cons = (expectations or {}).get("survey_consensus") or {}
    order = ((expectations or {}).get("surprise_rule") or {}).get("measures_in_priority") or []
    for m in order:
        c = cons.get(m)
        if c is None or values.get(m) is None:
            continue
        d = round(values[m] - float(c["value"] if isinstance(c, dict) else c), 1)
        label = "soft" if d < 0 else "inline" if d == 0 else "above" if d < 0.2 else "hot"
        return {"surprise": label, "surprise_measure": m, "surprise_diff_pp": d, "consensus_status": "survey_consensus"}
    return {"surprise": "unknown", "surprise_measure": None, "surprise_diff_pp": None, "consensus_status": "consensus_unavailable"}


def reference_diffs(values, expectations):
    out = []
    for r in (expectations or {}).get("reference_expectations") or []:
        v = values.get(r["measure"])
        out.append({"measure": r["measure"], "kind": r["kind"], "label": r["label"], "expected": r["value"], "official": v,
                    "diff_pp": None if v is None else round(v - r["value"], 1), "source_url": r["source_url"],
                    "note": "reference only — never used for surprise or decisions"})
    return out


def summary_zh(v, s):
    t = (f"{v['reference_month'][:4]}年{int(v['reference_month'][5:])}月 CPI：整体环比 {v['headline_mom_sa']:+.1f}%（季调）、同比 {v['headline_yoy_nsa']:.1f}%；"
         f"核心环比 {v['core_mom_sa']:+.1f}%、同比 {v['core_yoy_nsa']:.1f}%（BLS 官方）")
    return t + ("｜无可靠共识预期，不判定偏软/偏热" if s["surprise"] == "unknown" else f"｜相对共识（{s['surprise_measure']}）{s['surprise_diff_pp']:+.1f}pp → {s['surprise']}")


# ---------------------------------------------------------------- state transition ------------------------
def step(ev_key, ev, now, fetch_api=http_post_json, fetch_text=http_get, expectations=None):
    """Return (new_event_dict, log_entry_or_None). Pure apart from the injected fetchers."""
    ev = json.loads(json.dumps(ev))
    rel = ts(ev["release"]["utc"])
    ref = CPI_EVENTS[ev_key]["reference"]
    if now < rel:
        ev["outcome_status"] = "pending"
        return ev, None
    if ev.get("outcome_status") == "recorded" and ev.get("official_outcome_recorded_at"):
        return ev, None  # official values are immutable; re-verification is an explicit --recheck
    log = {"event": ev_key, "attempted_at": iso(now), "source": API, "series": list(SERIES.values())}
    status, body = fetch_api(API, {"seriesid": list(SERIES.values()), "startyear": str(int(ref[:4]) - 1), "endyear": ref[:4]})
    log["http_status"] = status
    values, api = None, {}
    if status == 200:
        try:
            api = json.loads(body)
        except Exception:
            api = {}
        log["api_status"] = api.get("status")
        if api.get("status") == "REQUEST_SUCCEEDED":
            pts = series_points(api)
            log["latest_period_per_series"] = {k: (max(v) if v else None) for k, v in pts.items()}
            values = compute(pts, ref)
            log["data_sha256"] = sha(json.dumps(pts, sort_keys=True)) if pts else None
    if not values:
        late = now - rel > STALE_AFTER
        ev["outcome_status"] = "stale" if late else "official_result_unavailable"
        ev["outcome_status_detail"] = (f"BLS API http={status} api_status={log.get('api_status')} "
                                       f"latest={log.get('latest_period_per_series')} — reference {ref} not available")
        ev["outcome_last_attempt_at"] = iso(now)
        log["result"] = ev["outcome_status"]
        return ev, log
    # optional cross-check against the release text (hash + parsed percents only; text not stored)
    tstat, tbody = fetch_text(RELEASE_TEXT)
    cross = {"url": RELEASE_TEXT, "http_status": tstat}
    if tstat == 200 and tbody:
        parsed = parse_release_text(tbody.decode("utf-8", "replace"))
        cross.update({"sha256": sha(tbody), "parsed": parsed})
        if parsed.get("reference_month") != ref:
            cross["result"] = "release_text_not_for_reference_month"
        else:
            diffs = {k: (parsed[k], values[k]) for k in ("headline_mom_sa", "headline_yoy_nsa", "core_mom_sa") if k in parsed and parsed[k] != values[k]}
            cross["result"] = "conflict" if diffs else ("match" if any(k in parsed for k in ("headline_mom_sa", "core_mom_sa")) else "unparsed")
            if diffs:
                cross["diffs"] = {k: {"release_text": a, "api_computed": b} for k, (a, b) in diffs.items()}
    else:
        cross["result"] = "unavailable"
    log["cross_check"] = {k: v for k, v in cross.items() if k != "parsed"}
    exp = expectations if expectations is not None else _load(EXPECT / f"{ev_key}.json")
    s = surprise(values, exp)
    outcome = {"values": values, "official_source": {"api": API, "series": SERIES, "release_text": RELEASE_TEXT,
                                                     "published_at": ev["release"]["utc"], "captured_at": iso(now),
                                                     "http_status": status, "api_status": api.get("status"),
                                                     "data_sha256": log.get("data_sha256")},
               "cross_check": cross, **s, "reference_expectation_diffs": reference_diffs(values, exp),
               "expectations_file": f"research/macro_events/expectations/{ev_key}.json",
               "expectations_preregistered_at": (exp or {}).get("preregistered_at")}
    if cross["result"] == "conflict":
        ev["outcome_status"] = "conflict"
        ev["outcome_status_detail"] = "BLS API and release text disagree — outcome withheld (fail-closed)"
        ev["official_outcome_candidate"] = outcome
        ev["official_outcome_recorded_at"] = None
        log["result"] = "conflict"
        return ev, log
    ev.update({"outcome_status": "recorded", "official_outcome_recorded_at": iso(now), "official_outcome": outcome,
               "surprise": s["surprise"], "summary": summary_zh(values, s)})
    ev.pop("outcome_status_detail", None)
    ev.pop("official_outcome_candidate", None)
    log["result"] = "recorded"
    return ev, log


# ---------------------------------------------------------------- Shadow checkpoint records ---------------
def market_snapshot():
    d = _load(DATA)
    core = d.get("core") or {}
    return {"as_of": d.get("spy_date"),
            "closes": {s: (core.get(s) or {}).get("close") for s in ("QQQ", "QQQM", "VGT", "VOO")},
            "drawdowns": {s: (core.get(s) or {}).get("drawdown") for s in ("QQQ", "QQQM", "VGT", "VOO")}}


def checkpoint_records(ev_key, ev, now, market=None, tranche_state=None, existing=None):
    """New append-only records for checkpoints whose session is complete and present in the market data."""
    market = market or market_snapshot()
    existing = existing if existing is not None else read_records(ev_key)
    have = {r["checkpoint"] for r in existing}
    base = next((r for r in existing if r["checkpoint"] == "T-1"), None)
    cp = ev["checkpoints"]
    rel = ts(ev["release"]["utc"])
    new = []
    for k in CHECKPOINTS:
        if k in have:
            continue
        d = cp[k]
        if market.get("as_of") != d:
            continue  # only record a checkpoint from data whose as_of is exactly that session — never backfill
        if k == "T-1":
            if now >= rel:
                continue  # a baseline captured after the release is not a baseline
        elif ev.get("outcome_status") != "recorded":
            continue
        rec = {"record_version": 1, "event": ev_key, "checkpoint": k, "session": d, "recorded_at": iso(now),
               "market_as_of": market["as_of"], "market": market, "tranche_state": tranche_state,
               "official_outcome_sha256": ((ev.get("official_outcome") or {}).get("official_source") or {}).get("data_sha256"),
               "surprise": ev.get("surprise"), "production_use": False, "used_in_decision": False}
        if k != "T-1":
            if base:
                rec["vs_baseline"] = {s: (None if not (base["market"]["closes"].get(s) and market["closes"].get(s)) else
                                          round(market["closes"][s] / base["market"]["closes"][s] - 1, 4)) for s in market["closes"]}
                rec["baseline_session"] = base["session"]
            else:
                rec["vs_baseline"] = None
                rec["baseline_status"] = "baseline_unavailable (no T-1 snapshot captured before release; not reconstructed)"
            rec["author_forecast_check"] = {"forecast": "约三周内见底", "status": "pending",
                                            "note": "evaluated only when the preregistered window closes; never rewritten"}
            rec["risk_note_zh"] = ("Shadow 记录：事件后市场与基线的差异只是观察，不代表因果，也不是买卖依据；"
                                   "惊喜方向未知时（无共识）不归因于 CPI。")
        new.append(rec)
    return new


def read_records(ev_key):
    p = RECORDS / f"{ev_key}.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(p, rows):
    if not rows:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def run(now=None, recheck=False):
    now = now or datetime.now(timezone.utc)
    cal = _load(EVENTS)
    changed = False
    notes = []
    for key in CPI_EVENTS:
        ev = cal["events"][key]
        if recheck and ev.get("outcome_status") == "recorded":
            ev = {**ev, "outcome_status": "recheck"}
        new, log = step(key, ev, now)
        if recheck and new.get("outcome_status") == "recorded" and cal["events"][key].get("official_outcome"):
            old = cal["events"][key]["official_outcome"]["values"]
            if old != new["official_outcome"]["values"]:
                new = {**cal["events"][key], "outcome_status": "conflict",
                       "outcome_status_detail": "re-fetch changed recorded official values — kept original, flagged"}
            else:
                new = cal["events"][key]
        if new != cal["events"][key]:
            cal["events"][key] = new
            changed = True
        append_jsonl(LOG, [log] if log else [])
        notes.append(f"{key}={new.get('outcome_status')}")
    if changed:
        EVENTS.write_text(json.dumps(cal, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    # checkpoint records use the tranche state evaluated on the (possibly updated) calendar
    st = bl.evaluate(bl.gather(now))
    tstate = {"overall": st["overall"], **{k: v["state"] for k, v in st["tranches"].items()}, "rules_version": st["rules_version"]}
    for key in CPI_EVENTS:
        rows = checkpoint_records(key, cal["events"][key], now, tranche_state=tstate)
        append_jsonl(RECORDS / f"{key}.jsonl", rows)
        if rows:
            notes.append(f"{key}:checkpoints+{','.join(r['checkpoint'] for r in rows)}")
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recheck", action="store_true")
    a = ap.parse_args()
    notes = run(recheck=a.recheck)
    print("::notice title=Macro official outcomes::" + " ".join(notes))


if __name__ == "__main__":
    main()
