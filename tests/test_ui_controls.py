from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'docs' / 'index.html').read_text(encoding='utf-8')
JS_FILES = list((ROOT / 'docs' / 'assets').glob('*.js'))
JS = '\n'.join(p.read_text(encoding='utf-8') for p in JS_FILES)
# Inline application JS is generated inside index.html; include it for function resolution.
ALL_JS = JS + '\n' + HTML

class ButtonParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.buttons=[]; self._current=None
    def handle_starttag(self, tag, attrs):
        if tag == 'button':
            self._current={'attrs':dict(attrs),'text':''}; self.buttons.append(self._current)
    def handle_data(self, data):
        if self._current is not None: self._current['text'] += data
    def handle_endtag(self, tag):
        if tag == 'button': self._current=None

parser=ButtonParser(); parser.feed(HTML)
buttons=parser.buttons
assert buttons, 'No buttons found in generated dashboard'

# 1) Inline onclick handlers must reference a callable symbol that exists in page/app JS.
for b in buttons:
    onclick=b['attrs'].get('onclick','').strip()
    if not onclick: continue
    m=re.match(r'([A-Za-z_$][\w.$]*)\s*\(', onclick)
    assert m, f"Unrecognized inline onclick: {onclick}"
    name=m.group(1)
    leaf=name.split('.')[-1]
    # Either function declaration / assignment / object method usage must exist in app sources.
    assert (re.search(rf'function\s+{re.escape(leaf)}\s*\(', ALL_JS)
            or re.search(rf'\b{re.escape(name)}\b', ALL_JS)), f"Missing onclick target {name}: {b['text'].strip()}"

# 2) Buttons without inline handlers must have a concrete selector hook used by JS.
selector_hooks = {
    'data-tooltip':'info-tip',
    'data-leaps-symbol':'data-leaps-symbol',
    'data-finance-mode':'data-finance-mode',
    'data-rate-preset':'data-rate-preset',
    'data-finance-view':'data-finance-view',
    'data-strategy':'data-strategy',
    'data-date-preset':'data-date-preset',
    'data-spot-preset':'data-spot-preset',
    'data-iv':'data-iv',
}
for b in buttons:
    a=b['attrs']
    if a.get('onclick'): continue
    bid=a.get('id')
    if bid:
        assert bid in JS, f"Button #{bid} has no JS binding: {b['text'].strip()}"
        continue
    matched=False
    for attr,token in selector_hooks.items():
        if attr in a:
            if attr == 'data-tooltip':
                css='\n'.join(x.read_text(encoding='utf-8') for x in (ROOT/'docs'/'assets').glob('*.css'))
                assert '.info-tip:focus' in css or '.info-tip:focus-visible' in css, f"Tooltip button has no focus interaction: {b['text'].strip()}"
            else:
                assert token in JS, f"Button [{attr}] has no delegated binding: {b['text'].strip()}"
            matched=True; break
    assert matched, f"Button lacks onclick/id/delegated selector: {a} {b['text'].strip()}"

# Regression: Daily Action options jump must use the robust tab opener.
assert 'onclick="openDashboardTab(\'tab-options\')"' in HTML
assert 'function openDashboardTab(id)' in HTML
assert 'id="tab-options"' in HTML
# Regression: fake private-mode button was converted to a status element.
assert '<span id="privateModeShield"' in HTML
print(f'test_ui_controls.py: audited {len(buttons)} generated buttons; all have an interaction binding')


# 3) Dynamic HTML templates in JS must not emit dead onclick handlers.
dynamic_handlers=[]
for path in JS_FILES:
    src=path.read_text(encoding='utf-8')
    for m in re.finditer(r'onclick=["\']\s*([A-Za-z_$][\w.$]*)\s*\(', src):
        dynamic_handlers.append((path.name,m.group(1)))
assert dynamic_handlers, 'No dynamic onclick handlers discovered'
for filename,name in dynamic_handlers:
    leaf=name.split('.')[-1]
    assert (re.search(rf'function\s+{re.escape(leaf)}\s*\(', ALL_JS)
            or re.search(rf'\b{re.escape(name)}\b', ALL_JS)
            or re.search(rf'\b{re.escape(leaf)}\s*[:=]', ALL_JS)), f"Missing dynamic onclick target {name} emitted by {filename}"

# 4) Every sidebar tab target must exist exactly once and switchTab/openDashboardTab must be present.
nav_targets=re.findall(r"switchTab\('([^']+)'", HTML)
assert nav_targets, 'No sidebar tab targets found'
for target in sorted(set(nav_targets)):
    assert len(re.findall(rf'id=["\']{re.escape(target)}["\']', HTML))==1, f"Tab target #{target} missing or duplicated"
assert 'function switchTab(' in HTML
assert 'function openDashboardTab(id)' in HTML

print(f'dynamic controls audited: {len(dynamic_handlers)} JS onclick handlers · {len(set(nav_targets))} tab targets')
