"""D-07: STOOQ pack validator flags bad inputs and never touches the canonical archive."""
import hashlib, io, json, sys, tempfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stooq_pack_validate as v  # noqa: E402

before = hashlib.sha256((ROOT / "data/history/stooq_watchlist.zip").read_bytes()).hexdigest()
good = "Date,Open,High,Low,Close,Volume\n2026-10-05,10,11,9,10.5,100\n2026-10-06,10.5,11,10,10.8,100\n2026-10-07,10.8,11.2,10.6,11,100\n"
bad = "Date,Open,High,Low,Close,Volume\n2026-10-05,10,11,9,12,100\n2026-10-05,10,11,9,10,100\n2026-10-10,10,11,9,10,100\n"
jump = "Date,Open,High,Low,Close,Volume\n2026-10-05,10,11,9,10,100\n2026-10-06,20,21,19,20,100\n"
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("zzza_us_d.csv", good); z.writestr("zzzb_us_d.csv", bad); z.writestr("zzzc_us_d.csv", jump)
    z.writestr("import_manifest.json", json.dumps({"files": [
        {"filename": "zzza_us_d.csv", "rows": 3, "start": "2026-10-05", "end": "2026-10-07", "sha256": hashlib.sha256(good.encode()).hexdigest()},
        {"filename": "zzzb_us_d.csv", "rows": 3, "start": "2026-10-05", "end": "2026-10-10", "sha256": "0" * 64},
        {"filename": "zzzc_us_d.csv", "rows": 2, "start": "2026-10-05", "end": "2026-10-06", "sha256": hashlib.sha256(jump.encode()).hexdigest()}]}))
with tempfile.TemporaryDirectory() as t:
    p = Path(t) / "pack.zip"; p.write_bytes(buf.getvalue())
    r = v.validate(p)
s = r["symbols"]
assert s["ZZZA"]["verdict"] == "new" and all(s["ZZZA"]["manifest"].values())
b = s["ZZZB"]
assert b["verdict"] == "invalid_or_review" and b["duplicates"] == 1 and b["ohlc_violations"] >= 1
assert b["non_session_dates"] == ["2026-10-10"] and not b["manifest"]["sha256_match"]
assert s["ZZZC"]["verdict"] == "invalid_or_review" and s["ZZZC"]["moves_over_40pct"]
assert r["import_plan"]["append_new"] == ["ZZZA"]
# existing symbol overlap: an identical copy of an archive member is overlap_identical
with zipfile.ZipFile(ROOT / "data/history/stooq_watchlist.zip") as z:
    spy = z.read("spy_us_d.csv").decode()
info, bars = v.check_file("spy_us_d.csv", spy)
assert v.overlap("SPY", bars, v.archive_bars())["overlap"] == "overlap_identical"
assert hashlib.sha256((ROOT / "data/history/stooq_watchlist.zip").read_bytes()).hexdigest() == before, "validator must not modify the archive"
print("test_stooq_pack_validate OK")
