"""#133 6106703460 P0: wxc-bot rule-based claims (claim_extractor, strict precision 0/6) are experimental.
No scoring / forward / action code in this repo may read the research-feed `claims` field."""
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CONSUMERS = ["scripts/source_intelligence_engine.py", "scripts/forward_observation_engine.py", "scripts/server_action_engine.py",
             "scripts/investment_watch_engine.py", "docs/assets/autonomous-agent.js", "docs/assets/decision-journal.js",
             "docs/assets/invest-actions.js", "docs/assets/product-intelligence.js", "docs/assets/single-action-outlet.js"]
pat = re.compile(r"""\[\s*['"]claims['"]\s*\]|\.get\(\s*['"]claims['"]|\.claims\b|claims_full|claim_extractor""")
hits = [p for p in CONSUMERS if (ROOT / p).exists() and pat.search((ROOT / p).read_text(encoding="utf-8"))]
assert not hits, f"experimental claims consumed by: {hits}"
print("PASS experimental claims isolated")
