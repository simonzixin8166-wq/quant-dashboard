#!/usr/bin/env python3
import hashlib,json,datetime,pathlib,re,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
sys.path.insert(0,str(ROOT/'scripts'))
from app_version import COMPONENT_VERSIONS
FILES=['index.html','data.json','assets/investment-assistant.js','assets/autonomous-agent.js','assets/decision-journal.js','assets/autonomous-qa.js','assets/market-live.js','assets/stock-watchlist.js','assets/options-v2.js','research/historical_journal.json','research/autonomous_agent.json','research/research_planner.json','research/official_evidence.json','research/event_evidence.json','research/event_window_attribution.json','research/research_execution.json','research/self_improvement.json','research/module_intelligence.json','research/cross_asset_divergence.json','research/cross_asset_divergence_history.json','research/breadth_intelligence.json','research/breadth_intelligence_history.json','research/regime_combination_memory.json','research/regime_combination_history.json','research/system_status.json','research/learning_evaluation.json','research/playbook_status.json','research/ledger_anchor.json','research/range_intelligence.json','research/playbook_outcome_shadow.json','research/walk_forward_replay.json','research/controlled_learning_policy.json','research/forward_learning_feedback.json','research/challenger_experiments.json','research/source_reading_memory.json']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
meta=(DOCS/'index.html').read_text(encoding='utf-8',errors='ignore')
m=re.search(r'<meta name="application-version" content="([^"]+)"',meta)
version=m.group(1) if m else 'unknown'
hashes={f:sha(DOCS/f) for f in FILES if (DOCS/f).exists()}
fingerprint=hashlib.sha256((version+'|'+'|'.join(f'{k}:{v}' for k,v in sorted(hashes.items()))).encode()).hexdigest()[:20]
out={'app_version':version,'build_id':fingerprint,'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'component_versions':COMPONENT_VERSIONS,'critical_files':hashes}
(DOCS/'build-manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"build-manifest {version} {fingerprint}")
