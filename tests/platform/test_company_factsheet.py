"""Research-quality read model: fact-sheet projection, source drilldowns, and
pre-save memo quality signals."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.services.company_factsheet import build_company_fact_sheet, data_quality_dashboard
from backend.workflows import memo


def _seed_company(stores, ticker: str = "SRC") -> dict:
    ent = stores.identity.ensure_entity(
        ticker, name="Source Corp", sector="Technology", industry="Software")
    source_id = stores.evidence.add_source(
        "filing", locator="https://www.sec.gov/Archives/src",
        title=f"{ticker} 10-K", publisher="SEC EDGAR")
    tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
    stores.financial.add_fact(
        ent["id"], tag, "2025-12-31", "annual", 100_000_000.0,
        unit="USD", taxonomy="us-gaap", source_id=source_id,
        accession="000000-src-25", filed_at="2026-02-15",
        mapped_concept="revenue", field_label="Revenue")
    stores.financial.add_observation(
        ent["id"], "revenue", "2025-12-31", "annual", 100_000_000.0,
        unit="USD", is_calculated=False,
        lineage={"source": "sec_companyfacts", "tag": tag,
                 "accession": "000000-src-25", "filed": "2026-02-15"})
    stores.financial.add_observation(
        ent["id"], "gross_margin", "2025-12-31", "annual", 0.62,
        is_calculated=True,
        lineage={"source": "sec_companyfacts", "formula": "gross_profit / revenue",
                 "inputs": {"revenue": 100_000_000.0, "gross_profit": 62_000_000.0}})
    stores.financial.add_observation(
        ent["id"], "eps", "2025-12-31", "annual", 5.0,
        is_calculated=False, lineage={"source": "test"})
    stores.financial.add_observation(
        ent["id"], "shares_outstanding", "2025-12-31", "annual", 10_000_000.0,
        is_calculated=False, lineage={"source": "test"})
    stores.bulk.upsert_prices([
        {"ticker": ticker, "date": "2026-06-12", "close": 50.0, "volume": 1_000_000},
    ])
    stores.bulk.add_filing(
        "10-K", "2026-02-15", accession="000000-src-25",
        ticker=ticker, entity_id=ent["id"], title=f"{ticker} 10-K")
    return ent


def test_metric_source_drilldown_links_observation_to_reported_fact(stores):
    ent = _seed_company(stores)
    drilldown = stores.financial.source_drilldown(ent["id"], "revenue")
    assert drilldown is not None
    assert drilldown["observation_id"].startswith("obs_")
    assert drilldown["facts"][0]["concept"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert drilldown["facts"][0]["accession"] == "000000-src-25"
    assert drilldown["sources"][0]["publisher"] == "SEC EDGAR"


def test_company_fact_sheet_exposes_quality_and_source_metadata(stores):
    _seed_company(stores)
    sheet = build_company_fact_sheet(stores, "SRC")
    assert sheet["snapshot"]["pe"] == 10.0
    assert sheet["source_metadata"]["latest_filing_accession"] == "000000-src-25"
    assert sheet["source_metadata"]["source_hash"]
    assert "gross_margin" in sheet["source_drilldowns"]
    assert "pe" in sheet["source_drilldowns"]  # read-time projection source
    assert sheet["data_quality"]["mapping_gaps"]["counts"] == {}


def test_company_financials_route_returns_projection_fields(stores):
    _seed_company(stores)
    with TestClient(create_app()) as client:
        resp = client.get("/api/company/SRC/financials")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_metadata"]["latest_filing_accession"] == "000000-src-25"
    assert body["sources"]["gross_margin"]["facts"][0]["accession"] == "000000-src-25"
    assert "data_quality" in body
    src_resp = client.get("/api/company/SRC/financials/source?metric=revenue")
    assert src_resp.status_code == 200, src_resp.text
    assert src_resp.json()["source"]["facts"][0]["accession"] == "000000-src-25"


def test_research_data_quality_dashboard_aggregates_issues(stores):
    _seed_company(stores)
    stores.financial.add_fact(
        stores.identity.resolve_ticker("SRC")["id"], "UsefulButUnknownTag",
        "2025-12-31", "annual", 12.0, unit="USD", taxonomy="us-gaap",
        field_label="Useful but unknown", mapping_status="unmapped")
    dash = data_quality_dashboard(stores)
    assert dash["counts"]["entities"] == 1
    assert dash["counts"]["unmapped_tags"] == 1
    assert dash["rows"][0]["ticker"] == "SRC"


def test_memo_quality_warnings_flag_low_figure_density():
    sections = {
        "business_quality": {
            "subsections": {
                "business_model": (
                    "The company has a strong position and a durable culture. "
                    "Customers like the product and management is thoughtful."
                ),
                "moat": (
                    "Revenue grew 12% to $5B over the retained period. "
                    "ROIC was 21% in FY2025, above the 10% hurdle."
                ),
            }
        }
    }
    warnings = memo._memo_quality_warnings(sections)
    assert warnings == [
        "business_quality.business_model: low figure density "
        "(0% of substantive sentences carry a number)"
    ]
