#!/usr/bin/env python3
"""Validate an owner-supplied STOOQ daily pack BEFORE any import (#133 6117622847 / 6117657723, task D-07).

Read-only: never writes to data/history/. Usage:
  python -I scripts/stooq_pack_validate.py <pack.zip> [--out research/audit/stooq_pack_validation.json]
Checks: manifest sha256/rows/range; per file header, duplicates, ordering, OHLC logic, non-positive prices,
non-session dates, missing sessions (known exchange closures absent from trading_calendar listed separately),
one-day moves > 40 % (possible unadjusted split); overlap with the canonical archive: per-date close difference,
and every archive bar with open == high == low == close (synthetic flat bar candidates) compared with the pack.
Verdict per symbol: new | overlap_identical | overlap_consistent | overlap_conflict | invalid.
The report contains statistics only (no price series) so it is safe to commit.
"""
from __future__ import annotations
import csv, hashlib, io, json, sys, zipfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import trading_calendar as tc  # noqa: E402

ARCHIVE = ROOT / "data" / "history" / "stooq_watchlist.zip"
KNOWN_CLOSURES = {"1994-04-27": "Nixon state funeral", "2001-09-11": "September 11 closure", "2001-09-12": "September 11 closure",
                  "2001-09-13": "September 11 closure", "2001-09-14": "September 11 closure", "2004-06-11": "Reagan state funeral",
                  "2007-01-02": "Ford state funeral", "2012-10-29": "Hurricane Sandy", "2012-10-30": "Hurricane Sandy",
                  "2018-12-05": "G.H.W. Bush state funeral", "2025-01-09": "Carter state funeral"}  # absent from trading_calendar
HEADER = ["Date", "Open", "High", "Low", "Close", "Volume"]
TOL_IDENTICAL, TOL_CONSISTENT = 1e-6, 0.005  # relative close difference


def parse(text):
    rows = list(csv.reader(io.StringIO(text)))
    return rows[0], [r for r in rows[1:] if r]


def check_file(name, text):
    header, rows = parse(text)
    out = {"file": name, "header_ok": header == HEADER, "rows": len(rows)}
    if not out["header_ok"] or not rows:
        out["verdict"] = "invalid"; return out, {}
    ds = [r[0] for r in rows]
    bars = {}
    viol, nonpos, flat = [], 0, 0
    for r in rows:
        o, h, l, c = (float(x) for x in r[1:5])
        if min(o, h, l, c) <= 0:
            nonpos += 1
        if not (l <= min(o, c) <= max(o, c) <= h):
            viol.append(r[0])
        if o == h == l == c:
            flat += 1
        bars[r[0]] = (o, h, l, c, float(r[5] or 0))
    d0, d1 = date.fromisoformat(ds[0]), date.fromisoformat(ds[-1])
    sess = {str(d0)} | {str(d) for d in tc.sessions_between(d0, d1)}
    missing = sorted(sess - set(ds))
    jumps = [(ds[i], round(bars[ds[i]][3] / bars[ds[i - 1]][3] - 1, 4)) for i in range(1, len(ds))
             if bars[ds[i - 1]][3] > 0 and abs(bars[ds[i]][3] / bars[ds[i - 1]][3] - 1) > 0.40]
    out.update({"first": ds[0], "last": ds[-1], "duplicates": len(ds) - len(set(ds)), "sorted": ds == sorted(ds),
                "ohlc_violations": len(viol), "ohlc_violation_dates": viol[:10], "non_positive": nonpos,
                "flat_bars_in_pack": flat, "non_session_dates": sorted(set(ds) - sess)[:10],
                "missing_sessions": len(missing),
                "missing_known_closures": [m for m in missing if m in KNOWN_CLOSURES],
                "missing_unexplained": [m for m in missing if m not in KNOWN_CLOSURES][:20],
                "moves_over_40pct": jumps[:10]})
    return out, bars


def archive_bars():
    out = {}
    if not ARCHIVE.exists():
        return out
    with zipfile.ZipFile(ARCHIVE) as z:
        for n in z.namelist():
            if n.endswith("_us_d.csv"):
                _, rows = parse(z.read(n).decode())
                out[n.split("_")[0].upper()] = {r[0]: tuple(float(x) for x in r[1:5]) for r in rows if r}
    return out


def overlap(sym, bars, arch):
    a = arch.get(sym)
    if not a:
        return {"overlap": "new"}
    common = sorted(set(a) & set(bars))
    diffs = [abs(bars[d][3] / a[d][3] - 1) for d in common if a[d][3] > 0]
    flats = [d for d, v in a.items() if v[0] == v[1] == v[2] == v[3]]
    flat_cmp = []
    for d in sorted(flats)[-30:]:
        p = bars.get(d)
        flat_cmp.append({"date": d, "archive_close": a[d][3], "pack": None if p is None else
                         {"open": p[0], "high": p[1], "low": p[2], "close": p[3], "flat_in_pack": p[0] == p[1] == p[2] == p[3]}})
    mx = max(diffs) if diffs else None
    verdict = ("overlap_identical" if mx is not None and mx <= TOL_IDENTICAL else
               "overlap_consistent" if mx is not None and mx <= TOL_CONSISTENT else "overlap_conflict")
    big = sorted(((round(abs(bars[d][3] / a[d][3] - 1), 4), d) for d in common if a[d][3] > 0), reverse=True)[:5]
    return {"overlap": verdict, "common_dates": len(common), "archive_range": [min(a), max(a)],
            "max_rel_close_diff": mx, "largest_diffs": [{"date": d, "rel_diff": x} for x, d in big],
            "archive_flat_bars": len(flats), "archive_flat_bars_recent_vs_pack": flat_cmp,
            "pack_extends_archive_to": max(bars) if bars and max(bars) > max(a) else None}


def validate(pack_path):
    raw = Path(pack_path).read_bytes()
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    if any("/" in n or ".." in n for n in names):
        raise SystemExit("unsafe member path in pack")
    manifest = json.loads(z.read("import_manifest.json")) if "import_manifest.json" in names else {}
    mfiles = {f.get("filename"): f for f in manifest.get("files", [])}
    arch = archive_bars()
    report = {"pack_sha256": hashlib.sha256(raw).hexdigest(), "pack_name": Path(pack_path).name,
              "validated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
              "manifest_note": manifest.get("note"), "symbols": {}}
    for n in sorted(x for x in names if x.endswith("_us_d.csv")):
        data = z.read(n)
        info, bars = check_file(n, data.decode())
        m = mfiles.get(n, {})
        info["manifest"] = {"sha256_match": m.get("sha256") == hashlib.sha256(data).hexdigest(),
                            "rows_match": m.get("rows") == info.get("rows"),
                            "range_match": (m.get("start"), m.get("end")) == (info.get("first"), info.get("last"))}
        sym = n.split("_")[0].upper()
        info.update(overlap(sym, bars, arch) if bars else {"overlap": "invalid"})
        bad = (info.get("verdict") == "invalid" or info["duplicates"] or info["ohlc_violations"] or info["non_positive"]
               or info["non_session_dates"] or not all(info["manifest"].values()) or info["moves_over_40pct"])
        info["verdict"] = "invalid_or_review" if bad else info["overlap"]
        report["symbols"][sym] = info
    v = [s["verdict"] for s in report["symbols"].values()]
    report["summary"] = {k: v.count(k) for k in sorted(set(v))}
    report["import_plan"] = {"append_new": sorted(s for s, x in report["symbols"].items() if x["verdict"] == "new"),
                             "existing_identical_or_consistent": sorted(s for s, x in report["symbols"].items() if x["verdict"] in ("overlap_identical", "overlap_consistent")),
                             "quarantine_or_review": sorted(s for s, x in report["symbols"].items() if x["verdict"] in ("overlap_conflict", "invalid_or_review"))}
    return report


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else ROOT / "research" / "audit" / "stooq_pack_validation.json"
    rep = validate(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"summary": rep["summary"], "import_plan": rep["import_plan"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
