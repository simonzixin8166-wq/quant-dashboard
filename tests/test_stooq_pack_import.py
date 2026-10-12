"""D-03 import script: refuses unknown packs, appends new members byte-for-byte, repairs only synthetic flat bars and
>0.5 % conflicts with a correction log, keeps every other member identical, and is idempotent. Synthetic data only."""
import hashlib, io, json, sys, tempfile, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import stooq_pack_import as m  # noqa: E402

H = "Date,Open,High,Low,Close,Volume"
arch_f = f"{H}\n2026-10-01,9,10.5,8.5,10,100\n2026-10-02,10,10,10,10,0.0\n"           # synthetic flat bar on 10-02
arch_c = f"{H}\n2026-10-01,20,21,19,20,100\n2026-10-05,20,21,19,21,100\n"           # missing 10-02, conflict on 10-05
arch_k = f"{H}\n2026-10-01,5,6,4,5,1\n"                                              # untouched member
pack_f = f"{H}\n2026-10-01,9,10.5,8.5,10,100\n2026-10-02,9.8,10.4,9.6,10,555\n"
pack_c = f"{H}\n2026-10-01,20,21,19,20,100\n2026-10-02,20,22,19.5,21.5,100\n2026-10-05,20,21,19,20,100\n"
pack_n = f"{H}\n2026-10-01,1,2,0.5,1.5,10\n"
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    for n, t in (("zzzf_us_d.csv", pack_f), ("zzzc_us_d.csv", pack_c), ("zzzn_us_d.csv", pack_n)):
        z.writestr(n, t)
    z.writestr("import_manifest.json", json.dumps({"files": [{"filename": n, "sha256": hashlib.sha256(t.encode()).hexdigest()}
               for n, t in (("zzzf_us_d.csv", pack_f), ("zzzc_us_d.csv", pack_c), ("zzzn_us_d.csv", pack_n))]}))
pack = buf.getvalue()
m.APPEND, m.REPAIR_FLAT, m.REPAIR_CONFLICT, m.SKIP_IDENTICAL = ["ZZZN"], ["ZZZF"], ["ZZZC"], []
with tempfile.TemporaryDirectory() as t:
    t = Path(t); arc = t / "a.zip"; pk = t / "pack.zip"; pk.write_bytes(pack)
    with zipfile.ZipFile(arc, "w") as z:
        z.writestr("zzzf_us_d.csv", arch_f); z.writestr("zzzc_us_d.csv", arch_c); z.writestr("zzzk_us_d.csv", arch_k)
    # unknown pack is refused
    m.EXPECTED_SHA256 = "0" * 64
    try:
        m.apply(pk, arc, True); raise AssertionError("must refuse")
    except SystemExit:
        pass
    m.EXPECTED_SHA256 = hashlib.sha256(pack).hexdigest()
    s, corr = m.apply(pk, arc, False)                     # dry run writes nothing
    assert s["append"] == ["ZZZN"] and len(corr) == 3 and not (t / "corrections.jsonl").exists()
    s, corr = m.apply(pk, arc, True)
    z = zipfile.ZipFile(arc)
    assert z.read("zzzk_us_d.csv").decode() == arch_k, "untouched member must stay byte-identical"
    assert z.read("zzzn_us_d.csv").decode() == pack_n, "new member keeps original bytes"
    f = z.read("zzzf_us_d.csv").decode().splitlines()
    assert f[1] == "2026-10-01,9,10.5,8.5,10,100" and f[2] == "2026-10-02,9.8,10.4,9.6,10,555"
    c = z.read("zzzc_us_d.csv").decode().splitlines()
    assert c[2].startswith("2026-10-02,20,22") and c[3] == "2026-10-05,20,21,19,20,100" and c[1] == "2026-10-01,20,21,19,20,100"
    log = [json.loads(x) for x in (t / "corrections.jsonl").read_text().splitlines()]
    assert {(x["symbol"], x["date"]) for x in log} == {("ZZZF", "2026-10-02"), ("ZZZC", "2026-10-02"), ("ZZZC", "2026-10-05")}
    assert all(x["source_sha256"] == m.EXPECTED_SHA256 for x in log)
    assert (t / "pack_provenance_pack.json").exists()
    s2, corr2 = m.apply(pk, arc, True)                    # idempotent
    assert s2["append"] == [] and corr2 == [] and len((t / "corrections.jsonl").read_text().splitlines()) == 3
print("test_stooq_pack_import OK")
