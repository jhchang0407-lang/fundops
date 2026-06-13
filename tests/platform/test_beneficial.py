"""13D/G beneficial-ownership ingestion (ADR-0061): index parsing of
multi-token schedule forms, tolerant XML parsing, sync orchestration,
largest-holders view, and the company ownership endpoint."""

from __future__ import annotations

import pytest

from backend.services.ingest import beneficial, sec_index

SCHEDULE_XML = """<?xml version="1.0"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13d">
  <coverPage>
    <issuerName>Alpha Corp</issuerName>
  </coverPage>
  <reportingPersonInfo>
    <reportingPersonName>Granite Capital Partners LP</reportingPersonName>
    <aggregateAmountOwned>1,250,000</aggregateAmountOwned>
    <percentOfClass>7.4%</percentOfClass>
  </reportingPersonInfo>
  <reportingPersonInfo>
    <reportingPersonName>Granite Capital GP LLC</reportingPersonName>
    <aggregateAmountOwned>1,250,000</aggregateAmountOwned>
    <percentOfClass>7.4</percentOfClass>
  </reportingPersonInfo>
</edgarSubmission>
"""

INDEX_TEXT = """Form Type   Company Name   CIK   Date Filed   File Name
----------------------------------------------------------------------
SC 13D      ALPHA CORP     1111  20260610     edgar/data/1111/0000900000-26-000123.txt
SC 13G/A    ALPHA CORP     1111  20260610     edgar/data/1111/0000900000-26-000124.txt
S-3         ALPHA CORP     1111  20260610     edgar/data/1111/0000900000-26-000125.txt
10-Q        ALPHA CORP     1111  20260610     edgar/data/1111/0000900000-26-000126.txt
DEF 14A     ALPHA CORP     1111  20260610     edgar/data/1111/0000900000-26-000127.txt
"""


def test_parse_schedule_xml_extracts_persons():
    persons = beneficial.parse_schedule_xml(SCHEDULE_XML)
    assert len(persons) == 2
    assert persons[0]["owner_name"] == "Granite Capital Partners LP"
    assert persons[0]["shares"] == 1_250_000
    assert persons[0]["percent"] == 7.4
    assert beneficial.parse_schedule_xml("not xml at all") == []


def test_form_index_parses_multi_token_schedule_forms():
    rows = sec_index.parse_form_index(INDEX_TEXT)
    forms = {r["form"] for r in rows}
    assert forms == {"SC 13D", "SC 13G/A", "S-3", "10-Q"}  # DEF 14A not kept
    sc13d = next(r for r in rows if r["form"] == "SC 13D")
    assert sc13d["company"] == "ALPHA CORP"
    assert sc13d["accession"] == "0000900000-26-000123"


@pytest.fixture
def seeded_filings(stores):
    stores.identity.ensure_entity("ALPH", name="Alpha Corp")
    for form, acc in (("SC 13D", "0000900000-26-000123"),
                      ("SC 13G/A", "0000900000-26-000124"),
                      ("S-3", "0000900000-26-000125")):
        stores.bulk.add_filing(form, "2026-06-10", accession=acc,
                               cik="1111", ticker="ALPH")
    return stores


@pytest.mark.asyncio
async def test_sync_beneficial_records_holders_and_marks_processed(seeded_filings, monkeypatch):
    stores = seeded_filings
    monkeypatch.setattr(beneficial, "_fetch_primary_xml", lambda cik, acc: SCHEDULE_XML)
    monkeypatch.setattr(beneficial, "FETCH_DELAY_S", 0)
    out = await beneficial.sync_beneficial(stores)
    assert out["parsed"] == 2  # both schedules; S-3 is not a beneficial form
    holders = beneficial.largest_holders(stores, "ALPH")
    assert holders and holders[0]["percent"] == 7.4
    # Latest-per-owner dedupe: re-running on processed filings adds nothing.
    again = await beneficial.sync_beneficial(stores)
    assert again == {"parsed": 0, "skipped": 0}
    assert len(beneficial.largest_holders(stores, "ALPH")) == 2
    # S-3 remains retained as an event record, untouched by beneficial sync.
    assert stores.bulk.filings_for("ALPH", forms=["S-3"])


@pytest.mark.asyncio
async def test_fetch_failure_leaves_filing_unprocessed(seeded_filings, monkeypatch):
    stores = seeded_filings

    def boom(cik, acc):
        raise OSError("offline")

    monkeypatch.setattr(beneficial, "_fetch_primary_xml", boom)
    monkeypatch.setattr(beneficial, "FETCH_DELAY_S", 0)
    out = await beneficial.sync_beneficial(stores)
    assert out["parsed"] == 0
    assert len(stores.bulk.unprocessed_filings(forms=beneficial.BENEFICIAL_FORMS)) == 2


def test_ownership_endpoint_includes_largest_holders(seeded_filings):
    from fastapi.testclient import TestClient
    from backend.api import create_app

    stores = seeded_filings
    stores.bulk.add_ownership(
        "ALPH", "beneficial_ownership", "2026-06-10", "Granite Capital Partners LP",
        shares=1_250_000, payload={"percent": 7.4, "form": "SC 13D"},
    )
    client = TestClient(create_app())
    body = client.get("/api/company/ALPH/ownership").json()
    assert body["largest_holders"][0]["owner_name"] == "Granite Capital Partners LP"
    assert body["largest_holders"][0]["percent"] == 7.4
    assert "empty_reason" not in body
