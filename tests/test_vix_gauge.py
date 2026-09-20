from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
LIVE_JS = (ROOT / "docs" / "assets" / "market-live.js").read_text(encoding="utf-8")
BUILDER = (ROOT / "scripts" / "fetch_and_build.py").read_text(encoding="utf-8")


def test_vix_gauge_contract():
    assert 'data-vix-gauge' in HTML
    assert 'data-us-live-price="vix"' in HTML
    assert 'data-vix-zone' in HTML
    for band in ('calm', 'mild', 'caution', 'high', 'extreme'):
        assert f'vix-arc {band}' in HTML
    for label in ('&lt;15', '15–20', '20–25', '25–30', '≥30'):
        assert label in HTML


def test_live_refresh_updates_pointer_and_zone():
    assert 'function updateVixGauge(value)' in LIVE_JS
    for threshold in ('v < 15', 'v < 20', 'v < 25', 'v < 30'):
        assert threshold in LIVE_JS
    assert "Math.min(Math.max(v, 0), 40)" in LIVE_JS
    assert "if (key === 'vix') updateVixGauge(quote.price)" in LIVE_JS


def test_daily_builder_preserves_gauge():
    assert 'def vix_gauge_card(' in BUILDER
    assert 'vix_gauge_card(vol_value,None,vix_note)' in BUILDER


if __name__ == '__main__':
    test_vix_gauge_contract()
    test_live_refresh_updates_pointer_and_zone()
    test_daily_builder_preserves_gauge()
    print('test_vix_gauge.py: all assertions passed')
