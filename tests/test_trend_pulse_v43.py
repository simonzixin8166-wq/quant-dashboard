import sys, types, importlib.util, datetime, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.modules.setdefault('yfinance', types.SimpleNamespace(download=lambda *a, **k: None))
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('mav_build',ROOT/'scripts'/'fetch_and_build.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

rows=[]
start=datetime.date(2025,1,1)
price=20.0
for i in range(420):
    d=start+datetime.timedelta(days=i)
    if d.weekday()>=5:
        continue
    price*=1.0015 + 0.0025*math.sin(i/17)
    rows.append({'datetime':d.isoformat(),'open':str(price*.995),'high':str(price*1.018),'low':str(price*.982),'close':str(price),'volume':str(1_000_000+i*500)})
rows=list(reversed(rows))
result=m.calculate_trend_pulse(rows)
assert result['available'] is True
assert -100 <= result['score'] <= 100
assert result['state'] in {'趋势恶化','修复中','趋势启动','趋势退潮','高位钝化','二次启动','趋势延续','震荡观察'}
assert result['weekly'] in {'多头','空头','过渡','数据不足'}
assert len(result['series']) > 20
assert 'Supertrend' in result['method'] and 'ADX' in result['method']
