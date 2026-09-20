"""Build a small public calendar from official Fed and BLS sources only."""
import datetime as dt
import json
import os
import re
import urllib.request
from zoneinfo import ZoneInfo

HEADERS = {"User-Agent": "Mozilla/5.0 myAlphaView/2.2 (public research dashboard)"}
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
ET = ZoneInfo("America/New_York")

def fetch_text(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8-sig")

def parse_bls_cpi(text):
    events = []
    for block in text.split("BEGIN:VEVENT")[1:]:
        summary = re.search(r"^SUMMARY:(.+)$", block, re.M)
        start = re.search(r"^DTSTART(?:;[^:]*)?:(\d{8}T\d{6})", block, re.M)
        if not summary or not start or "Consumer Price Index" not in summary.group(1):
            continue
        value = dt.datetime.strptime(start.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=ET)
        events.append({"type":"CPI","title":"美国消费者价格指数发布","datetime":value.isoformat(),"source":"BLS","source_url":"https://www.bls.gov/schedule/news_release/cpi.htm"})
    return events

def parse_fomc(text):
    events = []
    panels = re.findall(r'(\d{4}) FOMC Meetings</a></h4>(.*?)(?=<div class="panel panel-default"|$)', text, re.S)
    months = {m:i for i,m in enumerate(("January","February","March","April","May","June","July","August","September","October","November","December"),1)}
    for year, panel in panels:
        for month, raw_date in re.findall(r'fomc-meeting__month[^>]*><strong>([A-Za-z]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)</div>', panel, re.S):
            nums = re.findall(r'\d{1,2}', raw_date)
            if month not in months or not nums: continue
            decision_day = int(nums[-1])
            value = dt.datetime(int(year), months[month], decision_day, 14, 0, tzinfo=ET)
            events.append({"type":"FOMC","title":"FOMC利率决议日","datetime":value.isoformat(),"source":"Federal Reserve","source_url":FED_URL})
    return events

def main():
    events = parse_bls_cpi(fetch_text(BLS_ICS_URL)) + parse_fomc(fetch_text(FED_URL))
    events.sort(key=lambda x:x["datetime"])
    if not events:
        raise RuntimeError("Official calendars returned no recognized events; existing file was not overwritten")
    payload = {"updated_at":dt.datetime.now(dt.timezone.utc).isoformat(),"policy":"official_sources_only","events":events}
    out = os.path.join(os.path.dirname(__file__), "..", "docs", "data", "market_events.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
    print(f"Wrote {len(events)} official events to {out}")

if __name__ == "__main__": main()
