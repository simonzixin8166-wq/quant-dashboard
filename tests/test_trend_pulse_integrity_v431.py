import sys, types, importlib.util, datetime, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.modules.setdefault('yfinance', types.SimpleNamespace(download=lambda *a, **k: None))
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('mav_build',ROOT/'scripts'/'fetch_and_build.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

rows=[]
end=datetime.date(2026,9,25)
d=end-datetime.timedelta(days=420)
price=30.0
while d<=end:
    if d.weekday()<5:
        price*=1.0007 + 0.0015*math.sin(d.toordinal()/17)
        rows.append({'datetime':d.isoformat(),'open':str(price*.997),'high':str(price*1.015),'low':str(price*.985),'close':str(price),'volume':'1500000'})
    d+=datetime.timedelta(days=1)
rows=list(reversed(rows))
latest=float(rows[0]['close'])
sec={'date':rows[0]['datetime'],'close':latest*1.001,'source':'Yahoo Finance'}
res=m.calculate_trend_pulse(rows,symbol='TEST',secondary=sec,today=end)
assert res['available'] is True
assert res['data_integrity']['status']=='PASS'
assert res['confidence']=='高（双源校验）'
assert res['analysis'] and res['guidance']

check=m.calculate_trend_pulse(rows,symbol='TEST',secondary=None,today=end)
assert check['available'] is True
assert check['data_integrity']['status']=='CHECK'
assert '暂停生成研究提示' in check['guidance']
assert check['guidance_paused'] is True and '中' not in check['confidence'] and '有限校验' in check['confidence']
assert check['analysis'] and check['risk_watch']            # descriptive data is kept on CHECK
assert res['guidance_paused'] is False and '暂停' not in res['guidance']

# secondary one session behind → CHECK (paused), not PASS
lag=m.calculate_trend_pulse(rows,symbol='TEST',secondary={'date':rows[1]['datetime'],'close':float(rows[1]['close'])},today=end)
assert lag['data_integrity']['status']=='CHECK' and lag['guidance_paused'] is True

# same-day sources disagree by > 1.5% → FAIL (no trend conclusion at all)
mis=m.calculate_trend_pulse(rows,symbol='TEST',secondary={'date':rows[0]['datetime'],'close':latest*1.05},today=end)
assert mis['available'] is False and mis['data_integrity']['status']=='FAIL'

# stale primary data (> 7 days old) → FAIL
stale=m.calculate_trend_pulse(rows,symbol='TEST',secondary=sec,today=end+datetime.timedelta(days=12))
assert stale['available'] is False and stale['data_integrity']['status']=='FAIL'

bad=[dict(x) for x in rows]
bad[0]['high']='1'
fail=m.calculate_trend_pulse(bad,symbol='TEST',secondary=sec,today=end)
assert fail['available'] is False
assert fail['data_integrity']['status']=='FAIL'
print('test_trend_pulse_integrity_v431.py: all assertions passed')
