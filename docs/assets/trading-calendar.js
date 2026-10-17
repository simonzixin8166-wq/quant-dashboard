(function(global) {
  'use strict';

  const SPECIAL_CLOSURES = [
    '2018-12-05'
  ];

  function isLeapYear(year) {
    return (year % 4 === 0 && year % 100 !== 0) || (year % 400 === 0);
  }

  function daysInMonth(year, month) {
    return [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  }

  function getWeekday(year, month, day) {
    return new Date(`${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T12:00:00Z`).getUTCDay();
  }

  function formatDate(year, month, day) {
    return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  }

  function nthWeekday(year, month, targetWeekday, n) {
    let count = 0;
    for (let day = 1; day <= daysInMonth(year, month); day++) {
      if (getWeekday(year, month, day) === targetWeekday) {
        count++;
        if (count === n) return formatDate(year, month, day);
      }
    }
    throw new Error('weekday occurrence not found');
  }

  function lastWeekday(year, month, targetWeekday) {
    for (let day = daysInMonth(year, month); day > 0; day--) {
      if (getWeekday(year, month, day) === targetWeekday) return formatDate(year, month, day);
    }
    throw new Error('weekday not found');
  }

  function shiftDate(dateStr, offsetDays) {
    const d = new Date(`${dateStr}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() + offsetDays);
    return d.toISOString().slice(0, 10);
  }

  function observed(dateStr) {
    const d = new Date(`${dateStr}T12:00:00Z`);
    const w = d.getUTCDay();
    if (w === 6) { // Saturday, observe on Friday
      return shiftDate(dateStr, -1);
    }
    if (w === 0) { // Sunday, observe on Monday
      return shiftDate(dateStr, 1);
    }
    return dateStr;
  }

  function easterSunday(year) {
    const a = year % 19;
    const b = Math.floor(year / 100);
    const c = year % 100;
    const d = Math.floor(b / 4);
    const e = b % 4;
    const f = Math.floor((b + 8) / 25);
    const g = Math.floor((b - f + 1) / 3);
    const h = (19 * a + b - d - g + 15) % 30;
    const i = Math.floor(c / 4);
    const k = c % 4;
    const l = (32 + 2 * e + 2 * i - h - k) % 7;
    const m = Math.floor((a + 11 * h + 22 * l) / 451);
    const month = Math.floor((h + l - 7 * m + 114) / 31);
    const day = ((h + l - 7 * m + 114) % 31) + 1;
    return formatDate(year, month, day);
  }

  function holidays(year) {
    const rows = new Set();
    rows.add(observed(formatDate(year, 1, 1))); // New Year's Day
    rows.add(nthWeekday(year, 1, 1, 3));        // MLK (Monday=1)
    rows.add(nthWeekday(year, 2, 1, 3));        // Presidents
    rows.add(shiftDate(easterSunday(year), -2)); // Good Friday
    rows.add(lastWeekday(year, 5, 1));          // Memorial
    if (year >= 2022) {
      rows.add(observed(formatDate(year, 6, 19))); // Juneteenth
    }
    rows.add(observed(formatDate(year, 7, 4)));   // Independence Day
    rows.add(nthWeekday(year, 9, 1, 1));        // Labor Day
    rows.add(nthWeekday(year, 11, 4, 4));       // Thanksgiving (Thursday=4)
    rows.add(observed(formatDate(year, 12, 25))); // Christmas

    for (const d of SPECIAL_CLOSURES) {
      if (d.startsWith(String(year))) {
        rows.add(d);
      }
    }
    return Array.from(rows);
  }

  function isNyseHoliday(dateStr) {
    const year = Number(dateStr.slice(0, 4));
    return holidays(year).includes(dateStr);
  }

  function isUsRegularSession(now = new Date()) {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23'
    }).formatToParts(now);

    const v = Object.fromEntries(parts.map(x => [x.type, x.value]));

    if (['Sat', 'Sun'].includes(v.weekday)) return false;

    const dateStr = `${v.year}-${v.month}-${v.day}`;
    if (isNyseHoliday(dateStr)) return false;

    const minute = Number(v.hour) * 60 + Number(v.minute);

    // Check for early close at 13:00 ET (780 minutes)
    // Black Friday (day after Thanksgiving) and Christmas Eve
    const isEarlyClose = (dateStr === '2026-11-27' || dateStr === '2026-12-24');

    if (isEarlyClose) {
      return minute >= 570 && minute < 780;
    }

    return minute >= 570 && minute < 960;
  }

  global.isNyseHoliday = isNyseHoliday;
  global.isUsRegularSession = isUsRegularSession;
  global.holidays = holidays;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { isNyseHoliday, isUsRegularSession, holidays };
  }
})(typeof window !== 'undefined' ? window : globalThis);
