import unittest
import json
import subprocess
import sys
from scripts import trading_calendar

class TestTradingCalendarParity(unittest.TestCase):
    def test_holidays_parity(self):
        # Generate holidays for 2026-2028
        holidays = []
        for year in range(2026, 2029):
            holidays.extend([d.isoformat() for d in trading_calendar.holidays(year)])

        holidays_json = json.dumps(holidays)

        # Call Node script
        try:
            result = subprocess.run(
                ['node', 'tests/trading_calendar_parity.test.js', holidays_json],
                check=True,
                capture_output=True,
                text=True
            )
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Node tests failed with exit code {e.returncode}", file=sys.stderr)
            print("STDOUT:", e.stdout, file=sys.stderr)
            print("STDERR:", e.stderr, file=sys.stderr)
            self.fail("Node tests failed")

if __name__ == '__main__':
    unittest.main()
