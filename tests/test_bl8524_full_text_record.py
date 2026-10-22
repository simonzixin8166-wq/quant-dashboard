"""R-01 full-text verification record (#133, PR #231 follow-up): coverage complete, categories valid,
no full text stored, partial history retained, numbers match the owner's outline."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "shadow_theses"
r = json.loads((D / "brightline_8524_full_text_verified_v1_0.json").read_text(encoding="utf-8"))
v = r["source"]["verification"]
assert r["status"].startswith("full_text_verified") and r["production_use"] is False and r["automatic_orders"] is False
assert v["paragraphs"] == 50 and v["body_chars_with_ws"] == 3266 and len(v["section_headings"]) == 7
assert v["normalized_paragraph_sha256"] == "f909e1b9d5d085e1f0b0ec35bf24781fdae9eaca21831269c282a5d393bd56ec"
assert all(r["source"]["matches_owner_outline"].values())
# coverage: every paragraph mapped; every non-heading paragraph reviewed (claims or explicitly rhetoric-only)
m = r["coverage"]["matrix"]
assert [x["p"] for x in m] == list(range(1, 51)) and sum(x["role"] == "section_heading" for x in m) == 7
assert all(x["role"] in ("section_heading", "claims", "rhetoric_no_checkable_claim") for x in m)
assert r["coverage"]["paragraphs_with_claims"] + len(r["coverage"]["paragraphs_rhetoric_only"]) == r["coverage"]["non_heading_paragraphs"] == 43
# categories
cats = {"author_claim", "officially_verified", "derived", "unverified"}
assert all(c["category"] in cats for c in r["claims"]) and {c["category"] for c in r["claims"]} == cats
ids = {c["id"] for c in r["claims"]}
assert all(set(x["claims"]) <= ids for x in m)
# key author rules present (cash floor, three tranches, risk freeze)
txt = json.dumps(r["claims"], ensure_ascii=False)
for k in ("20%", "第一批", "第二批", "第三批", "坏情境", "杠杆"):
    assert k in txt, k
# no full text stored: short quotes ≤ 360 chars total; no stored paragraph text
assert sum(len(q["quote"]) for q in r["short_quotes"]) == r["source"]["excerpt_chars_persisted"] <= 360
assert all("text" not in x for x in m)
log = json.loads((D / "logs" / "bl8524_full_text_verification_2026-10-13.json").read_text(encoding="utf-8"))
assert log["stored_text"].startswith("none") and len(log["paragraph_sha256_16"]) == 50
# author claims never 'verified'; partial history retained untouched
for c in r["author_claims_unverified"]:
    assert not str(c["verification"]).startswith("verified")
for f in ("brightline_8524_bottom_window_shadow_v0_1.json", "brightline_8524_bottom_window_shadow_v0_2.json", "brightline_8524_analysis_zh.md"):
    assert (D / f).exists(), f
assert r["tranche_rules"]["logic_change_vs_v1"] is False
print("PASS BrightLine 8524 full-text record")
