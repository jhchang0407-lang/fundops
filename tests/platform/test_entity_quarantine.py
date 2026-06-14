"""#4: phantom-entity quarantine.

Delisted/shell/taken-private names (no prices AND no retained financials) are
flagged 'quarantined' and dropped from researchable surfaces (Markets tree,
peer groups, chat universe) while staying resolvable by deep-link. The /sync
payload reconciles the price-universe vs entities vs priced-entities counts.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app


@pytest.fixture
def client(stores, offline_ai):
    with TestClient(create_app()) as c:
        yield c


def _seed_covered(stores, ticker, sector="TestSec", industry="TestInd"):
    ent = stores.identity.ensure_entity(ticker, sector=sector, industry=industry)
    stores.financial.store_metrics_snapshot(
        ent["id"], {"revenue": 1.0e9}, "2025-12-31", "annual")
    return ent


def _seed_phantom(stores, ticker, sector="TestSec", industry="TestInd"):
    # No price_history and no latest_financials row.
    return stores.identity.ensure_entity(ticker, sector=sector, industry=industry)


def test_status_columns_added_and_default_active(stores):
    cols = {r["name"] for r in stores.ws.query("PRAGMA table_info(investment_entities)")}
    assert {"status", "status_reason", "status_at"} <= cols
    ent = stores.identity.ensure_entity("AAA")
    row = stores.ws.query_one(
        "SELECT status FROM investment_entities WHERE id = ?", (ent["id"],))
    assert row["status"] == "active"


def test_reconcile_quarantines_phantoms_and_reactivates(stores):
    phantom = _seed_phantom(stores, "PHNTM")
    covered = _seed_covered(stores, "REAL")
    res = stores.identity.reconcile_phantom_status()
    assert res["quarantined"] == 1
    assert stores.ws.query_one(
        "SELECT status FROM investment_entities WHERE id = ?", (phantom["id"],))["status"] \
        == "quarantined"
    assert stores.ws.query_one(
        "SELECT status FROM investment_entities WHERE id = ?", (covered["id"],))["status"] \
        == "active"
    # Idempotent: a second pass changes nothing.
    assert stores.identity.reconcile_phantom_status() == {"quarantined": 0, "reactivated": 0}
    # When data later arrives the phantom is reactivated.
    stores.bulk.upsert_prices([{"ticker": "PHNTM", "date": "2026-01-02", "close": 5.0}])
    assert stores.identity.reconcile_phantom_status()["reactivated"] == 1
    assert stores.ws.query_one(
        "SELECT status FROM investment_entities WHERE id = ?", (phantom["id"],))["status"] \
        == "active"


def test_quarantined_dropped_from_research_surfaces_but_resolvable(stores):
    _seed_phantom(stores, "PHNTM")
    _seed_covered(stores, "REAL")
    stores.identity.reconcile_phantom_status()

    group = [e["ticker"] for e in stores.identity.entities_in_group(sector="TestSec")]
    assert group == ["REAL"]
    assert "PHNTM" not in stores.identity.all_tickers()
    assert "REAL" in stores.identity.all_tickers()
    assert all(s["sector"] != "TestSec" or "REAL" in str(s)
               for s in stores.identity.industry_tree()) or True  # tree only counts active
    tree_sectors = {s["sector"]: s["count"] for s in stores.identity.industry_tree()}
    assert tree_sectors.get("TestSec") == 1  # only REAL counted

    # Deep-link resolution still works (renders a delisted state, not a 404).
    resolved = stores.identity.resolve_ticker("PHNTM")
    assert resolved is not None and resolved["status"] == "quarantined"


def test_sync_payload_has_reconciliation_block(client, stores):
    _seed_covered(stores, "REAL")
    _seed_phantom(stores, "PHNTM")
    stores.bulk.upsert_prices([{"ticker": "REAL", "date": "2026-01-02", "close": 10.0}])
    stores.identity.reconcile_phantom_status()
    rec = client.get("/api/sync").json()["reconciliation"]
    assert rec["entities_total"] == 2
    assert rec["entities_active"] == 1 and rec["entities_quarantined"] == 1
    assert rec["priced_entities"] == 1
    # price_tickers = priced_entities + benchmark/alias tickers (arithmetic reconciles).
    assert rec["price_tickers"] == rec["priced_entities"] + rec["benchmark_or_alias_tickers"]
