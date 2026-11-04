#!/usr/bin/env python3
"""D3 (GPT #133 6621145320): the recursive privacy / canary scanner finds planted values in nested objects, arrays,
JSONL and logs; reports location + category + redacted snippet only (never the raw value); and does not flag
ordinary public research content (fixture of real phrasings + a sample of real docs/research files)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import privacy_canary_scan as pcs  # noqa: E402

FX = ROOT / "tests" / "fixtures" / "privacy_canary"
NO_ALLOW = set()  # tests never rely on the Owner allowlist

# 1) positives: every category is found, at the right nested path
hits = pcs.scan_paths([FX / "positive_nested.json", FX / "positive_lines.jsonl", FX / "positive_build.log"], NO_ALLOW)
cats = {h["category"] for h in hits}
want = {"canary_token", "account_number", "position_amount", "email", "private_supabase", "private_ledger", "position_field"}
assert want <= cats, want - cats
locs = {h["location"] for h in hits}
assert any("records[0].nested.deep[0].text" in l for l in locs), locs          # nested object in array in object
assert any("records[3].claims[0][1].text" in l for l in locs), locs           # array inside array
assert any("[line 1].a.b[0]" in l for l in locs), locs                         # JSONL nested
assert any(l.endswith("positive_build.log:2") for l in locs), locs            # plain log line
assert any("records[7].holdings[0].qty" in l for l in locs), locs             # holding field by value
print(f"PASS positives: {len(hits)} hits, categories {sorted(cats)}")

# 2) redaction: no raw sensitive value appears in any reported snippet
raw = ["CANARY-7f3a9c21-4b6e-4d2a-9e11-0c55aa77bb01", "6228 4801 2345 6789 012", "real.person@gmail.com",
       "myalpha-ledger-private/blob", "$95,000", "9876543210", "1234-5678-9012", "options_positions"]
dump = json.dumps(hits, ensure_ascii=False)
assert not [r for r in raw if r in dump], [r for r in raw if r in dump]
print("PASS redaction: snippets never contain the raw value")

# 3) negatives: real public phrasings (prices, per-share figures, EPS, public edge-function URL, form placeholder)
neg = pcs.scan_paths([FX / "negative_public.json"], NO_ALLOW)
assert not neg, neg
# real public research files sampled from docs/research (third-party excerpts, propositions, SEC text)
sample = [ROOT / "docs/research" / n for n in ("source_reading_memory.json", "official_evidence.json", "event_evidence.json",
                                              "auto_thesis_drafts.json", "forward_scorecard.json", "core_tier_alert_status.json")]
real = pcs.scan_paths([p for p in sample if p.exists()], NO_ALLOW)
assert not real, real[:5]
print(f"PASS negatives: 0 hits on the public-phrasing fixture and on {sum(p.exists() for p in sample)} real docs/research files")

# 4) the CLI exits 1 on a hit and 0 on clean input (no warning-only mode)
assert pcs.main([str(FX / "positive_nested.json")]) == 1
assert pcs.main([str(FX / "negative_public.json")]) == 0
# 5) an allowlist entry without owner_approval never silences a hit
import hashlib, tempfile
tmp = Path(tempfile.mkdtemp()) / "allow.json"
tmp.write_text(json.dumps({"entries": [{"value_sha256": hashlib.sha256(b"real.person@gmail.com").hexdigest(), "owner_approval": None}]}))
assert any(h["category"] == "email" for h in pcs.scan_paths([FX / "positive_nested.json"], pcs.load_allowlist(tmp)))
print("PASS CLI exit codes and allowlist requires owner_approval")
