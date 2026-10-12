#!/usr/bin/env python3
"""Import a validated owner STOOQ pack into the canonical archive (#133 6117622847; task D-03).

DRY RUN by default; writes only with --apply. Run ONLY after P0-05 (first scheduled research run) is reported.
  python -I scripts/stooq_pack_import.py <pack.zip> [--apply] [--archive data/history/stooq_watchlist.zip]
Rules (from research/audit/stooq_pack_validation.json and docs/development/master_plan.json D-03):
  - pack sha256 must equal EXPECTED_SHA256 and every manifest sha256 must match;
  - new symbols are appended with their original bytes; existing members keep identical bytes, except:
  - REPAIR_FLAT: only archive bars with open == high == low == close (synthetic) whose close equals the pack close
    are replaced with the pack's OHLCV (TQQQ: 2026-10-05..09);
  - REPAIR_CONFLICT: dates whose archive close differs from the pack by > 0.5 % are replaced, and pack dates missing
    inside the archive's range are inserted (LITE: 2026-09-29/30 replaced, 2026-10-01 inserted);
  - every replacement/insertion is appended to data/history/corrections.jsonl (old, new, source sha256, reason);
  - provenance for the pack is written to data/history/pack_provenance_<pack>.json;
  - symbols already identical (SPY) are skipped; re-running is a no-op (idempotent).
Never touches any other member's history; adjustment-basis differences (TQQQ pack history) are NOT imported.
"""
from __future__ import annotations
import csv, hashlib, io, json, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA256 = "ead9bb5ff738733424ef52ce9cdf0a8d5f7395122fb660dfe760564cf14316e2"
APPEND = ["AMZN", "META", "NOW", "DIA", "GLD", "HYG", "IWM", "TLT", "XLE", "XLF", "XLK", "AAOI", "AAPL", "CRWV", "MU", "INTC"]
QUALITY_FLAGS = {"AAOI": ["one_day_moves_over_40pct_real"], "AAPL": ["one_day_move_2000_09_29_real", "early_flat_bars"],
                 "CRWV": ["one_day_move_2025_04_01_real"], "INTC": ["pre_1990_close_only_flat_bars", "early_gaps"],
                 "MU": ["early_gaps"], "AMZN": ["early_gaps"]}
REPAIR_FLAT = ["TQQQ"]
REPAIR_CONFLICT = ["LITE"]
SKIP_IDENTICAL = ["SPY"]


def rows_of(text):
    lines = text.splitlines()
    return lines[0], {r[0]: r for r in csv.reader(io.StringIO("\n".join(lines[1:]))) if r}


def to_text(header, rows):
    return header + "\n" + "\n".join(",".join(rows[d]) for d in sorted(rows)) + "\n"


def plan(pack_bytes, archive_path):
    if hashlib.sha256(pack_bytes).hexdigest() != EXPECTED_SHA256:
        raise SystemExit("pack sha256 mismatch — refuse")
    pz = zipfile.ZipFile(io.BytesIO(pack_bytes))
    man = {f["filename"]: f for f in json.loads(pz.read("import_manifest.json")).get("files", [])}
    for n, f in man.items():
        if hashlib.sha256(pz.read(n)).hexdigest() != f["sha256"]:
            raise SystemExit(f"manifest sha256 mismatch for {n} — refuse")
    az = zipfile.ZipFile(archive_path)
    members = {n: az.read(n) for n in az.namelist()}
    new_members, corrections, skipped = {}, [], []
    for s in APPEND:
        n = f"{s.lower()}_us_d.csv"
        if n in members:
            skipped.append({"symbol": s, "reason": "already in archive"})
            continue
        new_members[n] = pz.read(n)
    for s in REPAIR_FLAT + REPAIR_CONFLICT:
        n = f"{s.lower()}_us_d.csv"
        header, arows = rows_of(members[n].decode())
        _, prow = rows_of(pz.read(n).decode())
        changed = dict(arows)
        lo, hi = min(arows), max(arows)
        for d, a in arows.items():
            p = prow.get(d)
            if not p:
                continue
            ao, ah, al, ac = (float(x) for x in a[1:5])
            pc = float(p[4])
            if s in REPAIR_FLAT and ao == ah == al == ac and abs(pc / ac - 1) < 1e-9 and not (p[1] == p[2] == p[3] == p[4]):
                changed[d] = p; corrections.append({"symbol": s, "date": d, "old": a[1:], "new": p[1:], "reason": "synthetic flat bar (O=H=L=C, volume 0) replaced with real OHLCV; same close"})
            elif s in REPAIR_CONFLICT and ac > 0 and abs(pc / ac - 1) > 0.005:
                changed[d] = p; corrections.append({"symbol": s, "date": d, "old": a[1:], "new": p[1:], "reason": "archive close differs from owner STOOQ pack by >0.5 %; replaced"})
        if s in REPAIR_CONFLICT:
            for d, p in prow.items():
                if lo <= d <= hi and d not in arows:
                    changed[d] = p; corrections.append({"symbol": s, "date": d, "old": None, "new": p[1:], "reason": "session missing in archive; inserted from owner STOOQ pack"})
        if changed != arows:
            new_members[n] = to_text(header, changed).encode()
    return members, new_members, corrections, skipped


def apply(pack_path, archive_path, do_apply):
    raw = Path(pack_path).read_bytes()
    members, new_members, corrections, skipped = plan(raw, archive_path)
    summary = {"pack_sha256": hashlib.sha256(raw).hexdigest(), "append": sorted(k.split("_")[0].upper() for k in new_members if k not in members),
               "repair": sorted({c["symbol"] for c in corrections}), "corrections": len(corrections), "skipped": skipped + [{"symbol": s, "reason": "identical"} for s in SKIP_IDENTICAL],
               "apply": do_apply}
    if not do_apply or not new_members:
        return summary, corrections
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    tmp = Path(archive_path).with_suffix(".tmp.zip")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n in sorted(set(members) | set(new_members)):
            z.writestr(n, new_members[n] if n in new_members else members[n])
    with zipfile.ZipFile(tmp) as z:  # untouched members must stay byte-identical
        for n, b in members.items():
            if n not in new_members and z.read(n) != b:
                raise SystemExit(f"member {n} changed unexpectedly — abort")
    tmp.replace(archive_path)
    hist = Path(archive_path).parent
    with (hist / "corrections.jsonl").open("a", encoding="utf-8") as fh:
        for c in corrections:
            fh.write(json.dumps({**c, "source": "owner STOOQ pack", "source_sha256": summary["pack_sha256"], "applied_at": now}, ensure_ascii=False, sort_keys=True) + "\n")
    prov = {"pack": Path(pack_path).name, "sha256": summary["pack_sha256"], "imported_at": now, "appended": summary["append"],
            "quality_flags": {s: QUALITY_FLAGS.get(s, []) for s in summary["append"]}, "repaired": summary["repair"],
            "corrections": len(corrections), "authorization": "owner authorized publishing 2026-10-12 12:33 (UTC+8)",
            "validation": "research/audit/stooq_pack_validation.json", "note": "history imported today is not Genuine Forward; new symbols' first hypotheses are not revisits"}
    (hist / f"pack_provenance_{Path(pack_path).stem}.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return summary, corrections


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    archive = Path(argv[argv.index("--archive") + 1]) if "--archive" in argv else ROOT / "data" / "history" / "stooq_watchlist.zip"
    summary, corrections = apply(argv[1], archive, "--apply" in argv)
    print(json.dumps(summary, ensure_ascii=False))
    for c in corrections:
        print(json.dumps(c, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
