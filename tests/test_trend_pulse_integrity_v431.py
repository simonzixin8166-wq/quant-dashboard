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

bad=[dict(x) for x in rows]
bad[0]['high']='1'
fail=m.calculate_trend_pulse(bad,symbol='TEST',secondary=sec,today=end)
assert fail['available'] is False
assert fail['data_integrity']['status']=='FAIL'
print('test_trend_pulse_integrity_v431.py: all assertions passed')
