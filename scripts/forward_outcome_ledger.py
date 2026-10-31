#!/usr/bin/env python3
"""FWD-01 L1/L2: score matured forward observations under the frozen contract fsc-1.0.

Inputs (append-only, never modified here):
  research/archive/forward_observations.jsonl           genuine forward (fo-1.0, server_daily)
  research/archive/forward_observations_promoted.jsonl  owner-approved historical reconstruction
  config/forward_scoring_contract.json                  fsc-1.0 (hash-pinned; mismatch -> fail closed)
Outputs:
  research/archive/forward_outcomes.jsonl      append-only; corrections are new rows with `supersedes`
  research/archive/corporate_actions.jsonl     append-only split events (Yahoo chart events=splits)
  docs/research/forward_scorecard.json         aggregate only (no positions, no amounts)

Prices are only the ledgers' own `payload.close` (written once at capture, never re-fetched, never mixed with
auto-adjusted series). Returns are price returns excluding dividends, split-adjusted from recorded split events.
`as_of` is the latest session in the genuine ledger, so the scorer is deterministic and needs no wall clock.
Lifecycle per (event_id, horizon, contract): pending (derived, never written) -> matured | unavailable;
a later different result for the same key is appended with `supersedes` (late price, newly recorded split).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

CONTRACT = ROOT / "config" / "forward_scoring_contract.json"
GENUINE = ROOT / "research" / "archive" / "forward_observations.jsonl"
PROMOTED = ROOT / "research" / "archive" / "forward_observations_promoted.jsonl"
OUTCOMES = ROOT / "research" / "archive" / "forward_outcomes.jsonl"
ACTIONS = ROOT / "research" / "archive" / "corporate_actions.jsonl"
OUT = ROOT / "docs" / "research" / "forward_scorecard.json"

PINNED = ("fsc-1.0", "3eb0efc58e3eba8b")
# fsc-1.1 (Owner 10/30): a PARALLEL VIEW derived from the fsc-1.0 outcome rows; it never writes outcome rows and
# never replaces the official fsc-1.0 scorecard until the Owner approves the switch.
PINNED_V11 = ("fsc-1.1", "e1fc145c3a3e4e33")
CONTRACT_V11 = ROOT / "config" / "forward_scoring_contract_v1_1.json"
SCORER_VERSION = "fol-1.0"
LATE_GRACE_SESSIONS = 3          # a missing maturity close stays pending this long (owner-agreed, #133 6383888703)
GAP_LIMIT = 0.40                 # |day-over-day| move above this with no recorded split -> split_unverified
PRICE_BASIS = "price_return_ex_dividends_split_adjusted_ledger_close"
PRICE_BASIS_ZH = ("价格收益：只用账本捕获时的收盘价计算，按已核实的拆股换算；不含股息，也不做股息再投资"
                  "（名称中的 ex_dividends 指不含股息，不是已做股息调整）。")
MAE_BASIS_ZH = "最大不利变动（MAE）按每日收盘价计算，不代表盘中最大不利波动；任一交易日缺数据时不计算。"
OPS = {">": lambda a, b: a > b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b}


class ContractError(RuntimeError):
    pass


# ---------- io ----------
def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def lines_of(path):
    return [x for x in (path.read_text(encoding="utf-8").splitlines() if path.exists() else []) if x.strip()]


def committed_lines(path):
    try:
        rel = path.relative_to(ROOT).as_posix()
        out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [x for x in out.splitlines() if x.strip()]
    except Exception:
        return []


def check_append_only(old_lines, new_lines):
    if len(new_lines) < len(old_lines):
        return False, "ledger_shrank"
    if new_lines[:len(old_lines)] != old_lines:
        return False, "prior_line_changed"
    return True, "ok"


def dump(row):
    return json.dumps(row, ensure_ascii=False, sort_keys=True)


def sha(text, n=16):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


# ---------- contract ----------
def load_contract(path=CONTRACT):
    c = json.loads(path.read_text(encoding="utf-8"))
    digest = sha(json.dumps(c["rules"], ensure_ascii=False, sort_keys=True))
    if (c.get("contract_id"), digest) != PINNED:
        raise ContractError(f"contract_mismatch:{c.get('contract_id')}:{digest}")
    return c, digest


def load_contract_v11(path=None):
    path = path or CONTRACT_V11
    c = json.loads(Path(path).read_text(encoding="utf-8"))
    digest = sha(json.dumps(c["rules"], ensure_ascii=False, sort_keys=True))
    if (c.get("contract_id"), digest) != PINNED_V11 or (c.get("based_on") or {}).get("hash") != PINNED[1]:
        raise ContractError(f"contract_mismatch:{c.get('contract_id')}:{digest}")
    return c, digest


def view_v11(current, contract_v11):
    """fsc-1.1 view of fsc-1.0 outcome rows: benchmark-identical symbols leave hit/miss (copies; originals untouched)."""
    excluded = set(contract_v11["rules"]["benchmark_identical_symbols"])
    out = []
    for o in current:
        if o.get("symbol") in excluded and o.get("status") == "matured" and o.get("hit") in (True, False):
            o = {**o, "hit": "benchmark_identical"}
        out.append(o)
    return out


def hit_of(rules, decision, excess):
    rule = rules["classes"].get(decision)
    if rule is None:
        return "unscored_unmapped"
    if rule["hit_if"] is None:
        return "abstain"
    h = rule["hit_if"]
    return bool(OPS[h["op"]](excess, h["value"]))


# ---------- prices & splits ----------
def price_index(genuine, promoted):
    """(symbol, session) -> (close, source event_id). Genuine wins on overlap; both are capture-time closes."""
    px = {}
    for rows in (promoted, genuine):
        for r in rows:
            c = (r.get("payload") or {}).get("close")
            if isinstance(c, (int, float)) and c > 0:
                px[(r["symbol"], r["session"])] = (float(c), r["event_id"])
    return px


def split_events(actions):
    ev = defaultdict(list)
    for a in actions:
        if a.get("type") == "split" and float(a.get("ratio") or 0) > 0:
            ev[a["symbol"]].append((a["ex_date"], float(a["ratio"]), a["action_id"]))
    return ev


def factor(ev, symbol, start, end):
    """Product of split ratios with start < ex_date <= end (post-split close x factor = pre-split basis)."""
    f, refs = 1.0, []
    for d, ratio, aid in ev.get(symbol, []):
        if start < d <= end:
            f *= ratio
            refs.append(aid)
    return f, refs


def _between(start, end):
    out, d = [], tc.next_session(_d(start))
    while d <= _d(end):
        out.append(d.isoformat())
        d = tc.next_session(d)
    return out


def _d(s):
    from datetime import date
    return date.fromisoformat(s)


# ---------- scoring ----------
def score_one(row, group, h, contract_id, contract_hash, rules, px, ev, as_of):
    """Return an outcome dict, or None while pending (never written)."""
    sym, s0 = row["symbol"], row["session"]
    md = tc.add_sessions(_d(s0), h).isoformat()
    base = {"event_id": row["event_id"], "group": group, "symbol": sym, "session": s0, "h": h, "matures_on": md,
            "decision": (row.get("payload") or {}).get("decision"), "eligible": bool((row.get("payload") or {}).get("eligible")),
            "market_mode": (row.get("market") or {}).get("mode"), "contract_id": contract_id,
            "contract_hash": contract_hash, "scorer_version": SCORER_VERSION, "price_basis": PRICE_BASIS,
            "rule_hash": row.get("rule_hash"), "benchmark": rules["benchmark"], "as_of": as_of}
    recorded = (row.get("matures") or {}).get(str(h))
    if recorded is not None and recorded != md:
        return {**base, "status": "invalid", "reason": f"matures_mismatch:{recorded}"}
    if md > as_of:
        return None
    late_cutoff = tc.add_sessions(_d(md), LATE_GRACE_SESSIONS).isoformat()

    def unavailable(reason, **extra):
        if as_of < late_cutoff:
            return None  # still inside the late-data grace: stays pending
        return {**base, "status": "unavailable", "reason": reason, **extra}

    bench = rules["benchmark"]
    start = px.get((sym, s0))
    if start is None:
        start = ((row.get("payload") or {}).get("close"), row["event_id"])
    if not isinstance(start[0], (int, float)) or start[0] <= 0:
        return {**base, "status": "unavailable", "reason": "missing_start_close"}
    b0 = px.get((bench, s0))
    end, b1 = px.get((sym, md)), px.get((bench, md))
    if end is None:
        return unavailable("missing_end_close")
    if b0 is None or b1 is None:
        return unavailable("missing_benchmark")

    days = _between(s0, md)
    covered = [d for d in days if (sym, d) in px]
    bcovered = [d for d in days if (bench, d) in px]
    # unexplained gaps (|move| > 40% between consecutive available closes, after recorded splits)
    for who, cov in ((sym, covered), (bench, bcovered)):
        prev_d, prev_c = s0, px[(who, s0)][0]
        for d in cov:
            c = px[(who, d)][0] * factor(ev, who, prev_d, d)[0]
            if abs(c / prev_c - 1) > GAP_LIMIT:
                return {**base, "status": "unavailable", "reason": "split_unverified", "gap": {"symbol": who, "from": prev_d, "to": d}}
            prev_d, prev_c = d, px[(who, d)][0]

    f, refs = factor(ev, sym, s0, md)
    bf, brefs = factor(ev, bench, s0, md)
    ret = end[0] * f / start[0] - 1
    bret = b1[0] * bf / b0[0] - 1
    excess = ret - bret
    missing = [d for d in days if d not in covered]
    bmissing = [d for d in days if d not in bcovered]
    if not missing and not bmissing:
        mae = min(px[(sym, d)][0] * factor(ev, sym, s0, d)[0] / start[0] - 1 for d in days)
        mae_status = "ok"
    else:
        mae, mae_status = None, "unavailable(coverage_incomplete)"
    return {**base, "status": "matured", "reason": None,
            "start_ref": start[1], "end_ref": end[1], "bench_start_ref": b0[1], "bench_end_ref": b1[1],
            "split_factor": f, "split_refs": refs, "bench_split_factor": bf, "bench_split_refs": brefs,
            "ret": round(ret, 6), "bench_ret": round(bret, 6), "excess_vs_qqq": round(excess, 6),
            "hit": hit_of(rules, base["decision"], excess),
            "mae": None if mae is None else round(mae, 6), "mae_status": mae_status,
            "mae_coverage": {"expected": len(days), "covered": len(covered), "missing_sessions": missing,
                             "bench_covered": len(bcovered), "bench_missing_sessions": bmissing,
                             "basis": "ledger daily closes; not intraday lows"}}


RESULT_KEYS = ("status", "reason", "ret", "bench_ret", "excess_vs_qqq", "hit", "mae", "mae_status", "split_factor",
               "bench_split_factor", "start_ref", "end_ref", "bench_start_ref", "bench_end_ref", "matures_on")


def result_sha(o):
    return sha(json.dumps({k: o.get(k) for k in RESULT_KEYS}, ensure_ascii=False, sort_keys=True))


def plan(genuine, promoted, actions, existing, contract, contract_hash, scored_at, source_sha=None, hold=()):
    """Pure: outcomes to append (new keys, or a changed result -> supersedes), plus the current view."""
    rules = contract["rules"]
    cid = contract["contract_id"]
    px, ev = price_index(genuine, promoted), split_events(actions)
    as_of = max((r["session"] for r in genuine), default="0000-00-00")
    latest = {}
    counts = Counter()
    for o in existing:
        k = (o["event_id"], o["h"], o["contract_id"])
        latest[k] = o
        counts[k] += 1
    groups = (("genuine_forward", genuine), ("promoted", promoted))
    seen_ids = set()
    add, current, pending = [], [], Counter()
    for group, rows in groups:
        for r in rows:
            if r["event_id"] in seen_ids:
                raise ContractError(f"duplicate_event_id:{r['event_id']}")
            seen_ids.add(r["event_id"])
            for h in rules["horizons_sessions"]:
                k = (r["event_id"], h, cid)
                # hold: split lookup failed this run -> no new result for this symbol (treated as pending)
                o = None if r["symbol"] in hold else score_one(r, group, h, cid, contract_hash, rules, px, ev, as_of)
                if o is None:
                    pending[(group, h)] += 1
                    if k in latest:
                        current.append(latest[k])
                    continue
                o["result_sha"] = result_sha(o)
                prev = latest.get(k)
                if prev is not None and prev.get("result_sha") == o["result_sha"]:
                    current.append(prev)
                    continue
                o["outcome_id"] = sha(f"{r['event_id']}|{h}|{cid}|{counts[k]}", 24)
                o["supersedes"] = prev["outcome_id"] if prev else None
                o["scored_at"] = scored_at
                o["source_sha"] = source_sha
                add.append(o)
                current.append(o)
    return add, current, pending, as_of


def scorecard(current, pending, as_of, contract, contract_hash, generated_at):
    rules = contract["rules"]
    minimum = rules["min_n_for_rate"]
    cells = defaultdict(Counter)
    episodes = defaultdict(Counter)
    regimes = defaultdict(set)
    by_sym = defaultdict(list)
    for o in current:
        by_sym[(o["group"], o["h"], o["symbol"])].append(o)
    first_of_run = set()
    for (_, _, _), rows in by_sym.items():
        rows.sort(key=lambda x: x["session"])
        prev = None
        for o in rows:
            run_continues = prev is not None and prev["decision"] == o["decision"] and \
                tc.next_session(_d(prev["session"])).isoformat() == o["session"]
            if not run_continues:
                first_of_run.add(o["outcome_id"])
            prev = o
    for o in current:
        key = (o["group"], o["h"], o["decision"], o["eligible"])
        c = cells[key]
        c["rows"] += 1
        if o["status"] != "matured":
            c[o["status"]] += 1
            continue
        c["matured"] += 1
        regimes[(o["group"], o["h"])].add((o["session"], o.get("market_mode")))
        h = o["hit"]
        tag = "hit" if h is True else "miss" if h is False else h
        c[tag] += 1
        if o["outcome_id"] in first_of_run:
            episodes[key]["episodes"] += 1
            episodes[key]["episode_" + tag] += 1
    out_cells = []
    for key in sorted(cells, key=lambda k: (k[0], k[1], str(k[2]), k[3])):
        g, h, dec, el = key
        c, e = cells[key], episodes[key]
        scored = c["hit"] + c["miss"]
        escored = e["episode_hit"] + e["episode_miss"]
        out_cells.append({
            "group": g, "h": h, "decision": dec, "eligible": el, "matured": c["matured"],
            "unavailable": c["unavailable"], "invalid": c["invalid"], "abstain": c["abstain"],
            "unscored_unmapped": c["unscored_unmapped"], "benchmark_identical": c["benchmark_identical"],
            "scored": scored, "hits": c["hit"],
            "hit_rate": round(c["hit"] / scored, 4) if scored >= minimum else None,
            "status": "reportable_minimum_only" if scored >= minimum else "INSUFFICIENT",
            "independent_episodes": e["episodes"], "episode_scored": escored,
            "episode_hit_rate": round(e["episode_hit"] / escored, 4) if escored >= minimum else None,
        })
    return {
        "version": 1, "generated_at": generated_at, "as_of_session": as_of,
        "contract_id": contract["contract_id"], "contract_hash": contract_hash, "scorer_version": SCORER_VERSION,
        "price_basis": PRICE_BASIS, "mae_basis": "ledger daily closes only; null when any session is missing",
        # plain-language reading of the two basis codes above (display text only; fsc-1.0 contract and hash unchanged)
        "price_basis_zh": PRICE_BASIS_ZH, "mae_basis_zh": MAE_BASIS_ZH,
        "late_grace_sessions": LATE_GRACE_SESSIONS, "gap_limit": GAP_LIMIT,
        "learning_state": "UNPROVEN",
        "note": "n>=20 is only the minimum reporting threshold, not proof of predictive skill; genuine_forward and "
                "promoted are never pooled; historical reconstruction is not genuine forward evidence.",
        "pending": [{"group": g, "h": h, "rows": n} for (g, h), n in sorted(pending.items())],
        "regime_coverage": [{"group": g, "h": h, "sessions": len({s for s, _ in v}),
                             "modes": dict(Counter(m for _, m in v))} for (g, h), v in sorted(regimes.items())],
        "cells": out_cells,
    }


# ---------- corporate actions (network, only for keys about to be scored) ----------
def fetch_splits(symbol, timeout=15):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2y&events=splits"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    out = []
    for v in (result.get("events", {}).get("splits", {}) or {}).values():
        num, den = float(v["numerator"]), float(v["denominator"])
        if num > 0 and den > 0:
            ex = datetime.fromtimestamp(int(v["date"]), timezone.utc).date().isoformat()
            out.append({"type": "split", "symbol": symbol, "ex_date": ex, "ratio": num / den,
                        "numerator": num, "denominator": den, "source": "yahoo_chart_events_splits"})
    return out


def refresh_actions(symbols, actions, fetched_at, fetch=fetch_splits):
    """Append newly seen split events (dedupe by symbol/ex_date/ratio). Returns (new_rows, failed_symbols)."""
    have = {(a["symbol"], a["ex_date"], round(float(a["ratio"]), 8)) for a in actions}
    new, failed = [], []
    for s in sorted(symbols):
        try:
            for e in fetch(s):
                k = (e["symbol"], e["ex_date"], round(e["ratio"], 8))
                if k not in have:
                    have.add(k)
                    e["action_id"] = sha(f"{k[0]}|{k[1]}|{k[2]}", 16)
                    e["first_seen"] = fetched_at
                    new.append(e)
        except Exception as exc:  # noqa: BLE001 - recorded, never silently treated as "no split"
            failed.append(f"{s}:{type(exc).__name__}")
    return new, failed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="do not query split events")
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    contract, digest = load_contract()
    genuine, promoted = read_jsonl(GENUINE), read_jsonl(PROMOTED)
    actions = read_jsonl(ACTIONS)
    existing = read_jsonl(OUTCOMES)
    as_of = max((r["session"] for r in genuine), default="0000-00-00")

    # splits are refreshed only for symbols with something maturing (and the benchmark); a failed lookup keeps
    # those keys out of this run (they stay pending inside the grace window, then are retried).
    due = {r["symbol"] for rows in (genuine, promoted) for r in rows
           for h in contract["rules"]["horizons_sessions"] if tc.add_sessions(_d(r["session"]), h).isoformat() <= as_of}
    failed = []
    if due and not a.offline:
        due.add(contract["rules"]["benchmark"])
        new_actions, failed = refresh_actions(due, actions, now)
        actions = actions + new_actions
        if new_actions:
            ok, why = check_append_only(committed_lines(ACTIONS), lines_of(ACTIONS) + [dump(x) for x in new_actions])
            if not ok:
                print(f"::error title=Forward outcomes::APPEND_ONLY_VIOLATION corporate_actions {why}")
                return 1
            ACTIONS.parent.mkdir(parents=True, exist_ok=True)
            with ACTIONS.open("a", encoding="utf-8") as fh:
                fh.writelines(dump(x) + "\n" for x in new_actions)
    if failed:
        print(f"::warning title=Forward outcomes::SPLIT_LOOKUP_FAILED {','.join(failed)[:300]}")

    add, current, pending, as_of = plan(genuine, promoted, actions, existing, contract, digest, now,
                                        os.getenv("GITHUB_SHA"), hold={x.split(":")[0] for x in failed})
    new_lines = lines_of(OUTCOMES) + [dump(x) for x in add]
    ok, why = check_append_only(committed_lines(OUTCOMES), new_lines)
    if not ok:
        print(f"::error title=Forward outcomes::APPEND_ONLY_VIOLATION forward_outcomes {why}")
        return 1
    if add:
        OUTCOMES.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUTCOMES.with_suffix(".tmp")
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        os.replace(tmp, OUTCOMES)
    sc = scorecard(current, pending, as_of, contract, digest, now)
    sc["split_lookup_failed"] = failed
    # fsc-1.1 parallel view (fail-soft: a missing/mismatched v1.1 file never touches the official fsc-1.0 output)
    try:
        c11, d11 = load_contract_v11()
        v = scorecard(view_v11(current, c11), pending, as_of, contract, digest, now)
        sc["parallel_views"] = [{"contract_id": c11["contract_id"], "contract_hash": d11, "status": c11["status"],
                                 "based_on": c11["based_on"], "excluded_symbols": c11["rules"]["benchmark_identical_symbols"],
                                 "official": False, "cells": v["cells"]}]
    except (OSError, ValueError, KeyError, ContractError) as exc:
        sc["parallel_views"] = [{"contract_id": "fsc-1.1", "status": "unavailable", "reason": type(exc).__name__}]
        print(f"::warning title=Forward outcomes::FSC_1_1_VIEW_UNAVAILABLE {exc}"[:300])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(sc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sup = sum(1 for x in add if x.get("supersedes"))
    status = Counter(x["status"] for x in add)
    print(f"::notice title=Forward outcomes::FWD_OUTCOMES as_of={as_of} added={len(add)} superseding={sup} "
          f"status={dict(status)} pending={sum(pending.values())} split_lookup_failed={len(failed)}")
    if sup:
        print(f"::warning title=Forward outcomes::FWD_OUTCOMES_SUPERSEDED {sup} result(s) changed; appended, originals kept")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
