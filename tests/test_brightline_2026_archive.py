from pathlib import Path
import json, re
ROOT=Path(__file__).resolve().parents[1]
rows=[]
for q in ('q1','q2','q3'):
    p=ROOT/'docs'/'data'/f'brightline_2026_{q}.json'
    d=json.loads(p.read_text(encoding='utf-8'))
    assert d['year']==2026
    rows.extend(d['articles'])
urls=[re.sub(r'#.*$','',x['url']) for x in rows]
assert len(rows)==118
assert len(set(urls))==118
assert sum(1 for x in rows if x.get('deep_analysis'))==14
js=(ROOT/'docs'/'assets'/'wenxuecity.js').read_text(encoding='utf-8')
assert 'brightline-2026.html' in js
page=(ROOT/'docs'/'brightline-2026.html').read_text(encoding='utf-8')
assert '118篇' in page and '14 篇' in page and '104 篇' in page
wf=(ROOT/'.github'/'workflows'/'wenxuecity.yml').read_text(encoding='utf-8')
assert re.search(r'^\s*schedule\s*:',wf,re.M) is None
print('PASS BrightLine 2026 static archive')
