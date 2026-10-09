"""#133 item B: private stock ledger contract (static checks; no private data)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIG = (ROOT / "supabase/migrations/202610100002_stock_positions_private.sql").read_text(encoding="utf-8")
AUDIT = (ROOT / "supabase/tests/stock_positions_isolation.sql").read_text(encoding="utf-8")
JS = (ROOT / "docs/assets/stock-positions.js").read_text(encoding="utf-8")
WF = (ROOT / ".github/workflows/deploy-supabase.yml").read_text(encoding="utf-8")


def test_migration_owner_only():
    assert "enable row level security" in MIG.lower()
    assert re.search(r"revoke\s+all\s+on\s+(table\s+)?public\.stock_positions\s+from\s+anon", MIG, re.I)
    assert MIG.count("auth.uid()") >= 4
    assert "stock_positions_one_open_per_account_symbol" in MIG
    assert "STOCK_POSITION_ACCOUNT_NOT_OWNED" in MIG
    assert "broker_account_id bigint not null" in MIG


def test_audit_negative_probes():
    for marker in ("DUPLICATE_NOT_BLOCKED", "CROSS_ACCOUNT_NOT_BLOCKED", "RLS_LEAK", "RLS_UPDATE_LEAK", "PROBE_ROLLBACK"):
        assert marker in AUDIT, marker


def test_deploy_step_asserts():
    assert "202610100002_stock_positions_private.sql" in WF and "stock_positions_isolation.sql" in WF
    assert 'a.get("policies") == 4' in WF and 'a.get("cross_account_rows") == 0' in WF


def test_frontend_wired_and_private():
    for p in ("docs/index.html", "scripts/fetch_and_build.py"):
        s = (ROOT / p).read_text(encoding="utf-8")
        assert 'id="stockLedgerRoot"' in s and "assets/stock-positions.js" in s, p
    assert "console." not in JS
    assert "localStorage" not in JS  # private rows never cached in the browser
    assert "broker" not in re.sub(r"broker_account_id|broker_accounts|券商", "", JS).lower().replace("no broker link", "")


def test_no_trading_calls():
    assert not re.search(r"order|trade|ibkr", re.sub(r"order\(|不会下单|sort_order", "", JS), re.I)


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
    print("test_stock_positions_contract PASS")
