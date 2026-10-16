#!/usr/bin/env python3
"""OFI-A1 — daily closing option-chain + open-interest snapshot archive (stage A, owner-approved, #133).

Scope (owner decision 2026-10-13):
  universe  = underlyings of the owner's real stock/option positions (read at runtime from Supabase)
              ∪ the 6 options-context symbols (QQQ SOFI LITE IREN NVDA TSLA, or MAV_OPTION_UNIVERSE)
  window    = expirations up to +60 calendar days, strikes within ±20 % of the latest local close
  storage   = the PRIVATE ledger repo only (stream `option_chain_snapshots`); the public repo gets an
              aggregate status file with no symbols, no positions and no accounts.

What this is NOT: no anomaly scores, no signals, no homepage output, no orders. Data are Alpaca free
Basic `feed=indicative` (adjusted quotes, delayed trades) plus the contracts endpoint's open interest,
which is usually the PRIOR session's figure (`open_interest_date` is stored with every row). Every row
carries used_in_decision=false. Missing data are recorded as null / unavailable, never filled.

Request budget per run: per underlying 1 oi_window call + 1 chain_window call (+ pagination pages),
plus 2 Supabase reads (positions). Calls are reported in the public status file.
"""
from __future__ import annotations
import hashlib, io, json, os, sys, urllib.parse, urllib.request, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

VERSION = "ofi-a1-v1"
STREAM = "option_chain_snapshots"
CONTEXT_UNIVERSE = ["QQQ", "SOFI", "LITE", "IREN", "NVDA", "TSLA"]  # == options_opportunity_context.UNIVERSE
CANONICAL_SYMBOL = {"GOOGL": "GOOG"}
MAX_UNDERLYINGS = 15
DTE_MAX_DAYS = 60
STRIKE_BAND = 0.20
DEFAULT_EDGE = "https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/options-market"
STATUS_OUT = ROOT / "docs" / "research" / "option_snapshot_status.json"
DATA = ROOT / "docs" / "data.json"
HISTORY_ZIP = ROOT / "data" / "history" / "stooq_watchlist.zip"
# Post-close run window (UTC): the 21:30Z Daily qualifies, the 08:15Z morning run does not, so the same
# session is never fetched twice. OFI_SNAPSHOT_FORCE=1 overrides for a manual dispatch.
RUN_WINDOW_UTC = (20, 24)
NON_OPTIONABLE = {"BTC/USD", "GCMAIN", "VIX"}


def canonical(sym):
    s = str(sym or "").upper().strip().lstrip("$")
    return CANONICAL_SYMBOL.get(s, s)


def build_universe(context, held, cap=MAX_UNDERLYINGS):
    """Union of context symbols and held underlyings, canonical, de-duplicated, capped.
    Held symbols come first so a cap never drops a real position in favour of a context symbol."""
    out = []
    for s in list(held or []) + list(context or []):
        c = canonical(s)
        if c and c not in NON_OPTIONABLE and c not in out and all(ch.isalnum() or ch in ".-" for ch in c):
            out.append(c)
    dropped = out[cap:]
    return out[:cap], dropped


def window(ref_price, today, dte_max=DTE_MAX_DAYS, band=STRIKE_BAND):
    exp_lte = (today + timedelta(days=dte_max)).isoformat()
    if ref_price is None or ref_price <= 0:
        return {"expiration_lte": exp_lte, "strike_gte": None, "strike_lte": None}
    return {"expiration_lte": exp_lte, "strike_gte": round(ref_price * (1 - band), 2),
            "strike_lte": round(ref_price * (1 + band), 2)}


def should_run(now, force=False):
    if force:
        return True, "forced"
    if not tc.is_session(now.date()):
        return False, "not_a_session_day"
    if not (RUN_WINDOW_UTC[0] <= now.hour < RUN_WINDOW_UTC[1]):
        return False, "outside_post_close_window"
    return True, "post_close_window"


def _columns(payload, keys):
    cols = {k: payload.get(k) or [] for k in keys}
    n = max((len(v) for v in cols.values()), default=0)
    return [{k: (cols[k][i] if i < len(cols[k]) else None) for k in keys} for i in range(n)]


def merge(oi_payload, chain_payload):
    """Join contracts (OI) and snapshots (quotes/IV/greeks/volume) on OCC symbol. Nothing is inferred:
    a contract present on one side only keeps nulls for the other side's fields."""
    oi_rows = {r["optionSymbol"]: r for r in _columns(oi_payload or {}, ["optionSymbol", "expiration", "strike", "side", "multiplier",
                                                                       "openInterest", "openInterestDate", "closePrice", "closePriceDate"]) if r["optionSymbol"]}
    ch_rows = {r["optionSymbol"]: r for r in _columns(chain_payload or {}, ["optionSymbol", "expiration", "strike", "side", "bid", "ask", "last",
                                                                          "iv", "delta", "gamma", "theta", "vega", "volume", "updated"]) if r["optionSymbol"]}
    rows = []
    for occ in sorted(set(oi_rows) | set(ch_rows)):
        a, b = oi_rows.get(occ, {}), ch_rows.get(occ, {})
        rows.append([occ, a.get("expiration") or b.get("expiration"), a.get("strike") if a.get("strike") is not None else b.get("strike"),
                     (a.get("side") or b.get("side") or "")[:1].upper() or None, a.get("multiplier"),
                     a.get("openInterest"), a.get("openInterestDate"), a.get("closePrice"), a.get("closePriceDate"),
                     b.get("bid"), b.get("ask"), b.get("last"), b.get("volume"), b.get("iv"), b.get("delta"), b.get("updated")])
    return rows


ROW_FIELDS = ["occ", "expiration", "strike", "side", "multiplier", "open_interest", "open_interest_date", "close_price",
              "close_price_date", "bid", "ask", "last", "volume_day", "iv", "delta", "quote_updated_epoch"]


def quality(rows, market_date):
    n = len(rows)
    oi_known = [r for r in rows if r[5] is not None]
    oi_dates = sorted({r[6] for r in oi_known if r[6]})
    quoted = [r for r in rows if r[9] is not None and r[10] is not None]
    return {"contracts": n, "oi_coverage": round(len(oi_known) / n, 4) if n else None, "oi_dates": oi_dates,
            "oi_is_prior_session_or_older": bool(oi_dates) and max(oi_dates) < market_date,
            "quote_coverage": round(len(quoted) / n, 4) if n else None,
            "volume_known": sum(1 for r in rows if r[12] is not None)}


def make_record(symbol, market_date, captured_at, win, ref, rows, calls, truncated, error=None):
    rec = {"record_id": f"ocs:{market_date}:{symbol}", "schema": VERSION, "symbol": symbol, "market_date": market_date,
           "captured_at": captured_at, "provider": "Alpaca", "feed": "indicative", "delayed": True,
           "oi_source": "alpaca_trading_v2_options_contracts (open_interest_date stored per row)",
           "reference_close": ref, "window": win, "row_fields": ROW_FIELDS, "rows": rows,
           "quality": quality(rows, market_date), "truncated": bool(truncated), "api_calls": calls,
           "status": "error" if error else ("ok" if rows else "empty"), "error": error,
           "used_in_decision": False, "production_use": False, "signal": None}
    rec["rows_sha256"] = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
    return rec


# ---------------------------------------------------------------- I/O (injectable for tests)
def _http_json(url, headers, timeout=25):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def edge_call(action, symbol, win, http=_http_json):
    key = os.getenv("SUPABASE_KEY") or ""
    endpoint = os.getenv("OPTIONS_MARKET_ENDPOINT") or DEFAULT_EDGE
    params = {"action": action, "symbol": symbol, "expiration_lte": win["expiration_lte"]}
    if win.get("strike_gte") is not None:
        params["strike_gte"] = f"{win['strike_gte']:.2f}"
        params["strike_lte"] = f"{win['strike_lte']:.2f}"
    headers = {"User-Agent": "MyAlpha-OFI-A1"}
    if key:
        headers.update({"apikey": key, "Authorization": f"Bearer {key}"})
    return http(endpoint + "?" + urllib.parse.urlencode(params), headers)


def held_underlyings(http=_http_json):
    """Distinct underlyings of open stock/option positions. Returns (symbols, reads, error). Never logged."""
    base, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not base or not key:
        return [], 0, "supabase_unconfigured"
    out, reads, errs = [], 0, []
    h = {"apikey": key, "Authorization": f"Bearer {key}", "User-Agent": "MyAlpha-OFI-A1"}
    for table in ("options_positions", "stock_positions"):
        try:
            reads += 1
            rows = http(f"{base.rstrip('/')}/rest/v1/{table}?select=*", h) or []
        except Exception as e:  # table missing / RLS → skip that table, record why (no row data)
            errs.append(f"{table}:{type(e).__name__}")
            continue
        for r in rows:
            st = str(r.get("status") or "open").lower()
            if st in ("closed", "expired", "assigned", "rolled", "deleted"):
                continue
            s = canonical(r.get("symbol") or r.get("underlying") or "")
            if s and s not in out:
                out.append(s)
    return out, reads, (";".join(errs) or None)


def reference_closes(symbols):
    ref = {}
    try:
        d = json.loads(DATA.read_text(encoding="utf-8"))
        for group in ("stocks", "core", "index"):
            for s, v in (d.get(group) or {}).items():
                if isinstance(v, dict) and v.get("close") and canonical(s) not in ref:
                    ref[canonical(s)] = (float(v["close"]), v.get("date"))
    except Exception:
        pass
    missing = [s for s in symbols if s not in ref]
    if missing and HISTORY_ZIP.exists():
        try:
            with zipfile.ZipFile(HISTORY_ZIP) as z:
                names = {Path(n).stem.upper(): n for n in z.namelist()}
                for s in missing:
                    n = names.get(s)
                    if not n:
                        continue
                    lines = [x for x in io.TextIOWrapper(z.open(n), encoding="utf-8").read().splitlines() if x.strip()]
                    last = lines[-1].split(",")
                    ref[s] = (float(last[4]), last[0])
        except Exception:
            pass
    return ref


def run(now=None, http=_http_json, ledger=None, force=False):
    now = now or datetime.now(timezone.utc)
    go, why = should_run(now, force)
    market_date = tc.expected_latest_completed_session(now).isoformat()
    status = {"version": VERSION, "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
              "market_date": market_date, "run_reason": why, "storage": "private_ledger", "public_fields": "aggregate only",
              "provider": "Alpaca free Basic, feed=indicative (delayed/adjusted); OI from contracts endpoint (usually prior session)",
              "used_in_decision": False, "production_use": False, "signals": None}
    if not go:
        status.update(status_code="skipped")
        return status, []
    if ledger is None:
        status.update(status_code="unavailable", reason="private_ledger_unconfigured")
        return status, []
    held, reads, held_err = held_underlyings(http)
    env_ctx = [x for x in (os.getenv("MAV_OPTION_UNIVERSE") or "").replace(";", ",").split(",") if x.strip()]
    universe, dropped = build_universe(env_ctx or CONTEXT_UNIVERSE, held)
    refs = reference_closes(universe)
    today = now.date()
    captured = status["generated_at"]
    records, calls = [], 0
    for sym in universe:
        ref = refs.get(sym)
        win = window(ref[0] if ref else None, today)
        c = 0
        try:
            c += 1
            oi = edge_call("oi_window", sym, win, http)
            c += 1
            ch = edge_call("chain_window", sym, win, http)
            rows = merge(oi, ch)
            rec = make_record(sym, market_date, captured, win, {"close": ref[0], "date": ref[1]} if ref else None, rows,
                              c + int(oi.get("pages") or 1) - 1 + int(ch.get("pages") or 1) - 1,
                              bool(oi.get("truncated")) or bool(ch.get("truncated")))
        except Exception as e:
            rec = make_record(sym, market_date, captured, win, None, [], c, False, error=type(e).__name__)
        calls += rec["api_calls"]
        records.append(rec)
    ok = [r for r in records if r["status"] == "ok"]
    contracts = sum(r["quality"]["contracts"] for r in ok)
    oi_known = sum(round((r["quality"]["oi_coverage"] or 0) * r["quality"]["contracts"]) for r in ok)
    status.update(
        status_code="ok" if ok and len(ok) == len(records) else ("partial" if ok else "unavailable"),
        underlyings_ok=len(ok), underlyings_failed=len(records) - len(ok), capped=len(dropped),
        contracts_archived=contracts, oi_coverage=round(oi_known / contracts, 4) if contracts else None,
        edge_calls=calls, supabase_reads=reads, positions_read_error=held_err)
    try:
        res = ledger.append_many(STREAM, records, market_date)
        status.update(ledger={"appended": res.added_count, "record_count": res.record_count, "head_hash": res.head_hash})
    except Exception as e:
        status.update(status_code="unavailable", reason=f"ledger_write_failed:{type(e).__name__}")
    return status, records


def main():
    force = os.getenv("OFI_SNAPSHOT_FORCE", "").strip() in ("1", "true", "yes")
    try:
        from private_ledger import PrivateGitHubLedger
        ledger = PrivateGitHubLedger.from_env()
    except Exception:
        ledger = None
    status, _ = run(ledger=ledger, force=force)
    STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=OFI-A1 option snapshot::status={status.get('status_code')} market_date={status['market_date']} "
          f"contracts={status.get('contracts_archived')} oi_coverage={status.get('oi_coverage')} calls={status.get('edge_calls')}")
    return 1 if status.get("status_code") == "unavailable" else 0


if __name__ == "__main__":
    sys.exit(main())
