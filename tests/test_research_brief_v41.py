from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
generator = (ROOT / 'scripts' / 'fetch_and_build.py').read_text(encoding='utf-8')
page = (ROOT / 'docs' / 'index.html').read_text(encoding='utf-8')

assert 'def build_market_brief' in generator
assert 'def build_what_changed' in generator
assert 'def build_iren_brief' in generator
assert 'def fetch_iren_news' in generator
assert '市场简报' in page
assert '今日变化' in page
assert 'IREN 每日观察' in page
assert 'market-tape' in page
assert 'STRATEGY ENGINE ·' not in page
assert 'IREN 每日观察' in page and '重点研究 · IREN' in page
