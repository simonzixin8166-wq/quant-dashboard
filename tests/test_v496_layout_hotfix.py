from pathlib import Path
root=Path(__file__).resolve().parents[1]
css=(root/'docs/assets/design-v4.8.css').read_text()
html=(root/'docs/index.html').read_text()
gen=(root/'scripts/fetch_and_build.py').read_text()
assert '\\n' not in css, 'design CSS contains literal \\n tokens'
assert 'footer footer-with-analytics' in html
assert 'footer-analytics private-console' in html
assert '<section class="section private-console site-analytics-bottom">' not in html
assert 'footer footer-with-analytics' in gen
assert '.stock-table table{' in css and 'min-width:0!important' in css
for n,w in [(1,'20%'),(2,'13%'),(3,'12%'),(4,'10%'),(5,'7%'),(6,'10%'),(7,'17%'),(8,'11%')]:
    needle=f'.stock-table th:nth-child({n}),.stock-table td:nth-child({n}){{width:{w}!important}}'
    assert needle in css, needle
assert "if(id === 'tab-stocks') document.querySelectorAll('.stock-table')" in html
print('test_v496_layout_hotfix.py: all assertions passed')
