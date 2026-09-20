"""Build a small public calendar from official Fed and BLS sources only."""
import datetime as dt
import json
import os
import re
import time
import urllib.request
from zoneinfo import ZoneInfo

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,text/calendar;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
ET = ZoneInfo("America/New_York")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "data", "market_events.json")

def fetch_text(url, attempts=3):
    last_error = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read().decode("utf-8-sig")
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise last_error

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

def load_cached_events(out):
    try:
        with open(out, encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("policy") != "official_sources_only":
            return {}, None
        grouped = {"CPI": [], "FOMC": []}
        for event in payload.get("events", []):
            kind = event.get("type")
            if kind in grouped and event.get("datetime") and event.get("source"):
                grouped[kind].append(event)
        return grouped, payload.get("updated_at")
    except (OSError, ValueError, TypeError):
        return {}, None

def main():
    out = OUTPUT_PATH
    cached, cached_at = load_cached_events(out)
    events, status, refreshed = [], {}, False
    sources = (
        ("CPI", BLS_ICS_URL, parse_bls_cpi),
        ("FOMC", FED_URL, parse_fomc),
    )
    for kind, url, parser in sources:
        try:
            current = parser(fetch_text(url))
            if not current:
                raise ValueError(f"{kind} official source returned no recognized events")
            events.extend(current)
            status[kind] = "fresh"
            refreshed = True
            print(f"{kind}: refreshed {len(current)} events from official source")
        except Exception as exc:
            fallback = cached.get(kind, [])
            events.extend(fallback)
            status[kind] = "cached" if fallback else "unavailable"
            print(f"WARNING: {kind} refresh failed ({exc}); using {len(fallback)} cached official events")

    events.sort(key=lambda x:x["datetime"])
    if not events:
        print("WARNING: official calendars unavailable and no valid cache exists; continuing without overwriting")
        return
    if not refreshed:
        print(f"Official calendar endpoints unavailable; retained last verified file from {cached_at or 'unknown time'}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    payload = {"updated_at":now,"policy":"official_sources_only","source_status":status,"events":events}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    temp = out + ".tmp"
    with open(temp,"w",encoding="utf-8") as f:
        json.dump(payload,f,ensure_ascii=False,indent=2)
    os.replace(temp,out)
    print(f"Wrote {len(events)} verified official events to {out}; status={status}")

if __name__ == "__main__": main()
