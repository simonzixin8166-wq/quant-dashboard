import datetime, importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("fb",ROOT/"scripts"/"fetch_and_build.py")
fb=importlib.util.module_from_spec(spec);spec.loader.exec_module(fb)

rows=[
 {"datetime":"2026-10-02","close":"11"},
 {"datetime":"2026-10-01","close":"10"},
 {"datetime":"2026-09-30","close":"9"},
]
# 14:30 UTC = 10:30 ET on Oct 2: today's candle must be excluded.
out=fb.filter_completed_us_daily_rows(rows,datetime.datetime(2026,10,2,14,30,tzinfo=datetime.timezone.utc))
assert [x["datetime"] for x in out]==["2026-10-01","2026-09-30"]
# 21:00 UTC = 17:00 ET: completed daily candle may be used.
out2=fb.filter_completed_us_daily_rows(rows,datetime.datetime(2026,10,2,21,0,tzinfo=datetime.timezone.utc))
assert out2==rows
# Weekend: do not drop the latest historical row.
out3=fb.filter_completed_us_daily_rows(rows,datetime.datetime(2026,10,3,14,30,tzinfo=datetime.timezone.utc))
assert out3==rows
print("PASS V6.6.3 completed US daily candle guard")
