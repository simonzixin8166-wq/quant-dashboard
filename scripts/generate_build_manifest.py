#!/usr/bin/env python3
import hashlib,json,datetime,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
FILES=['index.html','data.json','assets/investment-assistant.js','assets/autonomous-agent.js','assets/decision-journal.js','assets/autonomous-qa.js','assets/market-live.js','assets/stock-watchlist.js','assets/options-v2.js','research/historical_journal.json','research/autonomous_agent.json','research/research_planner.json','research/research_execution.json','research/self_improvement.json','research/module_intelligence.json']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
meta=(DOCS/'index.html').read_text(encoding='utf-8',errors='ignore')
m=re.search(r'<meta name="application-version" content="([^"]+)"',meta)
version=m.group(1) if m else 'unknown'
hashes={f:sha(DOCS/f) for f in FILES if (DOCS/f).exists()}
fingerprint=hashlib.sha256((version+'|'+'|'.join(f'{k}:{v}' for k,v in sorted(hashes.items()))).encode()).hexdigest()[:20]
out={'app_version':version,'build_id':fingerprint,'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'critical_files':hashes}
(DOCS/'build-manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"build-manifest {version} {fingerprint}")
