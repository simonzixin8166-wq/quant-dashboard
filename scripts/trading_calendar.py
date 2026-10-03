#!/usr/bin/env python3
"""Small deterministic US equity trading-session calendar for MyAlpha.

Covers regular NYSE/Nasdaq full-day holidays needed by Playbook cooldown,
freshness, heartbeat, and outcome horizons. Special one-off closures should be
added explicitly if they occur.
"""
from __future__ import annotations
import calendar
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET=ZoneInfo("America/New_York")

def _nth_weekday(year,month,weekday,n):
    count=0
    for day in range(1,calendar.monthrange(year,month)[1]+1):
        d=date(year,month,day)
        if d.weekday()==weekday:
            count+=1
            if count==n:return d
    raise ValueError("weekday occurrence not found")

def _last_weekday(year,month,weekday):
    for day in range(calendar.monthrange(year,month)[1],0,-1):
        d=date(year,month,day)
        if d.weekday()==weekday:return d
    raise ValueError("weekday not found")

def _observed(d):
    if d.weekday()==5:return d-timedelta(days=1)
    if d.weekday()==6:return d+timedelta(days=1)
    return d

def _easter_sunday(year):
    # Anonymous Gregorian algorithm.
    a=year%19;b=year//100;c=year%100;d=b//4;e=b%4;f=(b+8)//25
    g=(b-f+1)//3;h=(19*a+b-d-g+15)%30;i=c//4;k=c%4
    l=(32+2*e+2*i-h-k)%7;m=(a+11*h+22*l)//451
    month=(h+l-7*m+114)//31;day=((h+l-7*m+114)%31)+1
    return date(year,month,day)

def holidays(year):
    rows=set()
    rows.add(_observed(date(year,1,1)))
    rows.add(_nth_weekday(year,1,0,3))   # MLK
    rows.add(_nth_weekday(year,2,0,3))   # Presidents
    rows.add(_easter_sunday(year)-timedelta(days=2)) # Good Friday
    rows.add(_last_weekday(year,5,0))    # Memorial
    if year>=2022: rows.add(_observed(date(year,6,19))) # Juneteenth
    rows.add(_observed(date(year,7,4)))
    rows.add(_nth_weekday(year,9,0,1))   # Labor
    rows.add(_nth_weekday(year,11,3,4))  # Thanksgiving
    rows.add(_observed(date(year,12,25)))
    # If next New Year's Day is Saturday, Dec 31 of current year is observed.
    next_new_year=date(year+1,1,1)
    if next_new_year.weekday()==5: rows.add(date(year,12,31))
    return rows

def is_session(value):
    d=value if isinstance(value,date) and not isinstance(value,datetime) else value.date()
    return d.weekday()<5 and d not in holidays(d.year)

def previous_session(value):
    d=value if isinstance(value,date) and not isinstance(value,datetime) else value.date()
    d-=timedelta(days=1)
    while not is_session(d): d-=timedelta(days=1)
    return d

def next_session(value):
    d=value if isinstance(value,date) and not isinstance(value,datetime) else value.date()
    d+=timedelta(days=1)
    while not is_session(d): d+=timedelta(days=1)
    return d

def sessions_between(start,end):
    """Trading sessions > start and <= end."""
    if isinstance(start,str): start=date.fromisoformat(start[:10])
    if isinstance(end,str): end=date.fromisoformat(end[:10])
    rows=[];d=start
    while d<end:
        d+=timedelta(days=1)
        if is_session(d): rows.append(d)
    return rows

def add_sessions(start,n):
    if isinstance(start,str): start=date.fromisoformat(start[:10])
    d=start
    step=1 if n>=0 else -1
    for _ in range(abs(n)):
        d=d+timedelta(days=step)
        while not is_session(d): d=d+timedelta(days=step)
    return d

def expected_latest_completed_session(now_utc=None):
    now_utc=now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is None: now_utc=now_utc.replace(tzinfo=timezone.utc)
    local=now_utc.astimezone(ET)
    d=local.date()
    # Conservative close confirmation buffer: 16:15 ET.
    if is_session(d) and (local.hour>16 or (local.hour==16 and local.minute>=15)):
        return d
    if is_session(d):
        return previous_session(d)
    while not is_session(d):
        d-=timedelta(days=1)
    return d

if __name__=="__main__":
    print(expected_latest_completed_session().isoformat())
