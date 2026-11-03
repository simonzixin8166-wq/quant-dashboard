#!/usr/bin/env python3
"""Offline, read-only report for one matured forward cohort (11/5 acceptance + fea-0.2 attribution + rfi-0.1).

Specs (#133): stage-0 checklist 6512706287 §C, GPT review 6513028156, Claude v0.2 6513057000 (Owner-approved
6513072588), fea-0.1 6512922683 -> fea-0.2, rfi-0.1 (rule families / independence).
Reads committed ledgers / outcomes / contract / SEC archive of a quant-dashboard checkout. Writes nothing
(scripts/forward_attribution_weekly.py writes the weekly summary from run()).

  python fwd_cohort_report.py --repo . --group genuine_forward --sessions 2026-10-08 --h 20
  python fwd_cohort_report.py --repo . --group promoted --sessions 2026-09-29,2026-09-30 --h 20   # pilot

Attribution never changes hit/miss. Same checks run on hits and misses. Unobservable -> unknown, never "none".
"""
import argparse, glob, hashlib, json, sys
import datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

FEA = {"version": "fea-0.2", "h": 20, "noise_band": 0.01, "event_share": 0.5, "shock_drop": -0.03,
       "checkpoints": (5, 10, 15), "regime_share": 0.25, "regime_min_days": 15,
       "order": ["S1", "D1", "D2", "M2", "M1", "E1", "E2", "R4", "R3", "R0"]}
BENCH_IDENTICAL = {"QQQ", "QQQM"}                 # Owner 10/30 (fsc-1.1 scope)
UNDERLYING = {"QQQ": "NDX", "QQQM": "NDX", "QLD": "NDX", "TQQQ": "NDX", "SPY": "SPX", "VOO": "SPX"}  # rfi-0.1
BROAD = {"SPY", "VOO", "QLD", "TQQQ"}             # descriptive flag broad_index_vs_broad_index
CONFIRMED_DEFECTS = {}                            # S1: {event_id: "E-xx"}; filled only from confirmed records


def rd(p):
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()] if Path(p).exists() else []


def sha_rows(rows):
    return hashlib.sha256("\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows).encode()).hexdigest()[:16]


def run(root, group="genuine_forward", sessions=None, h=20, stamp=True):
    """Build the report. Returns (markdown lines, issues, summary dict). Read-only.

    sessions=None -> every session whose rows all have a matured/final h outcome (the weekly job's cohort)."""
    a = argparse.Namespace(group=group, h=h, sessions=None)
    root = Path(root)
    sys.path.insert(0, str(root / "scripts"))
    import trading_calendar as tc
    import forward_outcome_ledger as fol

    if a.h != FEA["h"]:
        print(f"fea-0.2 applies to h=20 only; h={a.h} -> attribution NOT RUN")
    arch = root / "research" / "archive"
    gen, pro = rd(arch / "forward_observations.jsonl"), rd(arch / "forward_observations_promoted.jsonl")
    ledger = gen if a.group == "genuine_forward" else pro
    outcomes = [o for o in rd(arch / "forward_outcomes.jsonl") if o.get("group") == a.group and o.get("h") == a.h]
    contract, digest = fol.load_contract(root / "config" / "forward_scoring_contract.json")
    rules = contract["rules"]["classes"]
    if sessions is None:
        done = {o["event_id"] for o in outcomes if o.get("status") != "pending"}
        by_s = defaultdict(list)
        for r in ledger:
            by_s[r["session"]].append(r["event_id"] in done)
        sessions = sorted(s for s, v in by_s.items() if v and all(v))
    elif isinstance(sessions, str):
        sessions = sessions.split(",")
    a.sessions = ",".join(sessions) if sessions else "(none matured)"

    # closes and modes from both ledgers (the scorer's own price basis)
    close, mode = defaultdict(dict), {}
    for r in gen + pro:
        close[r["symbol"]][r["session"]] = r["payload"]["close"]
        mode.setdefault(r["session"], (r.get("market") or {}).get("mode"))
    D = dt.date.fromisoformat
    add = lambda s, k: str(tc.add_sessions(D(s), k))
    nxt = lambda s: str(tc.next_session(D(s)))
    prv = lambda s: str(tc.previous_session(D(s)))

    def excess(sym, s0, s1):
        try:
            return (close[sym][s1] / close[sym][s0] - 1) - (close["QQQ"][s1] / close["QQQ"][s0] - 1)
        except KeyError:
            return None

    # earnings (8-K Item 2.02) filing dates
    earn = defaultdict(set)
    for f in glob.glob(str(arch / "sec_filings" / "*.jsonl")):
        for r in rd(f):
            if r.get("form") == "8-K" and "Item 2.02" in " ".join(r.get("excerpts") or []):
                earn[r.get("symbol")].add(r.get("filing_date"))

    # rfi-0.1 episodes over the whole ledger
    ep_start, by = {}, defaultdict(list)
    for r in ledger:
        by[r["symbol"]].append(r)
    for sym, rs in by.items():
        rs.sort(key=lambda r: r["session"])
        prev = None
        for r in rs:
            cont = prev is not None and prev["payload"]["decision"] == r["payload"]["decision"] and nxt(prev["session"]) == r["session"]
            ep_start[r["event_id"]] = not cont
            prev = r

    def indep(xs):
        seen, res = set(), []
        for x in xs:
            if not ep_start.get(x[0]["event_id"]):
                continue
            k = (x[0]["session"], UNDERLYING.get(x[0]["symbol"], x[0]["symbol"]), x[0]["payload"]["decision"])
            if k not in seen:
                seen.add(k); res.append(x)
        return res

    cohort = [r for r in ledger if r["session"] in sessions]
    oc = {o["event_id"]: o for o in outcomes}
    out, issues = [], []
    P = out.append
    P(f"# Cohort report · {a.group} · sessions {a.sessions} · h={a.h}")
    P(f"- contract `{contract['contract_id']}` hash `{digest}`; attribution `{FEA['version']}`; independence `rfi-0.1`")
    # reproducibility (GPT #133 6537701769 §4.6): script + input snapshots
    P(f"- script sha256 `{hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]}`; inputs sha256: "
      + ", ".join(f"{n} `{hashlib.sha256((arch / n).read_bytes()).hexdigest()[:16]}`" for n in
                  ("forward_observations.jsonl", "forward_observations_promoted.jsonl", "forward_outcomes.jsonl")
                  if (arch / n).exists())
      + (f"; run at {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}" if stamp else ""))
    P(f"- ledger rows in cohort: **{len(cohort)}**; outcomes found: {sum(1 for r in cohort if r['event_id'] in oc)}; "
      f"cohort sha `{sha_rows(cohort)}`; outcomes sha `{sha_rows([oc[r['event_id']] for r in cohort if r['event_id'] in oc])}`")

    # ---------- §1 row-by-row reconciliation ----------
    P("\n## 1. Row-by-row reconciliation")
    P("| symbol | session | decision | matures | status | reason | start_ref | end | bench | excess | hit | contract | episode_start |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    rows = []
    for r in sorted(cohort, key=lambda r: (r["session"], r["symbol"])):
        o = oc.get(r["event_id"])
        st = o["status"] if o else "pending"
        if o and o.get("contract_hash") != digest:
            issues.append(f"{r['symbol']}: contract_hash {o.get('contract_hash')}")
        if o and o.get("matures_on") != r["matures"].get(str(a.h)):
            issues.append(f"{r['symbol']}: matures_on {o.get('matures_on')} != ledger {r['matures'].get(str(a.h))}")
        if o and st == "matured" and (o.get("start_ref") != r["event_id"] or not o.get("bench_end_ref")):
            issues.append(f"{r['symbol']}: refs")
        hit = None if not o else ("abstain" if o.get("hit") is None and st == "matured" else o.get("hit"))
        rows.append((r, o, st, hit))
        P(f"| {r['symbol']} | {r['session']} | {r['payload']['decision']} | {r['matures'].get(str(a.h))} | {st} | "
          f"{(o or {}).get('reason') or ''} | {(o or {}).get('start_ref', '')[:8]} | {(o or {}).get('matures_on', '')} | "
          f"{(o or {}).get('bench_end_ref', '')[:8]} | {'' if not o or o.get('excess_vs_qqq') is None else f'{o['excess_vs_qqq']:+.4f}'} | "
          f"{hit} | {(o or {}).get('contract_hash', '')} | {ep_start.get(r['event_id'])} |")

    # ---------- §2 denominators, incl./excl. QQQ+QQQM ----------
    def denom(rs):
        c = Counter()
        for r, o, st, hit in rs:
            c["rows"] += 1
            if st == "pending": c["pending"] += 1
            elif st == "invalid": c["invalid"] += 1
            elif st != "matured": c["unavailable"] += 1
            elif hit == "abstain": c["abstain"] += 1
            else:
                c["scored"] += 1; c["hit" if hit else "miss"] += 1
        return dict(c)
    P("\n## 2. Denominators (mutually exclusive; scored = hit + miss; abstain/unavailable/invalid/pending never in a rate)")
    inc, exc = denom(rows), denom([x for x in rows if x[0]["symbol"] not in BENCH_IDENTICAL])
    for name, d in (("including QQQ/QQQM", inc), ("excluding QQQ/QQQM", exc)):
        parts = sum(d.get(k, 0) for k in ("pending", "invalid", "unavailable", "abstain", "scored"))
        ok = parts == d.get("rows", 0) and d.get("scored", 0) == d.get("hit", 0) + d.get("miss", 0)
        P(f"- {name}: rows {d.get('rows', 0)} = pending {d.get('pending', 0)} + invalid {d.get('invalid', 0)} + "
          f"unavailable {d.get('unavailable', 0)} + abstain {d.get('abstain', 0)} + scored {d.get('scored', 0)} "
          f"(hit {d.get('hit', 0)} + miss {d.get('miss', 0)}) -> {'consistent' if ok else 'INCONSISTENT'}")
        if not ok:
            issues.append(f"denominator inconsistent ({name})")
    if inc.get("invalid"):
        issues.append("invalid rows present -> acceptance conclusion SUSPENDED (find the cause; never re-class as unavailable)")
    by_cls = defaultdict(list)
    for x in rows:
        by_cls[x[0]["payload"]["decision"]].append(x)
    for cls, rs in sorted(by_cls.items()):
        d = denom(rs)
        ind = indep([x for x in rs if x[2] == "matured" and x[3] != "abstain"])
        weeks = len({D(x[0]["session"]).isocalendar()[1] for x in ind})
        ok = len(ind) >= 20 and weeks >= 4
        P(f"  - {cls}: {d}; independent scored episodes {len(ind)}, entry weeks {weeks} -> "
          f"{'reportable (rfi-0.1)' if ok else 'INSUFFICIENT (rfi-0.1: need >=20 independent episodes and >=4 weeks)'}")

    # ---------- §3 independence (rfi-0.1) ----------
    P("\n## 3. Independence (rfi-0.1)")
    eps = [x for x in rows if ep_start.get(x[0]["event_id"])]
    ind = indep(rows)
    P(f"- rows {len(rows)} -> episode starts {len(eps)} -> after same-index collapse {len(ind)}; "
      f"distinct entry sessions {len({x[0]['session'] for x in rows})}; "
      f"regimes at entry {dict(Counter(x[0]['market'].get('mode') for x in rows))}")

    # ---------- §4 attribution (fea-0.2) ----------
    prim, inf_hit = Counter(), Counter()
    if a.h == FEA["h"] and rows:
        P("\n## 4. Attribution (fea-0.2; explains, never re-scores)")
        P("| symbol | session | decision | hit | excess | primary | secondary | path 5/10/15 | event | mode_share | process_ok | informative | flags |")
        P("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r, o, st, hit in rows:
            if st != "matured" or hit == "abstain":
                continue
            sym, s0, end, x = r["symbol"], r["session"], o["matures_on"], o["excess_vs_qqq"]
            rule = rules[r["payload"]["decision"]]["hit_if"]
            sat = lambda v: v is not None and {"<": v < rule["value"], ">": v > rule["value"], "<=": v <= rule["value"]}[rule["op"]]
            noise = abs(x) < FEA["noise_band"]
            checks, ev, fired = {}, "n/a", []
            if r["event_id"] in CONFIRMED_DEFECTS: fired.append(("S1", "CONFIRMED"))
            if r.get("market_as_of") != s0: fired.append(("D1", "CONFIRMED"))
            if o.get("reason"): fired.append(("D2", "CONFIRMED"))
            if sym in BENCH_IDENTICAL: fired.append(("M2", "CONFIRMED"))
            if noise: fired.append(("M1", "CONFIRMED"))
            # E1 earnings
            if not noise and sym not in UNDERLYING and sym not in {"VGT", "SMH"}:
                fs = sorted(f for f in earn.get(sym, ()) if s0 <= f <= end)
                if not earn.get(sym):
                    ev = "unknown(no_filing_history)"
                elif not fs:
                    ev = "none_in_window"
                evs, e1 = [], False
                for f in fs:
                    w0, w1 = max(prv(f), s0), min(nxt(f), end)
                    ex = excess(sym, w0, w1)
                    if ex is None:
                        evs.append(f"{f}:unknown(missing_close)"); continue
                    evs.append(f"{f}:{ex:+.4f}")
                    if (ex > 0) == (x > 0) and abs(ex) >= FEA["event_share"] * abs(x):
                        e1 = True
                if evs:
                    ev = "; ".join(evs)
                if e1:
                    fired.append(("E1", "CONFIRMED"))
            # E2 market shock
            if not noise:
                s, shock = s0, None
                for _ in range(a.h):
                    s1 = nxt(s)
                    try:
                        q = close["QQQ"][s1] / close["QQQ"][s] - 1
                    except KeyError:
                        shock = shock or "unknown"; s = s1; continue
                    if q <= FEA["shock_drop"]:
                        dx = excess(sym, s, s1)
                        if dx is not None and (dx > 0) == (x > 0) and abs(dx) >= FEA["event_share"] * abs(x):
                            fired.append(("E2", "CONFIRMED")); break
                    s = s1
            # R4 timing (misses only, final outside noise band)
            path = [excess(sym, s0, add(s0, k)) for k in FEA["checkpoints"]]
            if not hit and not noise and sum(1 for v in path if sat(v)) >= 2 and not sat(x):
                fired.append(("R4", "CONFIRMED"))
            # R3 regime change
            win = [add(s0, k) for k in range(1, a.h + 1)]
            known = [mode.get(s) for s in win if mode.get(s)]
            m0 = (r.get("market") or {}).get("mode")
            if len(known) < FEA["regime_min_days"]:
                share = "unavailable(insufficient_regime_coverage)"
            else:
                share = round(sum(1 for m in known if m != m0) / len(known), 2)
                if share >= FEA["regime_share"] and not hit: fired.append(("R3", "CONFIRMED"))
            order = {c: i for i, c in enumerate(FEA["order"])}
            fired.sort(key=lambda t: order[t[0]])
            primary = fired[0][0] if fired else ("R0" if not hit else "-")
            # fea-0.2 §8: R0 is CONFIRMED only when every check was observable; any unknown -> UNKNOWN
            conf = dict(fired).get(primary, "CONFIRMED")
            if primary == "R0" and ("unknown" in str(ev) or not isinstance(share, float) or any(v is None for v in path)):
                conf = "UNKNOWN"
            primary_txt = f"{primary}({conf})" if primary != "-" else "-"
            secondary = [c for c, _ in fired[1:]]
            pok = all([r.get("market_as_of") == s0, r.get("source_sha"), r.get("rule_hash"), r.get("run_id")])
            pok = True if pok else "unknown"
            informative = primary not in {"M1", "M2"}
            flags = ["broad_index_vs_broad_index"] if sym in BROAD else []
            prim[(bool(hit), primary)] += 1
            inf_hit[("hit" if hit else "miss", informative)] += 1
            P(f"| {sym} | {s0} | {r['payload']['decision']} | {hit} | {x:+.4f} | {primary_txt} | {','.join(secondary)} | "
              f"{['n/a' if v is None else f'{v:+.3f}' for v in path]} | {ev} | {share} | {pok} | {informative} | {','.join(flags)} |")
        misses = sum(v for (h, _), v in prim.items() if not h)
        r0 = prim.get((False, "R0"), 0)
        P(f"\n- misses by primary: {dict((c, v) for (h, c), v in prim.items() if not h)}")
        P(f"- hits by primary: {dict((c, v) for (h, c), v in prim.items() if h)}")
        P(f"- unattributed_rate (R0 / misses): {r0}/{misses}; attribution_coverage: {misses - r0}/{misses}")
        P(f"- informative_hit {inf_hit[('hit', True)]}, uninformative_hit {inf_hit[('hit', False)]}; "
          f"informative_miss {inf_hit[('miss', True)]}, uninformative_miss {inf_hit[('miss', False)]}")

    P("\n## 5. Verdict")
    if inc.get("pending"):
        issues.append(f"{inc['pending']} rows still pending -> NOT RUN")
    P(f"- engineering acceptance: **{'PASS' if not issues else 'CHECK: ' + '; '.join(issues)}**")
    P("- investment validity: **INSUFFICIENT** unless a class above is marked reportable (rfi-0.1) · learning UNPROVEN / FINAL=NO")
    misses = sum(v for (hh, _), v in prim.items() if not hh)
    r0 = prim.get((False, "R0"), 0)
    summary = {
        "attribution_version": FEA["version"], "independence_version": "rfi-0.1",
        "contract_id": contract["contract_id"], "contract_hash": digest, "group": a.group, "h": a.h,
        "sessions": list(sessions or []), "rows": len(rows),
        "denominators_including_qqq_qqqm": inc, "denominators_excluding_qqq_qqqm": exc,
        "independent_scored_episodes": len(indep([x for x in rows if x[2] == "matured" and x[3] != "abstain"])),
        "misses_by_primary": {c: v for (hh, c), v in sorted(prim.items()) if not hh},
        "hits_by_primary": {c: v for (hh, c), v in sorted(prim.items()) if hh},
        "misses": misses, "unattributed_R0": r0,
        "attribution_coverage": None if not misses else round((misses - r0) / misses, 4),
        "engineering_acceptance": "PASS" if not issues else "CHECK", "issues": issues,
        "investment_validity": "INSUFFICIENT", "learning_state": "UNPROVEN", "final": "NO",
        "production_effect": "none",
    }
    return out, issues, summary


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--group", default="genuine_forward", choices=["genuine_forward", "promoted"])
    ap.add_argument("--sessions", required=True)
    ap.add_argument("--h", type=int, default=20)
    a = ap.parse_args(argv)
    out, issues, _ = run(a.repo, a.group, a.sessions, a.h)
    print("\n".join(out))
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
