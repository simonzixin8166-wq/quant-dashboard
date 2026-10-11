#!/usr/bin/env python3
"""MyAlpha daily automatic research job (#133 6109260776 P0-2 / 6109291884). Shadow only.

Runs on the server after the Daily update (and as an idempotent scheduled fallback). No Claude, no paid API,
no user visit. For every symbol in the canonical free price archive:

  ingestion   : canonical daily bars (data/history/stooq_watchlist.zip), trend_pulse (docs/data.json),
                FRED point-in-time macro (docs/research/macro_context.json), SEC filings on record
                (docs/research/auto_thesis_drafts.json — listed only, facts NOT extracted → 'unavailable'),
                recent author claims (wxc-bot state/author_claims_hp.json, ce-5, experimental) — each input is
                recorded with source, as_of and sha256
  eligibility : bars must be for the expected latest completed NYSE session and ≥200 sessions deep;
                otherwise the record is an explicit abstention (cannot_judge + reason)
  evidence    : computed metrics, each a signed evidence item citing its input
  analysis    : rule-based stance (bullish / neutral / bearish / cannot_judge), supporting vs opposing evidence,
                machine-checkable invalidation, horizon, next review date, risks — a research hint, never an order
  shadow-write: append-only research/knowledge/auto_research_journal.jsonl with generator_version, rule_hash,
                run_id, generated_at, market_as_of, input hashes, decision_reason, production_use=false
  revisit     : the previous active hypothesis of each symbol is re-checked on the new bar; status changes are
                appended as events (never overwrite); a stance change opens a new hypothesis that supersedes it

Idempotent: (symbol, market_as_of, generator_version, type) is written once. Status summary:
docs/research/auto_research_status.json (public data only).
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402
import knowledge_contract as kc  # noqa: E402

GENERATOR = "auto-research-1"
JOURNAL = ROOT / "research" / "knowledge" / "auto_research_journal.jsonl"
STATUS = ROOT / "docs" / "research" / "auto_research_status.json"
MACRO = ROOT / "docs" / "research" / "macro_context.json"
CLAIMS_URL = "https://raw.githubusercontent.com/simonzixin8166-wq/wxc-bot/main/state/author_claims_hp.json"
EXCLUDE = {"VIX"}
GROWTH = {"QQQ", "QQQM", "QLD", "TQQQ", "VGT", "SMH", "NVDA", "AMD", "MSFT", "TSM", "LITE", "AVGO", "MRVL", "NBIS",
          "GOOG", "ORCL", "TSLA", "IREN", "HOOD", "SOFI", "DRAM", "SPCX"}
HORIZON = 20
RULES = {"stretched_ma200": 0.15, "rsi_hot": 70, "rsi_cold": 30, "adx_weak": 20, "real_yield_jump_20d": 0.15,
         "vix_stress": 25, "near_high_pct": 0.03, "claim_days": 21}
RULE_HASH = hashlib.sha256(json.dumps({"rules": RULES, "view": "knowledge_contract.rule_view v1", "gen": GENERATOR},
                                      sort_keys=True).encode()).hexdigest()[:16]


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def archive_symbols():
    import zipfile
    with zipfile.ZipFile(kc.ARCHIVE) as z:
        return sorted(n.split("_")[0].upper() for n in z.namelist() if n.endswith("_us_d.csv"))


def load_inputs(fetch_claims=True):
    inputs = {"price_archive": {"source": "data/history/stooq_watchlist.zip", "sha256": sha_bytes(kc.ARCHIVE.read_bytes())},
              "trend_pulse": {"source": "docs/data.json", "sha256": sha_bytes(kc.DATA.read_bytes())}}
    macro = None
    if MACRO.exists():
        raw = MACRO.read_bytes()
        macro = json.loads(raw)
        inputs["fred_macro"] = {"source": "docs/research/macro_context.json", "sha256": sha_bytes(raw), "as_of": macro.get("as_of")}
    else:
        inputs["fred_macro"] = {"source": "docs/research/macro_context.json", "status": "unavailable"}
    filings_raw = kc.DRAFTS.read_bytes() if kc.DRAFTS.exists() else b""
    inputs["sec_filings_list"] = {"source": "docs/research/auto_thesis_drafts.json", "sha256": sha_bytes(filings_raw),
                                  "note": "filing list only; financial facts not extracted (unavailable)"}
    claims = []
    if fetch_claims:
        try:
            with urllib.request.urlopen(urllib.request.Request(CLAIMS_URL, headers={"User-Agent": "MyAlpha-Research"}), timeout=20) as r:
                raw = r.read()
            doc = json.loads(raw)
            claims = doc.get("claims") or []
            inputs["author_claims"] = {"source": "wxc-bot state/author_claims_hp.json", "sha256": sha_bytes(raw),
                                       "as_of": doc.get("generated_at"), "extractor": doc.get("extractor"), "status": "experimental_unvalidated"}
        except Exception as e:
            inputs["author_claims"] = {"source": "wxc-bot state/author_claims_hp.json", "status": f"unavailable ({type(e).__name__})"}
    return inputs, macro, claims


def macro_evidence(macro):
    out = []
    s = (macro or {}).get("series") or {}
    ry = s.get("DFII10") or {}
    if ry.get("latest"):
        ch = (ry.get("changes") or {}).get("20")
        out.append({"name": "real_yield_10y", "value": ry["latest"]["value"], "change_20": ch,
                    "source": "FRED DFII10 (point-in-time)", "as_of": ry["latest"]["date"], "realtime_start": ry["latest"].get("realtime_start")})
    y10 = s.get("DGS10") or {}
    if y10.get("latest"):
        out.append({"name": "yield_10y", "value": y10["latest"]["value"], "change_20": (y10.get("changes") or {}).get("20"),
                    "source": "FRED DGS10 (point-in-time)", "as_of": y10["latest"]["date"]})
    return out


def signed_evidence(sym, m, macro_ev, claims, vix):
    """Each item: name, value, source, as_of, sign (+1 supports upside, -1 supports downside, 0 context)."""
    ev = []
    def add(name, value, sign, source, as_of, note):
        ev.append({"name": name, "value": value, "sign": sign, "source": source, "as_of": as_of, "note": note})
    a = m["as_of"]
    add("close_vs_ma50", round(m["dist_ma50"], 4), 1 if m["close"] > m["ma50"] else -1, "stooq archive", a,
        f"close {m['close']:.2f} {'above' if m['close'] > m['ma50'] else 'below'} MA50 {m['ma50']:.2f}")
    add("close_vs_ma200", round(m["dist_ma200"], 4), 1 if m["close"] > m["ma200"] else -1, "stooq archive", a,
        f"close {'above' if m['close'] > m['ma200'] else 'below'} MA200 {m['ma200']:.2f}")
    if m.get("weekly"):
        add("weekly_trend", m["weekly"], 1 if m["weekly"] == "多头" else (-1 if m["weekly"] == "空头" else 0), "trend_pulse", m.get("trend_pulse_as_of"), f"weekly {m['weekly']}, structure {m.get('structure')}")
    if m["dist_ma200"] > RULES["stretched_ma200"]:
        add("stretched_vs_ma200", round(m["dist_ma200"], 4), -1, "stooq archive", a, f"{m['dist_ma200']:.1%} above MA200 (>{RULES['stretched_ma200']:.0%})")
    if m.get("rsi") is not None:
        r = m["rsi"]
        add("rsi14", r, -1 if r > RULES["rsi_hot"] else (1 if r < RULES["rsi_cold"] else 0), "trend_pulse", m.get("trend_pulse_as_of"), "overbought" if r > RULES["rsi_hot"] else ("oversold" if r < RULES["rsi_cold"] else "neutral range"))
    if m.get("adx") is not None and m["adx"] < RULES["adx_weak"]:
        add("trend_strength_weak", m["adx"], 0, "trend_pulse", m.get("trend_pulse_as_of"), f"ADX {m['adx']} < {RULES['adx_weak']}: trend not strong in either direction")
    if m["close"] >= m["high_60"] * (1 - RULES["near_high_pct"]):
        add("near_60d_high", m["high_60"], 0, "stooq archive", a, f"within {RULES['near_high_pct']:.0%} of 60-session high {m['high_60']:.2f}")
    for x in macro_ev:
        if x["name"] == "real_yield_10y" and x.get("change_20") is not None and sym in GROWTH:
            jump = x["change_20"] > RULES["real_yield_jump_20d"]
            add("real_yield_20d_change", round(x["change_20"], 3), -1 if jump else 0, x["source"], x["as_of"],
                f"10Y real yield {x['value']} ({x['change_20']:+.2f} in 20 obs){' — headwind for long-duration growth' if jump else ''}")
    if vix.get("value") is not None:
        add("vix", vix["value"], -1 if vix["value"] > RULES["vix_stress"] else 0, vix["source"], vix["as_of"], "stress" if vix["value"] > RULES["vix_stress"] else "calm")
    for c in claims:
        coarse = {"buy": 1, "add": 1, "bullish": 1, "hold": 0, "sell": -1, "trim": -1, "bearish": -1}.get(c["stance"], 0)
        add("author_claim", f"{c['author']}: {c['stance']}/{c['status']}", coarse * 0, "wxc-bot author_claims_hp (experimental)", c.get("published_at"),
            f"author statement ({c['hp_gate']}); not a verified trade; context only, not counted as evidence")
    return ev


def invalidation(stance, m):
    if stance == "bullish":
        return [{"metric": "close", "op": "<", "ref": "ma50", "note": "close below MA50"},
                {"metric": "close", "op": "<", "value": round(m["low_60"], 2), "note": "break of 60-session low"}]
    if stance == "bearish":
        return [{"metric": "close", "op": ">", "ref": "ma50", "note": "close back above MA50"},
                {"metric": "close", "op": ">", "value": round(m["high_60"], 2), "note": "break of 60-session high"}]
    return [{"metric": "close", "op": "<", "ref": "ma50", "note": "neutral → bearish review below MA50"},
            {"metric": "close", "op": ">", "value": round(m["high_60"], 2), "note": "neutral → bullish review above 60-session high"}]


def hint(stance):
    return {"bullish": "Watch (research: upside thesis holds; not an order)", "bearish": "Watch (research: downside risk; not an order)",
            "neutral": "Hold/Watch (research: no new thesis; not an order)", "cannot_judge": "No hint (insufficient data)"}[stance]


def analyse(sym, rows, macro_ev, claims, vix, expected):
    if rows is None or len(rows) < 200:
        return {"stance": "cannot_judge", "reason": "insufficient canonical history"}, None
    if rows[-1]["d"] != expected:
        return {"stance": "cannot_judge", "reason": f"stale bars: last {rows[-1]['d']} ≠ expected {expected}"}, None
    m = kc.trend_metrics(sym, rows)
    stance = kc.rule_view(m)
    ev = signed_evidence(sym, m, macro_ev, claims, vix)
    up = [e for e in ev if e["sign"] > 0]
    down = [e for e in ev if e["sign"] < 0]
    if stance == "bullish":
        sup, opp = up, down
    elif stance == "bearish":
        sup, opp = down, up
    else:
        sup, opp = up, down  # neutral: upside items vs downside items, both shown
    reason = (f"rule_view={stance}: close {m['close']:.2f} vs MA50 {m['ma50']:.2f} / MA200 {m['ma200']:.2f}, weekly {m.get('weekly')}, "
              f"dist MA200 {m['dist_ma200']:+.1%}, pulse {m.get('trend_pulse_state')}; +{len(up)} / -{len(down)} signed evidence")
    return {"stance": stance, "reason": reason, "metrics": m, "evidence": ev, "supporting": sup, "opposing": opp}, m


def read_journal():
    return [json.loads(x) for x in JOURNAL.read_text(encoding="utf-8").splitlines() if x.strip()] if JOURNAL.exists() else []


def latest_active(journal, sym):
    hyps = [j for j in journal if j["symbol"] == sym and j["type"] == "hypothesis"]
    if not hyps:
        return None
    h = hyps[-1]
    closed = any(j["type"] == "revisit" and j.get("hypothesis_id") == h["record_id"] and j["status"] in ("invalidated", "superseded")
                 for j in journal)
    return None if closed else h


def check_invalidation(h, rows):
    k = len(rows) - 1
    vals = {"close": rows[k]["c"], "ma50": kc.sma(rows, k, 50), "ma200": kc.sma(rows, k, 200)}
    for x in h["invalidation"]:
        ref = vals.get(x["ref"]) if x.get("ref") else x.get("value")
        cur = vals.get(x["metric"])
        if cur is None or ref is None:
            continue
        if (cur < ref) if x["op"] == "<" else (cur > ref):
            return x
    return None


def run(now=None, fetch_claims=True, run_id=None):
    now = now or datetime.now(timezone.utc)
    run_id = run_id or os.getenv("GITHUB_RUN_ID") or "local"
    expected = tc.expected_latest_completed_session(now).isoformat()
    next_open = datetime.combine(tc.next_session(date.fromisoformat(expected)), datetime.min.time().replace(hour=9, minute=30), kc_tz()).astimezone(timezone.utc)
    inputs, macro, claims = load_inputs(fetch_claims)
    macro_ev = macro_evidence(macro)
    vix = kc.market_context()
    journal = read_journal()
    keys = {(j["symbol"], j["market_as_of"], j["generator_version"], j["type"]) for j in journal}
    gen_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    new, log = [], []
    for sym in [s for s in archive_symbols() if s not in EXCLUDE]:
        rows = kc.history(sym)
        rel = [c for c in claims if c.get("symbol") == sym]
        res, m = analyse(sym, rows, macro_ev, rel, vix, expected)
        base = {"generator_version": GENERATOR, "rule_hash": RULE_HASH, "run_id": run_id, "generated_at": gen_at,
                "market_as_of": expected, "symbol": sym, "production_use": False, "shadow": True,
                "locked_before_next_open": now < next_open}
        prev = latest_active(journal + new, sym)
        if res["stance"] == "cannot_judge":
            if (sym, expected, GENERATOR, "abstain") not in keys:
                rec = {**base, "type": "abstain", "record_id": f"{sym}-{expected}-abstain", "stance": "cannot_judge",
                       "decision_reason": res["reason"], "inputs": {k: v for k, v in inputs.items() if k in ("price_archive",)}}
                new.append(rec); log.append(f"{sym}: abstain ({res['reason']})")
            continue
        if prev:  # revisit the active hypothesis on today's bar
            hit = check_invalidation(prev, rows)
            due = rows[-1]["d"] >= prev["next_review"]
            status = "invalidated" if hit else ("review_due" if due else "still_valid")
            if res["stance"] != prev["stance"] and status == "still_valid":
                status = "superseded"
            if (sym, expected, GENERATOR, "revisit") not in keys and prev["market_as_of"] != expected:
                new.append({**base, "type": "revisit", "record_id": f"{sym}-{expected}-revisit", "hypothesis_id": prev["record_id"],
                            "status": status, "trigger": hit, "close": rows[-1]["c"], "decision_reason": res["reason"]})
                log.append(f"{sym}: revisit {prev['record_id']} → {status}")
            if status == "still_valid" or status == "review_due" and res["stance"] == prev["stance"]:
                continue
        if (sym, expected, GENERATOR, "hypothesis") in keys:
            continue
        rel_claims = [{"record_id": c["record_id"], "author": c["author"], "stance": c["stance"], "status": c["status"],
                       "hp_gate": c["hp_gate"], "published_at": c.get("published_at"), "first_seen": c.get("first_seen"),
                       "provenance": c.get("provenance"), "sentence_sha256": c["sentence_sha256"],
                       "check": "compatibility only; author statement is not a verified trade"} for c in rel]
        rec = {**base, "type": "hypothesis", "record_id": f"{sym}-{expected}-h", "stance": res["stance"],
               "decision_reason": res["reason"], "research_hint": hint(res["stance"]),
               "metrics": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()},
               "supporting": res["supporting"], "opposing": res["opposing"], "author_claims": rel_claims,
               "invalidation": invalidation(res["stance"], m), "horizon_sessions": HORIZON,
               "next_review": tc.add_sessions(date.fromisoformat(expected), HORIZON).isoformat(),
               "risks": ["rule-based trend view only; fundamentals not extracted (SEC facts unavailable)",
                         "author claims are experimental (ce-5) and not evidence of trades"],
               "unknowns": ["SEC financial facts not extracted", "valuation not in free pipeline"] +
                           ([] if inputs["fred_macro"].get("sha256") else ["FRED macro unavailable"]) +
                           ([] if inputs.get("author_claims", {}).get("sha256") else ["author claims unavailable"]),
               "supersedes": prev["record_id"] if prev else None, "inputs": inputs,
               "outcome": {"status": "pending", "matures": tc.add_sessions(date.fromisoformat(expected), HORIZON).isoformat()}}
        rec["record_sha256"] = sha_bytes(json.dumps(rec, ensure_ascii=False, sort_keys=True).encode())
        new.append(rec); log.append(f"{sym}: hypothesis {res['stance']}")
    if new:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL.open("a", encoding="utf-8") as fh:
            for r in new:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    allj = journal + new
    week = [j for j in allj if j["market_as_of"] >= tc.add_sessions(date.fromisoformat(expected), -4).isoformat()]
    st = {"generator_version": GENERATOR, "rule_hash": RULE_HASH, "last_run_id": run_id, "last_run_at": gen_at,
          "market_as_of": expected, "appended_this_run": len(new), "journal_records": len(allj),
          "active_hypotheses": sum(1 for s in {j["symbol"] for j in allj} if latest_active(allj, s)),
          "stances_active": {s: latest_active(allj, s)["stance"] for s in sorted({j["symbol"] for j in allj}) if latest_active(allj, s)},
          "last_5_sessions": {"hypotheses": sum(1 for j in week if j["type"] == "hypothesis"),
                              "invalidated": sum(1 for j in week if j["type"] == "revisit" and j["status"] == "invalidated"),
                              "superseded": sum(1 for j in week if j["type"] == "revisit" and j["status"] == "superseded"),
                              "abstained": sum(1 for j in week if j["type"] == "abstain")},
          "inputs": {k: {kk: vv for kk, vv in v.items() if kk != "sha256"} for k, v in inputs.items()},
          "outcomes": "pending (first 20-session maturity after the first hypothesis session)",
          "learning_state": "UNPROVEN", "production_use": False, "log": log[:60]}
    STATUS.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return st, new


def kc_tz():
    from zoneinfo import ZoneInfo
    return ZoneInfo("America/New_York")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-claims", action="store_true")
    a = ap.parse_args(argv)
    st, new = run(fetch_claims=not a.no_claims)
    print(f"::notice title=Auto research::AUTO_RESEARCH market_as_of={st['market_as_of']} appended={st['appended_this_run']} "
          f"active={st['active_hypotheses']} run={st['last_run_id']}")
    for line in st["log"][:40]:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
