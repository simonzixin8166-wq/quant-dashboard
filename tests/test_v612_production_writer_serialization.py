from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
writers=[
    ROOT/".github/workflows/daily.yml",
    ROOT/".github/workflows/source-intelligence-validation.yml",
    ROOT/".github/workflows/trend-pulse-backtest.yml",
    ROOT/".github/workflows/wenxuecity.yml",
]
for path in writers:
    text=path.read_text(encoding="utf-8")
    assert "group: myalpha-production-writer" in text, path
    assert "ref: main" in text, path
    assert "fetch-depth: 0" in text, path

daily=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
source=(ROOT/".github/workflows/source-intelligence-validation.yml").read_text(encoding="utf-8")
trend=(ROOT/".github/workflows/trend-pulse-backtest.yml").read_text(encoding="utf-8")
wxc=(ROOT/".github/workflows/wenxuecity.yml").read_text(encoding="utf-8")

for name,text in [("daily",daily),("source",source),("trend",trend),("wxc",wxc)]:
    assert "git pull --rebase origin main" in text, name
    assert "git push origin HEAD:main" in text, name

print("PASS production writers serialize and checkout latest main before generation")
