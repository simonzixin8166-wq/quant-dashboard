from pathlib import Path
import json,zipfile,re
ROOT=Path(__file__).resolve().parents[1]
arc=ROOT/'data/history/stooq_watchlist.zip'
assert arc.exists() and arc.stat().st_size>100_000
with zipfile.ZipFile(arc) as z:
    names=[n for n in z.namelist() if re.match(r'^[a-z0-9.-]+_us_d\.csv$',n)]
assert len(names)==21, len(names)
report=json.loads((ROOT/'docs/research/historical_journal.json').read_text())
assert report['version']=='5.3.0'
assert report['summary']['symbols']==21
assert report['summary']['events']>500
assert report['summary']['mature_60']>300
assert '二次启动' in report['profiles']
assert 'excess_vs_qqq_avg' in report['profiles']['二次启动']['horizons']['60']
js=(ROOT/'docs/assets/decision-journal.js').read_text()
qa=(ROOT/'docs/assets/autonomous-qa.js').read_text()
assert 'historical_journal.json' in js
assert 'global.mavSupabase' in js
assert "getElementById('marketOptionAlert')" in qa
assert "function versionAligned" in qa
assert "APP_VERSION" in qa and "application-version" in qa
print('PASS V5.3 local history + autonomous learning contract')
