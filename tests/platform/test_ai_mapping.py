"""ADR-0015 governed AI-assisted XBRL tag mapping.

Covers the offline-safe scaffolding: unmapped-tag retention in the bulk
extract, the deterministic pre-accept validator, and the lazy proposal pass
(stub proposes nothing; a valid proposal is accepted + creates an observation;
an out-of-scope/hard-gate proposal is rejected with a retained reason and NO
observation). No network, no real provider.
"""

from __future__ import annotations

import asyncio

from backend.services.ingest import ai_mapping, sec_bulk


def _entry(end, val, accn="acc-1", start="2025-01-01"):
    return {"end": end, "val": val, "form": "10-K", "fy": 2025, "fp": "FY",
            "filed": "2026-02-20", "accn": accn, "start": start}


FACTS_WITH_UNMAPPED = {
    "cik": 42, "entityName": "Reit Co",
    "facts": {"us-gaap": {
        "Revenues": {"label": "Revenues",
                     "units": {"USD": [_entry("2025-12-31", 1000.0)]}},
        "PaymentsToAcquireRealEstate": {
            "label": "Payments to Acquire Real Estate",
            "units": {"USD": [_entry("2025-12-31", -500.0)]}},
    }},
}


def test_extract_retains_unmapped_tags(stores):
    ent = stores.identity.ensure_entity("REIT", name="Reit Co", cik="42")
    out = sec_bulk.extract_company_facts(stores, ent, FACTS_WITH_UNMAPPED)
    assert out["unmapped"] == 1
    unmapped = stores.financial.unmapped_facts(ent["id"])
    assert len(unmapped) == 1
    f = unmapped[0]
    assert f["concept"] == "PaymentsToAcquireRealEstate"
    assert f["field_label"] == "Payments to Acquire Real Estate"
    assert f["mapped_concept"] is None and f["mapping_status"] == "unmapped"
    # The mapped tag did NOT land in the unmapped corpus.
    assert all(u["concept"] != "Revenues" for u in unmapped)


def test_validate_mapping_governance():
    fact = {"unit": "USD", "value": 3.0}
    ok, reason = ai_mapping.validate_mapping("ffo_per_share", fact)
    assert ok, reason

    # Never map into a hard-gate metric (screening/IC decision authority).
    ok, reason = ai_mapping.validate_mapping("roe", fact)
    assert not ok and "hard-gate" in reason

    # Conflict with an already-accepted mapping.
    ok, reason = ai_mapping.validate_mapping(
        "ffo_per_share", fact, existing_metrics={"ffo_per_share"})
    assert not ok and "already" in reason

    # Value far outside the metric's typical range.
    ok, reason = ai_mapping.validate_mapping("ffo_per_share", {"unit": "USD", "value": 1e15})
    assert not ok and "typical range" in reason


def _seed_unmapped(stores, ticker="REIT"):
    ent = stores.identity.ensure_entity(ticker, name="Reit Co")
    stores.financial.add_fact(
        ent["id"], "FundsFromOperationsPerShare", "2025-12-31", "annual", 3.5,
        unit="USD", taxonomy="us-gaap", field_label="Funds From Operations Per Share",
        mapping_status="unmapped")
    return ent


def test_propose_mappings_offline_proposes_nothing(stores, offline_ai):
    ent = _seed_unmapped(stores)
    res = asyncio.run(ai_mapping.propose_mappings(
        stores, ent["id"], ["ffo_per_share"]))
    # The stub declines every proposal — governance-safe default.
    assert res["accepted"] == 0
    assert stores.financial.unmapped_facts(ent["id"])[0]["mapping_status"] == "unmapped"


def test_propose_mappings_accepts_valid(stores, offline_ai, monkeypatch):
    ent = _seed_unmapped(stores)

    async def fake(capability, system, user, shape, **kw):
        return {"target_metric": "ffo_per_share", "confidence": 0.92,
                "rationale": "FFO per share"}

    monkeypatch.setattr(offline_ai, "complete_json", fake)
    res = asyncio.run(ai_mapping.propose_mappings(stores, ent["id"], ["ffo_per_share"]))
    assert res["accepted"] == 1 and res["rejected"] == 0
    # Mapping recorded AND an observation created from the now-mapped fact.
    assert stores.financial.latest_value(ent["id"], "ffo_per_share") == 3.5
    assert stores.financial.unmapped_facts(ent["id"]) == []  # no longer unmapped


def test_propose_mappings_keeps_full_history_of_one_tag(stores, offline_ai, monkeypatch):
    ent = stores.identity.ensure_entity("REIT2", name="Reit Two")
    for end, val in (("2024-12-31", 3.0), ("2025-12-31", 3.5)):
        stores.financial.add_fact(
            ent["id"], "FundsFromOperationsPerShare", end, "annual", val, unit="USD",
            taxonomy="us-gaap", field_label="FFO per share", mapping_status="unmapped")

    async def fake(capability, system, user, shape, **kw):
        return {"target_metric": "ffo_per_share", "confidence": 0.9, "rationale": "FFO"}

    monkeypatch.setattr(offline_ai, "complete_json", fake)
    res = asyncio.run(ai_mapping.propose_mappings(stores, ent["id"], ["ffo_per_share"]))
    # Both periods of the SAME tag are accepted — not the first-only conflict bug.
    assert res["accepted"] == 2 and res["rejected"] == 0
    obs = stores.financial.observations(ent["id"], "ffo_per_share", period_type="annual")
    assert sorted(o["value"] for o in obs) == [3.0, 3.5]


def test_propose_mappings_rejects_competing_tag(stores, offline_ai, monkeypatch):
    ent = stores.identity.ensure_entity("REIT3", name="Reit Three")
    for tag in ("FundsFromOperationsPerShare", "AltFfoTag"):
        stores.financial.add_fact(
            ent["id"], tag, "2025-12-31", "annual", 3.5, unit="USD", taxonomy="us-gaap",
            field_label="FFO per share", mapping_status="unmapped")

    async def fake(capability, system, user, shape, **kw):
        return {"target_metric": "ffo_per_share", "confidence": 0.9, "rationale": "FFO"}

    monkeypatch.setattr(offline_ai, "complete_json", fake)
    res = asyncio.run(ai_mapping.propose_mappings(stores, ent["id"], ["ffo_per_share"]))
    # One tag wins the metric; the OTHER tag competing for it is rejected.
    assert res["accepted"] == 1 and res["rejected"] == 1


def test_propose_mappings_rejects_out_of_scope(stores, offline_ai, monkeypatch):
    ent = _seed_unmapped(stores)

    async def fake(capability, system, user, shape, **kw):
        return {"target_metric": "roe", "confidence": 0.9, "rationale": "guess"}

    monkeypatch.setattr(offline_ai, "complete_json", fake)
    res = asyncio.run(ai_mapping.propose_mappings(stores, ent["id"], ["ffo_per_share"]))
    assert res["accepted"] == 0 and res["rejected"] == 1
    # Rejected with a retained reason; NO observation created.
    assert stores.financial.latest_value(ent["id"], "roe") is None
    fact = stores.ws.query_one(
        "SELECT mapping_status, mapping_reason FROM reported_financial_facts "
        "WHERE entity_id = ?", (ent["id"],))
    assert fact["mapping_status"] == "rejected" and fact["mapping_reason"]
