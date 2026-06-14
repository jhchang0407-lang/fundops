"""Presentation-layer tests: human labels and unit-aware formatting
(backend/domain/labels.py), wiring summary text, screener snapshot display
fields, and Company Page milestone enrichment. Artifacts are built through the
real workflows in stub mode (conftest fixtures) — no network, no AI spend."""

from __future__ import annotations

import asyncio
import re

from backend.domain import labels, wiring
from backend.domain.artifact_schemas import MEMO_DECISIONS
from backend.domain.criteria import Criterion
from backend.services.portfolio_service import PortfolioService
from backend.workflows import pipeline, screener


def _run(coro):
    return asyncio.run(coro)


# --- pure helpers -----------------------------------------------------------------------


def test_metric_label_display_names():
    assert labels.metric_label("roic") == "ROIC"
    assert labels.metric_label("gross_margin") == "Gross Margin"
    assert labels.metric_label("fcf_yield") == "FCF Yield"
    assert labels.metric_label("debt_equity") == "Debt / Equity"
    assert labels.metric_label("returnOnInvestedCapital") == "ROIC"  # alias resolves
    assert labels.metric_label("some_custom_metric") == "Some Custom Metric"  # fallback
    assert labels.metric_label(None) == ""


def test_format_metric_value_units():
    # percent-typed metrics: stored 0-1 decimals rendered as %
    assert labels.format_metric_value("gross_margin", 0.46) == "46.0%"
    assert labels.format_metric_value("roic", 0.45) == "45.0%"
    assert labels.format_metric_value("revenue_growth", 0.123) == "12.3%"
    # float-typed but clearly decimal-ratio families
    assert labels.format_metric_value("fcf_yield", 0.06) == "6.0%"
    # percent-POINT metrics are never multiplied
    assert labels.format_metric_value("expected_return", 12.0) == "12.0%"
    # dollars: plain and compact
    assert labels.format_metric_value("price", 195.0) == "$195.00"
    assert labels.format_metric_value("market_cap", 2.1e12) == "$2.1T"
    assert labels.format_metric_value("market_cap", 5.0e10) == "$50.0B"
    assert labels.format_metric_value("revenue", 1.26e9) == "$1.3B"
    # multiples
    assert labels.format_metric_value("debt_equity", 1.5) == "1.5x"
    assert labels.format_metric_value("pe", 22.0) == "22.0x"
    # plain numbers and empties
    assert labels.format_metric_value("piotroski", 7) == "7"
    assert labels.format_metric_value("roic", None) == "—"
    assert labels.format_metric_value("sector", "Technology") == "Technology"


def test_describe_criterion_and_evaluation():
    c = Criterion("screen.roic_min", "screen", "quality", "test",
                  metric="roic", operator=">=", value=0.15)
    assert labels.describe_criterion(c) == "ROIC ≥ 15%"
    assert labels.describe_evaluation(c, 0.45) == "ROIC 45.0% (required ≥ 15%)"
    assert labels.describe_evaluation(c, 0.45, compact=True) == "ROIC 45.0% (≥ 15%)"
    assert labels.describe_evaluation(c, None) == "ROIC no data (required ≥ 15%)"
    # dicts (stored criterion rows) work the same as objects
    assert labels.describe_criterion(
        {"metric": "gross_margin", "operator": ">=", "value": 0.40}) == "Gross Margin ≥ 40%"
    # between / in operators
    band = Criterion("screen.pe_band", "screen", "", "test",
                     metric="pe", operator="between", value=[10, 25])
    assert labels.describe_criterion(band) == "P/E between 10x and 25x"
    sectors = Criterion("screen.sector", "screen", "", "test",
                        metric="sector", operator="in", value=["Technology", "Healthcare"])
    assert labels.describe_criterion(sectors) == "Sector one of Technology, Healthcare"


def test_evidence_rows_humanize_legacy_payloads():
    # Rows persisted before the display fields existed are humanized on read.
    legacy = {"criterion": "screen.roic_min", "metric": "roic",
              "threshold": ">= 0.1", "observed": 0.25}
    assert labels.describe_evidence_row(legacy) == "ROIC 25.0% (≥ 10%)"
    assert labels.evidence_key_number(legacy) == {"label": "ROIC", "value": "25.0% (≥ 10%)"}


def test_screener_summary_text():
    rows = [{"label": "ROIC", "observed_display": "45.0%", "threshold_display": "≥ 15%",
             "metric": "roic"},
            {"label": "Gross Margin", "observed_display": "46.0%",
             "threshold_display": "≥ 40%", "metric": "gross_margin"}]
    comps = [{"metric": "fcf_yield", "label": "FCF Yield", "contribution": 0.5,
              "percentile": 90.0}]
    text = labels.screener_summary(rows, rank=1, total=5, components=comps)
    assert text == ("Passed 2 of 2 requirements — ROIC 45.0% (≥ 15%), "
                    "Gross Margin 46.0% (≥ 40%). Ranked #1 of 5 on FCF Yield.")
    assert labels.screener_fail_summary(
        [{"metric": "roic", "threshold": ">= 0.1", "observed": 0.05}]
    ) == "Missed 1 requirement — ROIC 5.0% (≥ 10%)."


# --- wiring summary text ----------------------------------------------------------------


def test_wiring_summaries_use_product_language():
    crits = [
        Criterion("screen.roic_min", "screen", "q", "t",
                  metric="roic", operator=">=", value=0.10),
        Criterion("rank.fcf_yield", "rank", "c", "t",
                  metric="fcf_yield", operator=">", value=0.0, weight=1.0),
        Criterion("ic.expected_return_min", "ic_hurdle", "m", "t",
                  metric="expected_return", operator=">=", value=8.0),
    ]
    proj = wiring.project_settings(crits, north_star="quality", universe={"name": "Test"})
    s = proj["screener"]["summary"]
    assert "ROIC ≥ 10%" in s
    assert "Ranked by FCF Yield" in s
    assert "roic" not in s and "screen.roic_min" not in s and ">=" not in s
    ic = proj["ic_review"]["summary"]
    assert "Expected Return ≥ 8%" in ic
    assert "expected_return" not in ic and ">=" not in ic


# --- screener snapshot artifact ---------------------------------------------------------


def test_screener_snapshot_display_fields(stores, fake_market, constitution):
    rid = _run(screener.run_screener(stores))
    snaps = [a for a in stores.artifacts.for_run(rid) if a["kind"] == "screener_snapshot"]
    aaa = next(a for a in snaps if a["ticker"] == "AAA")
    body = aaa["payload"]["body"]

    # Reader regression: component breakdown must be on the snapshot payload.
    assert body["ranking_components"]
    assert [c["label"] for c in body["ranking_components"]] == ["FCF Yield",
                                                                "Revenue Growth (1Y)"]

    ev = {e["criterion"]: e for e in body["pass_evidence"]}
    roic = ev["screen.roic_min"]
    # Raw audit fields are kept...
    assert roic["metric"] == "roic"
    assert roic["threshold"] == ">= 0.1"
    assert roic["observed"] == 0.25
    # ...and display fields are added for the product surface.
    assert roic["label"] == "ROIC"
    assert roic["rule"] == "ROIC ≥ 10%"
    assert roic["threshold_display"] == "≥ 10%"
    assert roic["observed_display"] == "25.0%"

    assert all(k["display"] for k in body["key_financials"])
    fin = {k["metric"]: k["display"] for k in body["key_financials"]}
    assert fin["fcf_yield"] == "6.0%"

    assert "strongest on FCF Yield" in body["ranking_explanation"]
    assert "fcf_yield" not in body["ranking_explanation"]

    # Milestone-facing summary/rendered_md is human, never raw ids/decimals.
    md = aaa["rendered_md"]
    assert md == body["summary"]
    assert md == ("Passed 2 of 2 requirements — ROIC 25.0% (≥ 10%), "
                  "Gross Margin 55.0% (≥ 30%). Ranked #1 of 4 on FCF Yield.")
    assert "screen.roic_min" not in md


# --- company page milestones ------------------------------------------------------------


def test_company_milestones_human_titles_and_detail(stores, fake_market, constitution):
    from backend.api.routes.company import company_page

    _run(pipeline.run_pipeline(stores))
    PortfolioService(stores).add_lot("AAA", 50, 150.0, "2026-03-02")

    page = _run(company_page("AAA"))
    lanes = {ln["lane"]: ln["milestones"] for ln in page["lanes"]}

    scr = lanes["screener"][0]
    assert scr["title"] == "Screened — rank #1 of 4"
    assert scr["status"] == "selected"          # status chip, never duplicated in title
    assert "selected" not in scr["title"]
    assert "screen." not in scr["summary"] and "roic_min" not in scr["summary"]
    assert "ROIC 25.0% (≥ 10%)" in scr["summary"]
    kn = {k["label"]: k["value"] for k in scr["detail"]["key_numbers"]}
    assert kn["Rank"] == "#1 of 4"
    assert kn["ROIC"] == "25.0% (≥ 10%)"
    assert kn["Gross Margin"] == "55.0% (≥ 30%)"
    assert "Screen score" in kn

    th = lanes["thesis"][0]
    assert th["title"] == "Thesis — +18.0% expected"
    assert th["status"] == "completed"
    assert th["summary"]
    tkn = {k["label"]: k["value"] for k in th["detail"]["key_numbers"]}
    assert tkn["Price"] == "$100.00"
    assert tkn["Expected return"] == "+18.0%"
    assert tkn["Fair value"].startswith("$")  # exact value owned by the thesis stub
    assert len(tkn) >= 4  # top return components included

    ic = lanes["ic_review"][0]
    assert re.fullmatch(r"IC Review — \d+/100", ic["title"])
    assert ic["status"] in ("pass", "fail")
    assert "pass" not in ic["title"].lower()    # no status duplication
    assert ic["summary"]
    ikn = {k["label"]: k["value"] for k in ic["detail"]["key_numbers"]}
    assert "vs cutoff 70" in ikn["Gate score"]
    for label in ("Conviction", "Constitution fit", "Data quality"):
        assert ikn[label].endswith("/100")
    assert re.fullmatch(r"\d+ met, \d+ missed", ikn["Hurdles"])

    memo = lanes["memo"][0]
    assert memo["title"] == "Investment Memo"
    assert memo["status"] in MEMO_DECISIONS
    assert memo["status"] not in memo["title"].lower()
    assert memo["summary"].startswith("Decision:")
    mkn = {k["label"]: k["value"] for k in memo["detail"]["key_numbers"]}
    assert "Decision" in mkn and "Fair value" in mkn
    assert mkn["Fair value"].startswith("$")

    pf = lanes["portfolio"][0]
    assert pf["title"] == "Bought 50 @ $150.00"
    pkn = {k["label"]: k["value"] for k in pf["detail"]["key_numbers"]}
    assert pkn == {"Shares": "50", "Price": "$150.00", "Total value": "$7,500.00"}

    # No raw criterion/metric ids anywhere in milestone titles.
    for milestones in lanes.values():
        for m in milestones:
            assert "screen." not in m["title"] and "_" not in m["title"]
