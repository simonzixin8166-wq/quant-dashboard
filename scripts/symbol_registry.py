#!/usr/bin/env python3
"""Symbol registry — three separate universes + Missing Historical Symbols (#133 6117657723; tasks D-04, D-07).

Read-only generator (no network; writes research/audit/symbol_registry.json only). It does NOT change collection yet:
the daily collector is wired to this registry only after the first scheduled research run (task D-05).

  display_watchlist        what the website shows: docs/data.json stocks (owner's Supabase watchlist) + core + index.
                           Hiding a symbol here must never stop collection or delete history.
  research_universe        securities actually used by research/learning code, each with used_by:
                           auto_research (price archive), sec_facts, sec_memory, event_evidence / event archive,
                           options_context, support_volatility, fundamental_outcomes, source_mentions.
  data_collection_universe research_universe ∪ benchmarks ∪ display (securities only) ∪ owner-requested (AAPL, AMZN, AAOI + owner pack) — what the backend must keep
                           updated with finalized daily OHLCV, independent of the display list.
Per symbol: asset_type, identity (SEC ticker map entity when available; unverified otherwise — never guessed),
in_archive, archive_last_date, refresh_status (fresh / stale / missing vs the expected NYSE session),
quality flags (synthetic flat bars in the last 30 rows), pending import (validated owner pack), display flag.
Missing Historical Symbols: securities in the research or collection universe without archive history, counted as
DISTINCT SECURITIES (event rows are reported as a separate number, never as symbol counts).
"""
from __future__ import annotations
import csv, io, json, sys, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

RES = ROOT / "docs" / "research"
ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
OUT = ROOT / "research" / "audit" / "symbol_registry.json"
BENCHMARKS = {"SPY", "QQQ", "VOO", "DIA", "IWM", "TLT", "HYG", "GLD", "XLK", "XLF", "XLE"}
ETF = BENCHMARKS | {"QQQM", "QLD", "TQQQ", "VGT", "SMH", "DRAM"}  # DRAM: ETF (owner-confirmed 10/26)
NON_SECURITY = {"BTC/USD": "crypto", "GCMAIN": "future", "VIX": "index"}
OWNER_REQUESTED = {"AAPL", "AMZN", "AAOI"}  # #133 6117657723 priority list; plus every symbol in the validated owner pack
UNVERIFIED_IDENTITY = {"DRAM"}  # not in the SEC ticker map; never guess what instrument a code denotes


# Share-class aliases folded into one research symbol (owner decision 2026-10-13, #133): GOOGL → GOOG.
CANONICAL_SYMBOL = {"GOOGL": "GOOG"}


def load(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {} if d is None else d


def archive_state():
    out = {}
    if not ARCHIVE.exists():
        return out
    with zipfile.ZipFile(ARCHIVE) as z:
        for n in z.namelist():
            if not n.endswith("_us_d.csv"):
                continue
            rows = [r for r in csv.reader(io.StringIO(z.read(n).decode()))][1:]
            rows = [r for r in rows if r]
            flat = sum(1 for r in rows[-30:] if r[1] == r[2] == r[3] == r[4])
            out[n.split("_")[0].upper()] = {"last_date": rows[-1][0] if rows else None, "rows": len(rows), "flat_bars_last30": flat}
    return out


def build(now=None):
    now = now or datetime.now(timezone.utc)
    expected = tc.expected_latest_completed_session(now).isoformat()
    data = load(ROOT / "docs" / "data.json")
    arch = archive_state()
    used = defaultdict(set)
    display = {}
    for sec in ("stocks", "core", "index"):
        for s in (data.get(sec) or {}):
            display.setdefault(s, set()).add(sec)
    for s in arch:
        used[s].add("auto_research_price_archive" if s != "VIX" else "market_context")
    for s in (load(RES / "sec_fundamentals.json").get("symbols") or {}):
        used[s].add("sec_facts")
    for s in (load(RES / "company_fundamental_memory.json").get("symbols") or {}):
        used[s].add("sec_memory")
    for s in (load(RES / "event_evidence.json").get("symbols") or {}):
        used[s].add("event_evidence")
    ev_rows = Counter()
    for p in sorted((ROOT / "research" / "archive" / "events").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                s = json.loads(line).get("symbol")
                if s:
                    ev_rows[s] += 1
                    used[s].add("event_archive")
    for s in (load(RES / "options_opportunity_context.json").get("universe") or []):
        used[str(s.get("symbol") if isinstance(s, dict) else s)].add("options_context")
    for s in (load(RES / "support_volatility_intelligence.json").get("universe") or []):
        used[str(s.get("symbol") if isinstance(s, dict) else s)].add("support_volatility")
    fo = Counter()
    p = ROOT / "research" / "archive" / "fundamental_observations.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                s = json.loads(line).get("symbol"); fo[s] += 1; used[s].add("fundamental_outcomes")
    mentions = Counter()
    for r in (load(ROOT / "docs" / "data" / "source_intelligence.json").get("records") or []):
        for s in r.get("symbols") or []:
            mentions[CANONICAL_SYMBOL.get(s, s)] += 1  # historical records may still say GOOGL
    sec_entities = {k: v.get("entity") for k, v in (load(RES / "sec_fundamentals.json").get("symbols") or {}).items() if v.get("entity")}
    pack = load(ROOT / "research" / "audit" / "stooq_pack_validation.json")
    pack_verdict = {s: x.get("verdict") for s, x in (pack.get("symbols") or {}).items()}

    research = {s for s in used if s and "/" not in s and s not in NON_SECURITY}
    owner = OWNER_REQUESTED | set(pack_verdict)
    for s in owner:
        used[s].add("owner_requested")
    display_sec = {s for s in display if s not in NON_SECURITY}
    collection = research | BENCHMARKS | display_sec | owner
    rows = {}
    for s in sorted(collection | set(display) | set(NON_SECURITY) & set(arch)):
        a = arch.get(s)
        last = a["last_date"] if a else None
        refresh = "missing" if not a else ("fresh" if last and last >= expected else "stale")
        flags = []
        if a and a["flat_bars_last30"]:
            flags.append(f"synthetic_flat_bars_last30={a['flat_bars_last30']}")
        identity = ("unverified" if s in UNVERIFIED_IDENTITY else
                    f"sec_ticker_map:{sec_entities[s]}" if s in sec_entities else
                    "etf_or_benchmark" if s in ETF else "listed_ticker_unchecked")
        rows[s] = {"asset_type": NON_SECURITY.get(s) or ("etf" if s in ETF else "equity"),
                   "identity": identity, "display": sorted(display.get(s, [])), "in_research_universe": s in research,
                   "in_data_collection_universe": s in collection, "used_by": sorted(used.get(s, [])),
                   "in_archive": bool(a), "archive_last_date": last, "refresh_status": refresh,
                   "quality_flags": flags, "pending_owner_pack": pack_verdict.get(s) if not a or s in ("TQQQ", "LITE") else None,
                   "event_rows": ev_rows.get(s, 0), "fundamental_observations": fo.get(s, 0), "source_mentions": mentions.get(s, 0)}
    missing = []
    for s, r in rows.items():
        if r["in_data_collection_universe"] and not r["in_archive"] and r["asset_type"] in ("equity", "etf"):
            prio = (0 if r["identity"] == "unverified" else 1) , r["event_rows"] + r["fundamental_observations"] + r["source_mentions"]
            missing.append({"symbol": s, "use_cases": r["used_by"] or ["benchmark"], "owner_requested": "owner_requested" in r["used_by"], "event_rows": r["event_rows"],
                            "fundamental_observations": r["fundamental_observations"], "source_mentions": r["source_mentions"],
                            "display": r["display"], "identity": r["identity"],
                            "free_source": "owner-supplied STOOQ pack (validated, staged)" if r["pending_owner_pack"] else
                                           ("docs/data.json stocks (daily bar only, no history)" if "stocks" in r["display"] else "none known yet"),
                            "pending_owner_pack": r["pending_owner_pack"],
                            "priority": "high" if prio[1] >= 50 or s in BENCHMARKS or s in OWNER_REQUESTED else "medium" if prio[1] >= 10 else "low"})
    missing.sort(key=lambda x: (-(x["event_rows"] + x["fundamental_observations"] + x["source_mentions"]), x["symbol"]))
    ev_missing_rows = sum(r["event_rows"] for r in rows.values() if not r["in_archive"])
    return {
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"), "expected_session": expected,
        "counts": {"display_watchlist": len(display), "research_universe": len(research), "data_collection_universe": len(collection),
                   "in_archive": sum(1 for s in collection if s in arch),
                   "refresh": dict(Counter(rows[s]["refresh_status"] for s in collection)),
                   "missing_history_securities": len(missing),
                   "missing_history_covered_by_owner_pack": sum(1 for m in missing if m["pending_owner_pack"]),
                   "event_rows_without_history": ev_missing_rows},
        "note": "event_rows_without_history counts news/event rows, not securities; missing_history_securities counts distinct securities",
        "universes": {"display_watchlist": sorted(display), "research_universe": sorted(research), "data_collection_universe": sorted(collection)},
        "symbols": rows, "missing_historical_symbols": missing,
        "collection_rule": "data_collection_universe is updated daily with finalized OHLCV regardless of display; a missing bar is recorded missing/stale, never synthesized (D-05/D-06, wired after P0-05)",
        "read_only": True,
    }


def main():
    rep = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = rep["counts"]
    print(f"::notice title=Symbol registry::display={c['display_watchlist']} research={c['research_universe']} collection={c['data_collection_universe']} "
          f"in_archive={c['in_archive']} missing_securities={c['missing_history_securities']} (owner pack covers {c['missing_history_covered_by_owner_pack']}) "
          f"refresh={c['refresh']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
