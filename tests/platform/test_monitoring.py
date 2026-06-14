"""Offline/deterministic tests for the monitoring + portfolio + dashboard +
learning layer: thesis health plans/refreshes, portfolio service coverage,
dashboard projections, and outcome evaluation classification."""

from __future__ import annotations

import asyncio
import itertools
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from backend.core.workspace import now_iso
from backend.domain import thesis_health as thesis_health_domain
from backend.services import dashboard_service
from backend.services.portfolio_service import PortfolioService, process_coverage_queue
from backend.workflows import learning, thesis_health


# --- helpers ---------------------------------------------------------------------------

def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def _set(stores, sql: str, params: tuple) -> None:
    with stores.ws.transaction() as conn:
        conn.execute(sql, params)


def _age_plan(stores, plan_id: str, days: int) -> None:
    _set(stores, "UPDATE thesis_health_plans SET created_at = ? WHERE id = ?",
         (_ago(days), plan_id))


def _age_refreshes(stores, ticker: str, days: int) -> None:
    _set(stores, "UPDATE thesis_health_refreshes SET ran_at = ? WHERE ticker = ?",
         (_ago(days), ticker.upper()))


def _seed_obs(stores, ticker: str, metric: str, period_end: str, value: float,
              period_type: str = "quarterly") -> str:
    ent = stores.identity.ensure_entity(ticker)
    stores.financial.add_observation(ent["id"], metric, period_end, period_type, value)
    return ent["id"]


_ACCESSION_SEQ = itertools.count(1)


def _seed_filing(stores, ticker: str, form: str = "10-Q", filed_at: str | None = None,
                 processed: bool = False) -> str:
    fid = stores.bulk.add_filing(form, filed_at or now_iso(), ticker=ticker,
                                 accession=f"{ticker}-{next(_ACCESSION_SEQ):06d}")
    if processed and fid:
        stores.bulk.mark_filings_processed([fid])
    return fid


def _memo(stores, ticker: str, items: list[dict], decision: str = "attractive") -> str:
    ent = stores.identity.ensure_entity(ticker)
    payload = {
        "kind": "investment_memo", "schema_version": "1.0", "generated_at": now_iso(),
        "body": {
            "monitoring_plan_items": items,
            "sections": {"decision_summary": {"fields": {"decision": decision}}},
        },
    }
    return stores.artifacts.save_artifact("investment_memo", payload,
                                          ticker=ticker, entity_id=ent["id"])


def _quant(metric: str, comparator: str, threshold: float, item_type: str = "assumption",
           lookback: str = "latest", **kw) -> dict:
    return {"item_type": item_type, "title": f"{metric} {comparator} {threshold}",
            "tracking_mode": "quantitative", "metric": metric, "comparator": comparator,
            "threshold": threshold, "cadence": "quarterly", "lookback": lookback,
            "why_matters": "core thesis driver", **kw}


def _open_items(stores, section: str | None = None) -> list[dict]:
    return stores.dashboard.open_items(section)


# --- 1. ledger flows through PortfolioService incl. coverage queueing --------------------

def test_portfolio_ledger_and_coverage_queueing(stores):
    svc = PortfolioService(stores)
    res = svc.add_lot("aapl", 10, 100.0, "2026-01-05")
    assert res["lot_id"].startswith("lot_")
    assert res["coverage_state"] == "queued"
    assert stores.portfolio.holding("AAPL")["coverage_state"] == "queued"
    coverage = [w for w in stores.ops.queue_state(limit=200) if w["kind"] == "coverage_memo"]
    assert len(coverage) == 1 and coverage[0]["payload"]["ticker"] == "AAPL"

    # Second lot save re-checks coverage but never duplicates queued work.
    svc.add_lot("AAPL", 5, 110.0, "2026-02-01")
    coverage = [w for w in stores.ops.queue_state(limit=200) if w["kind"] == "coverage_memo"]
    assert len(coverage) == 1

    stores.portfolio.mark_price("AAPL", 120.0)
    stores.portfolio.rebuild_holdings()
    holding = stores.portfolio.holding("AAPL")
    assert holding["shares"] == 15
    assert holding["market_value"] == pytest.approx(15 * 120.0)

    # FIFO sale, partial exit: no decision-register entry yet.
    sale = svc.record_sale("AAPL", 10, 130.0, "2026-03-01")
    assert sale["realized_pnl"] == pytest.approx(10 * 30.0)
    assert not stores.learning.decisions()

    # Full exit: the sale row is history; exit lands in the decision register.
    sale2 = svc.record_sale("AAPL", 5, 90.0, "2026-03-02")
    assert sale2["realized_pnl"] == pytest.approx(5 * -20.0)
    assert stores.portfolio.holding("AAPL") is None
    decisions = stores.learning.decisions()
    assert any(d["kind"] == "portfolio_exit" and "AAPL" in d["title"] for d in decisions)
    assert len(stores.portfolio.lots("AAPL")) == 2
    assert len(stores.portfolio.sales("AAPL")) == 2


def test_coverage_queue_processing(stores, monkeypatch):
    svc = PortfolioService(stores)
    svc.add_lot("TSLA", 5, 100.0, "2026-01-02")

    # Failing memo workflow → terminal failed work + attention item.
    failing = types.ModuleType("backend.workflows.memo")

    async def boom(stores_, ticker=None, trigger="user", provenance=None):
        raise RuntimeError("memo generation exploded")

    failing.run_memo = boom
    monkeypatch.setitem(sys.modules, "backend.workflows.memo", failing)
    results = asyncio.run(process_coverage_queue(stores))
    assert results and all(r["state"] == "failed" for r in results)
    assert stores.portfolio.holding("TSLA")["coverage_state"] == "failed"
    failures = [i for i in _open_items(stores, "needs_attention")
                if i["source_type"] == "coverage_failure"]
    assert len(failures) == 1 and failures[0]["ticker"] == "TSLA"

    # Re-queue after failure, then succeed: covered state + auto-resolved item.
    _seed_obs(stores, "TSLA", "revenue", "2026-03-31", 1500.0)
    assert svc.ensure_coverage_for("TSLA") == "queued"

    succeeding = types.ModuleType("backend.workflows.memo")

    async def ok(stores_, ticker=None, trigger="user", provenance=None):
        memo_id = _memo(stores_, ticker, [_quant("revenue", ">=", 1000.0)])
        thesis_health.create_plan_for_memo(stores_, memo_id)
        return "run_fake"

    succeeding.run_memo = ok
    monkeypatch.setitem(sys.modules, "backend.workflows.memo", succeeding)
    results = asyncio.run(process_coverage_queue(stores))
    assert results == [{"ticker": "TSLA", "state": "covered"}]
    holding = stores.portfolio.holding("TSLA")
    assert holding["coverage_state"] == "covered"
    assert holding["coverage_memo_artifact_id"]
    assert not [i for i in _open_items(stores, "needs_attention")
                if i["source_type"] == "coverage_failure"]

    # Fresh thesis-health-ready memo means later saves are covered immediately.
    assert svc.add_lot("TSLA", 1, 100.0, "2026-02-01")["coverage_state"] == "covered"


# --- 2. plan creation from a memo artifact ------------------------------------------------

def test_create_plan_for_memo_validates_and_baselines(stores):
    _seed_obs(stores, "AAPL", "gross_margin", "2026-03-31", 0.45)
    _seed_obs(stores, "AAPL", "revenue", "2026-03-31", 1100.0)
    items = [
        _quant("gross_margin", ">=", 0.40, item_type="kill_criterion"),
        _quant("revenue", ">=", 1000.0),
        {"item_type": "risk", "title": "Brand strength holds", "tracking_mode": "qualitative",
         "why_matters": "qualitative evidence review"},
        _quant("not_a_real_metric", ">=", 1.0),  # invalid → downgraded, non-status-driving
    ]
    memo_id = _memo(stores, "AAPL", items)
    plan_id = thesis_health.create_plan_for_memo(stores, memo_id)
    assert plan_id

    stored = thesis_health.plan_items(stores, plan_id)
    assert len(stored) == 4
    by_title = {i["title"]: i for i in stored}
    gm = by_title["gross_margin >= 0.4"]
    assert gm["status"] == "intact" and gm["current_value"] == pytest.approx(0.45)
    rev = by_title["revenue >= 1000.0"]
    assert rev["status"] == "intact" and rev["current_value"] == pytest.approx(1100.0)
    qual = by_title["Brand strength holds"]
    assert qual["tracking_mode"] == "qualitative" and qual["status"] == "unknown"
    assert qual["last_checked_at"] is None
    bad = by_title["not_a_real_metric >= 1.0"]
    assert bad["tracking_mode"] == "unsupported"  # invalid item downgraded

    checks = stores.ws.query("SELECT * FROM thesis_health_checks")
    assert len(checks) == 2 and all(c["kind"] == "baseline" for c in checks)
    assert thesis_health.plan_ready(stores, plan_id)

    view = thesis_health.thesis_health_view(stores, "AAPL")
    assert view["summary_label"] == "Intact"
    assert len(view["items"]) == 3  # unsupported items hidden
    assert view["active_source"]["memo_artifact_id"] == memo_id
    assert "empty_reason" not in view

    # No memo at all → explanatory empty state.
    empty = thesis_health.thesis_health_view(stores, "ZZZZ")
    assert empty["summary_label"] is None
    assert empty["empty_reason"].startswith("Thesis health begins after a Completed Memo")

    # A new memo freezes the prior plan; older items stay historical.
    memo2 = _memo(stores, "AAPL", [_quant("revenue", ">=", 900.0)])
    plan2 = thesis_health.create_plan_for_memo(stores, memo2)
    assert plan2 and plan2 != plan_id
    assert thesis_health.active_plan(stores, "AAPL")["id"] == plan2
    old = stores.ws.query_one("SELECT active FROM thesis_health_plans WHERE id = ?", (plan_id,))
    assert old["active"] == 0

    # No monitoring items → no plan.
    assert thesis_health.create_plan_for_memo(stores, _memo(stores, "MSFT", [])) is None
    no_checks = thesis_health.thesis_health_view(stores, "MSFT")
    assert no_checks["empty_reason"] == "No thesis health checks yet."


# --- 2b. breach-framed comparators normalize to the healthy band (KO false-positive) -------

def _watch(item_type: str, title: str, metric: str, comparator: str, threshold: float,
           **kw) -> dict:
    """A quantitative watch item with an explicit (natural-language) title — unlike
    _quant, the title carries the breach framing the normalizer keys off."""
    return {"item_type": item_type, "title": title, "tracking_mode": "quantitative",
            "metric": metric, "comparator": comparator, "threshold": threshold,
            "cadence": "quarterly", "lookback": "latest", "confirmation_periods": 2,
            "immediate_kill": False, "why_matters": "core thesis driver", **kw}


def test_breach_framed_kill_criteria_baseline_intact_not_broken(stores):
    """KO repro: a memo phrases kill criteria/risks as the breach event and the
    model stored the comparator in that breach direction ('<' 0.0 for 'turns
    negative'). Current values are healthy, so the items MUST baseline intact —
    not broken — once the comparator is normalized to the healthy band."""
    _seed_obs(stores, "KO", "revenue_growth", "2026-03-31", 0.04)
    _seed_obs(stores, "KO", "debt_equity", "2026-03-31", 1.6)
    items = [
        # Stored in the BREACH direction, exactly as the bug produced them.
        _watch("kill_criterion", "Revenue growth turns negative", "revenue_growth",
               "<", 0.0),
        _watch("risk", "Debt/equity rises materially above 1.6x", "debt_equity",
               ">", 2.0),
    ]
    plan_id = thesis_health.create_plan_for_memo(stores, _memo(stores, "KO", items))
    stored = {i["title"]: i for i in thesis_health.plan_items(stores, plan_id)}

    rg = stored["Revenue growth turns negative"]
    assert rg["comparator"] == ">="                       # flipped to healthy band
    assert rg["status"] == "intact"                       # 0.04 >= 0.0
    assert rg["current_value"] == pytest.approx(0.04)
    de = stored["Debt/equity rises materially above 1.6x"]
    assert de["comparator"] == "<="                       # flipped to healthy band
    assert de["status"] == "intact"                       # 1.6 <= 2.0
    assert thesis_health.summary_for(stores, "KO") == "Intact"


def test_validate_plan_normalizes_only_inverted_breach_comparators():
    """The deterministic normalizer flips comparators stored in the breach
    direction, leaves correctly-framed items (and non-risk framings) untouched,
    and records a normalization note for each flip."""
    rg, de, gm_ok, gm_risk_ok = thesis_health_domain.validate_plan([
        _watch("kill_criterion", "Revenue growth turns negative", "revenue_growth",
               "<", 0.0, cadence="annual", lookback="yoy"),
        _watch("risk", "Debt/equity rises above 1.6x", "debt_equity", ">", 2.0),
        # Correctly framed (and not a risk/kill) → never auto-flipped.
        _watch("assumption", "Gross margin holds above 40%", "gross_margin", ">=", 0.40),
        # A risk already expressing the healthy band → confirmed, not flipped.
        _watch("risk", "Gross margin falls below 30%", "gross_margin", ">=", 0.30),
    ])
    assert (rg.comparator, rg.tracking_mode) == (">=", "quantitative") and rg.normalizations
    assert (de.comparator, de.tracking_mode) == ("<=", "quantitative") and de.normalizations
    assert gm_ok.comparator == ">=" and not gm_ok.normalizations
    assert gm_risk_ok.comparator == ">=" and not gm_risk_ok.normalizations


def test_repair_inverted_comparators_heals_legacy_plan(stores):
    """Plans persisted before normalization landed are healed in place: the stored
    comparator is flipped and the item re-baselined so its status reflects reality."""
    _seed_obs(stores, "KO", "revenue_growth", "2026-03-31", 0.04)
    plan_id = thesis_health.create_plan_for_memo(stores, _memo(stores, "KO", [
        _watch("kill_criterion", "Revenue growth turns negative", "revenue_growth",
               "<", 0.0)]))
    item = thesis_health.plan_items(stores, plan_id)[0]
    # Simulate legacy pre-fix state: comparator left in the breach direction, the
    # item wrongly recorded as broken off a healthy value.
    _set(stores, "UPDATE thesis_watch_items SET comparator = '<', status = 'broken', "
                 "consecutive_breaches = 2, current_value = 0.04 WHERE id = ?", (item["id"],))
    assert thesis_health.summary_for(stores, "KO") == "Broken"

    fixed = thesis_health.repair_inverted_comparators(stores)
    assert len(fixed) == 1
    assert (fixed[0]["ticker"], fixed[0]["from"], fixed[0]["to"]) == ("KO", "<", ">=")
    healed = thesis_health.plan_items(stores, plan_id)[0]
    assert healed["comparator"] == ">=" and healed["status"] == "intact"
    assert healed["consecutive_breaches"] == 0
    assert thesis_health.summary_for(stores, "KO") == "Intact"
    # Idempotent: the corrected comparator is no longer detected as inverted.
    assert thesis_health.repair_inverted_comparators(stores) == []


# --- 3. refresh lifecycle: watch → broken, gaps, material break + auto-resolve -------------

def test_refresh_watch_broken_material_break_and_recovery(stores):
    _seed_obs(stores, "MSFT", "revenue", "2025-12-31", 1100.0)
    memo_id = _memo(stores, "MSFT", [_quant("revenue", ">=", 1000.0,
                                            item_type="kill_criterion")])
    plan_id = thesis_health.create_plan_for_memo(stores, memo_id)
    item = thesis_health.plan_items(stores, plan_id)[0]
    assert item["status"] == "intact"
    assert thesis_health.due_tickers(stores) == ["MSFT"]  # never refreshed → due

    # New quarterly observation since the baseline → full recalc → watch (1/2).
    _age_plan(stores, plan_id, days=10)
    _seed_obs(stores, "MSFT", "revenue", "2026-03-31", 900.0)
    res = thesis_health.refresh_all(stores)
    assert res == [{"ticker": "MSFT", "metadata_only": False, "summary_label": "Watching"}]
    item = thesis_health.plan_items(stores, plan_id)[0]
    assert item["status"] == "watch" and item["consecutive_breaches"] == 1
    assert not [i for i in _open_items(stores, "needs_attention")
                if i["source_type"] == "thesis_break"]

    # Second consecutive breach confirms broken → material thesis break (high).
    # A new 10-Q in the bulk filings index (ADR-0059) makes MSFT due and
    # gates the full recalculation.
    _age_refreshes(stores, "MSFT", days=5)
    _seed_obs(stores, "MSFT", "revenue", "2026-06-30", 800.0)
    fid = _seed_filing(stores, "MSFT", filed_at=_ago(4))
    res = thesis_health.refresh_all(stores)
    assert res[0]["metadata_only"] is False and res[0]["summary_label"] == "Broken"
    item = thesis_health.plan_items(stores, plan_id)[0]
    assert item["status"] == "broken" and item["consecutive_breaches"] == 2
    breaks = [i for i in _open_items(stores, "needs_attention")
              if i["source_type"] == "thesis_break"]
    assert len(breaks) == 1
    assert breaks[0]["severity"] == "high"
    assert "(not held)" in breaks[0]["title"]

    # The unprocessed filing keeps MSFT due, but nothing filed after the full
    # refresh → metadata-only; statuses untouched.
    res = thesis_health.refresh_all(stores)
    assert res[0]["metadata_only"] is True and res[0]["summary_label"] == "Broken"
    assert thesis_health.plan_items(stores, plan_id)[0]["status"] == "broken"
    stores.bulk.mark_filings_processed([fid])

    # Recovery: healthy quarter + new filing → intact; break item auto-resolves.
    _age_refreshes(stores, "MSFT", days=5)
    _seed_obs(stores, "MSFT", "revenue", "2026-09-30", 1200.0)
    _seed_filing(stores, "MSFT", filed_at=_ago(1), processed=True)
    res = thesis_health.refresh_all(stores)
    assert res[0]["summary_label"] == "Intact"
    item = thesis_health.plan_items(stores, plan_id)[0]
    assert item["status"] == "intact" and item["consecutive_breaches"] == 0
    assert not [i for i in _open_items(stores, "needs_attention")
                if i["source_type"] == "thesis_break"]

    # Due cadence: freshly refreshed → not due; >30d (non-held) → due again.
    assert "MSFT" not in thesis_health.due_tickers(stores)
    _age_refreshes(stores, "MSFT", days=31)
    assert "MSFT" in thesis_health.due_tickers(stores)

    view = thesis_health.thesis_health_view(stores, "MSFT")
    assert view["summary_label"] == "Intact"
    assert len(view["history"]) == 4
    assert view["filings_last_checked"] and view["recalculated_at"]


def test_data_gap_preserves_status_and_flags_repeats(stores):
    _seed_obs(stores, "NVDA", "gross_margin", "2026-03-31", 0.55)
    memo_id = _memo(stores, "NVDA", [_quant("gross_margin", ">=", 0.50, lookback="yoy")])
    plan_id = thesis_health.create_plan_for_memo(stores, memo_id)
    item = thesis_health.plan_items(stores, plan_id)[0]
    assert item["status"] == "intact"  # baseline grounded from latest evidence

    # YoY needs the prior-year quarter; missing it is a data gap that
    # preserves the prior status-driving status. NVDA has no filings-index
    # rows and bootstrap has not run, so the stored-observation fallback
    # heuristic still gates the full recalc (pre-bulk workspace).
    _age_plan(stores, plan_id, days=10)
    _seed_obs(stores, "NVDA", "gross_margin", "2026-06-30", 0.60)
    thesis_health.refresh_all(stores)  # never refreshed → due
    item = thesis_health.plan_items(stores, plan_id)[0]
    assert item["status"] == "intact" and item["data_gap_count"] == 1

    # Second consecutive gap → low-priority attention item (targeted refresh:
    # 5 days old and filing-less is not yet due for the scheduled pass).
    _age_refreshes(stores, "NVDA", days=5)
    _seed_obs(stores, "NVDA", "gross_margin", "2026-09-30", 0.58)
    assert "NVDA" not in thesis_health.due_tickers(stores)
    thesis_health.refresh_for(stores, ["NVDA"], trigger="manual")
    item = thesis_health.plan_items(stores, plan_id)[0]
    assert item["status"] == "intact" and item["data_gap_count"] == 2
    gaps = [i for i in _open_items(stores, "needs_attention") if i["source_type"] == "data_gap"]
    assert len(gaps) == 1 and gaps[0]["severity"] == "low"

    view = thesis_health.thesis_health_view(stores, "NVDA")
    assert view["items"][0]["data_gap"] is True
    assert view["summary_label"] == "Intact"


# --- 3b. bulk filings index gates due-ness and full recalcs (ADR-0059) ---------------------

def test_filings_index_gates_due_and_full_refresh(stores):
    _seed_obs(stores, "FIL1", "revenue", "2026-03-31", 1200.0)
    plan_id = thesis_health.create_plan_for_memo(
        stores, _memo(stores, "FIL1", [_quant("revenue", ">=", 1000.0)]))
    _age_plan(stores, plan_id, days=10)

    # Bootstrapped bulk workspace: the stored-observation fallback stays off,
    # so a new observation WITHOUT a filings-index row is metadata-only.
    stores.bulk.set_state("bootstrap_done", "1")
    _seed_obs(stores, "FIL1", "revenue", "2026-06-30", 900.0)
    res = thesis_health.refresh_all(stores)  # never refreshed → due
    assert res == [{"ticker": "FIL1", "metadata_only": True, "summary_label": "Intact"}]
    item = thesis_health.plan_items(stores, plan_id)[0]
    assert item["status"] == "intact" and item["current_value"] == pytest.approx(1200.0)

    # Irrelevant form (8-K) → not due, still metadata-gated.
    _seed_filing(stores, "FIL1", form="8-K", filed_at=_ago(1), processed=True)
    assert "FIL1" not in thesis_health.due_tickers(stores)

    # New 10-Q row → due → FULL recalc consumes the waiting observation.
    fid = _seed_filing(stores, "FIL1", form="10-Q", filed_at=_ago(1))
    assert "FIL1" in thesis_health.due_tickers(stores)
    res = thesis_health.refresh_all(stores)
    assert res == [{"ticker": "FIL1", "metadata_only": False, "summary_label": "Watching"}]
    item = thesis_health.plan_items(stores, plan_id)[0]
    assert item["status"] == "watch" and item["current_value"] == pytest.approx(900.0)
    check = stores.ws.query_one(
        "SELECT filing_check FROM thesis_health_refreshes WHERE ticker = 'FIL1' "
        "AND metadata_only = 0 ORDER BY ran_at DESC LIMIT 1")
    assert '"filings_index"' in check["filing_check"]

    # Unprocessed relevant filing keeps the ticker due; once processed (and
    # nothing filed after the full refresh) it drops out of the due list.
    assert "FIL1" in thesis_health.due_tickers(stores)
    stores.bulk.mark_filings_processed([fid])
    assert "FIL1" not in thesis_health.due_tickers(stores)
    res = thesis_health.refresh_for(stores, ["FIL1"], trigger="manual")
    assert res[0]["metadata_only"] is True


def test_refresh_for_only_touches_given_tickers(stores):
    for t in ("TGTA", "TGTB"):
        _seed_obs(stores, t, "revenue", "2026-03-31", 1500.0)
        thesis_health.create_plan_for_memo(
            stores, _memo(stores, t, [_quant("revenue", ">=", 1000.0)]))
    res = thesis_health.refresh_for(stores, ["tgta", "NOPLAN"])
    assert [r["ticker"] for r in res] == ["TGTA"]  # NOPLAN: no active plan → skipped
    rows = stores.ws.query("SELECT ticker, trigger FROM thesis_health_refreshes")
    assert {(r["ticker"], r["trigger"]) for r in rows} == {("TGTA", "filing")}


# --- 4. dashboard rebuild: pressure + opportunities, rank sources, dedupe -------------------

def test_dashboard_rebuild_pressure_and_opportunities(stores):
    svc = PortfolioService(stores)
    svc.add_lot("HOLD1", 10, 100.0, "2026-01-02")
    svc.add_lot("HOLD2", 1, 50.0, "2026-01-03")
    stores.portfolio.mark_price("HOLD1", 100.0)
    stores.portfolio.mark_price("HOLD2", 50.0)
    stores.portfolio.rebuild_holdings()

    # HOLD1: immediate-kill breach at baseline → Broken (held).
    _seed_obs(stores, "HOLD1", "revenue", "2026-03-31", 500.0)
    memo_id = _memo(stores, "HOLD1", [_quant("revenue", ">=", 1000.0,
                                             item_type="kill_criterion",
                                             immediate_kill=True)])
    thesis_health.create_plan_for_memo(stores, memo_id)
    assert thesis_health.summary_for(stores, "HOLD1") == "Broken"

    # OPP1: non-held with a retained IC pass verdict.
    stores.artifacts.save_ic_verdict("OPP1", "pass", gate_score=82.0, conviction=80.0,
                                     constitution_fit=85.0, data_quality=80.0)

    dashboard_service.rebuild(stores)
    overview = dashboard_service.overview(stores)

    pressure = overview["portfolio_review"]["pressure"]
    assert [p["ticker"] for p in pressure] == ["HOLD1", "HOLD2"]
    assert pressure[0]["severity"] == "high"
    assert pressure[0]["rank_source"].startswith("Thesis health broken")
    assert pressure[0]["title"] == "Thesis pressure"  # category title, not the ticker
    assert "Concentration" in pressure[0]["body"]  # >20% weight surfaced factually
    assert pressure[1]["rank_source"].startswith("Coverage")
    for p in pressure:  # evidence-first language, never buy/sell
        text = f"{p['title']} {p['body']}".lower()
        assert "sell" not in text and "buy" not in text

    opportunities = overview["portfolio_review"]["opportunities"]
    assert len(opportunities) == 1
    assert opportunities[0]["ticker"] == "OPP1"
    assert "IC pass 82/100" in opportunities[0]["rank_source"]

    # Holdings view: factual flags + thesis health labels.
    rows = {r["ticker"]: r for r in svc.holdings_view()}
    assert rows["HOLD1"]["thesis_health_label"] == "Broken"
    assert any(f["kind"] == "concentration" for f in rows["HOLD1"]["flags"])
    assert rows["HOLD2"]["flags"] == []

    # Re-running the rebuild dedupes on source version.
    dashboard_service.rebuild(stores)
    again = dashboard_service.overview(stores)
    assert len(again["portfolio_review"]["pressure"]) == 2
    assert len(again["portfolio_review"]["opportunities"]) == 1

    # A dismissed opportunity stays dismissed for the same source version,
    # and the judgment-revealing response becomes a learning feedback signal.
    res = dashboard_service.respond_item(stores, opportunities[0]["id"], "dismiss")
    assert res["status"] == "dismissed"
    dashboard_service.rebuild(stores)
    final = dashboard_service.overview(stores)
    assert final["portfolio_review"]["opportunities"] == []
    assert stores.learning.records(kind="feedback_signal", ticker="OPP1")


# --- 5. outcome evaluation classification + patterns ----------------------------------------

def test_classify_outcome_rules():
    assert learning.classify_outcome(3, None, "Intact") == \
        ("no_clear_signal", "data quality gap")
    assert learning.classify_outcome(3, 5.0, "Intact")[0:2] == \
        ("no_clear_signal", "insufficient time")
    assert learning.classify_outcome(6, 15.0, "Intact")[0] == "thesis_worked"
    assert learning.classify_outcome(12, -20.0, "Broken")[0] == "thesis_failed"
    assert learning.classify_outcome(12, 30.0, "Broken")[0] == "lucky_result"
    assert learning.classify_outcome(6, -5.0, "Watching")[0] == "right_thesis_slow_market"
    assert learning.classify_outcome(6, -5.0, "Intact")[0] == "right_thesis_slow_market"
    assert learning.classify_outcome(6, 5.0, "Intact") == \
        ("no_clear_signal", "conflicting evidence")


def test_outcome_evaluations_and_pattern_detection(stores):
    # LRN1: thesis 200 days ago at $100, now $120, memo-backed health Intact.
    ent = stores.identity.ensure_entity("LRN1")
    thesis_id = stores.artifacts.save_artifact(
        "thesis", {"kind": "thesis", "schema_version": "1.0", "generated_at": now_iso(),
                   "body": {"price": 100.0, "summary": "compounding machine"}},
        ticker="LRN1", entity_id=ent["id"])
    _set(stores, "UPDATE artifacts SET created_at = ? WHERE id = ?", (_ago(200), thesis_id))
    stores.portfolio.mark_price("LRN1", 120.0)
    _seed_obs(stores, "LRN1", "revenue", "2026-03-31", 1100.0)
    thesis_health.create_plan_for_memo(
        stores, _memo(stores, "LRN1", [_quant("revenue", ">=", 1000.0)]))

    created = learning.run_outcome_evaluations(stores)
    assert created == 2  # 3- and 6-month windows due after ~200 days
    evals = stores.learning.records(kind="outcome_evaluation", ticker="LRN1")
    assert {e["window_months"] for e in evals} == {3, 6}
    for e in evals:
        assert e["payload"]["result"] == "thesis_worked"
        assert e["payload"]["return_pct"] == pytest.approx(20.0)
        assert e["payload"]["thesis_health_label"] == "Intact"
        # No bulk price history → entry fell back to the artifact snapshot.
        assert e["payload"]["price_source"] == "snapshot"
        assert e["lineage"]["anchor_artifact_id"] == thesis_id
    assert learning.run_outcome_evaluations(stores) == 0  # idempotent per window

    # Five more thesis_worked evaluations sharing a positive screening metric.
    run_id = stores.runs.start_run("screener")
    stores.runs.finish_run(run_id)
    for i, t in enumerate(["P1", "P2", "P3", "P4", "P5"], start=1):
        stores.artifacts.save_screener_result(
            run_id, t, passed=True, rank=i, score=90 - i,
            ranking_components=[{"metric": "fcf_yield", "value": 0.08}])
        stores.learning.add_record(
            "outcome_evaluation", {"result": "thesis_worked", "return_pct": 15.0},
            ticker=t, window_months=12)

    records = learning.detect_patterns(stores)
    kinds = {r["kind"] for r in records}
    assert kinds == {"pattern", "recommendation"}
    pattern = next(r for r in records if r["kind"] == "pattern")
    assert pattern["confidence_label"] == "promising"
    assert pattern["payload"]["metric"] == "fcf_yield"
    assert pattern["payload"]["direction"] == "positive"
    rec = next(r for r in records if r["kind"] == "recommendation")
    assert rec["confidence_label"] == "recommendation_ready"
    assert rec["payload"]["proposed_change"]["kind"] == "research_review"  # least aggressive
    assert learning.detect_patterns(stores) == []  # nothing new → no duplicates

    # Recommendation-ready records become Dashboard decision items; never auto-applied.
    dashboard_service.rebuild(stores)
    decisions = dashboard_service.overview(stores)["needs_decision"]
    assert any(d["source_type"] == "learning_recommendation" for d in decisions)

    view = learning.learning_view(stores)
    assert view["summary"]["counts"]["outcome_evaluations"] == 7
    assert view["summary"]["counts"]["recommendations"] == 1
    assert view["summary"]["counts"]["results"]["thesis_worked"] == 7


# --- 4b. AI proposes, the deterministic gate disposes -------------------------------------

def test_ai_candidate_surfaces_categorical_pattern_and_gate_rejects_fabrication(stores):
    """AI proposals only nominate where to look; the deterministic gate decides
    what is real. A sector concentration the numeric same-sign scan never
    inspects is confirmed when the data supports it; a feature no company
    actually has is rejected, so the model cannot fabricate a pattern."""
    for t in ("EN1", "EN2", "EN3"):
        stores.identity.ensure_entity(t, sector="Energy")
        stores.learning.add_record(
            "outcome_evaluation",
            {"result": "thesis_failed", "return_pct": -25.0, "idea_source": "pipeline"},
            ticker=t, window_months=12)

    # The pure deterministic scan finds nothing — no numeric screening metrics.
    assert learning.detect_patterns(stores) == []

    ai_candidates = [
        {"result": "thesis_failed", "feature": "sector", "direction": "Energy",
         "rationale": "energy names clustered in the failures", "systematic": True},
        {"result": "thesis_failed", "feature": "roic", "direction": "negative",
         "rationale": "fabricated — no roic evidence", "systematic": True},
    ]
    created = learning.detect_patterns(stores, ai_candidates=ai_candidates)
    pats = {p["payload"]["metric"]: p for p in created if p["kind"] == "pattern"}
    assert "sector" in pats and pats["sector"]["payload"]["direction"] == "Energy"
    assert pats["sector"]["payload"]["discovery"] == "ai"
    assert "roic" not in pats  # gate rejects a feature with no supporting data
    # idea_source is shared too but was not nominated, and the numeric scan never
    # inspects categorical features — so only AI-nominated context surfaces.
    assert "idea_source" not in pats


def test_propose_pattern_candidates_offline_is_noop(stores, offline_ai):
    """Stub mode proposes nothing, so the loop degrades to the deterministic
    scan (no model dependency to observe learning)."""
    for t in ("OF1", "OF2", "OF3"):
        stores.learning.add_record(
            "outcome_evaluation", {"result": "thesis_worked", "return_pct": 15.0},
            ticker=t, window_months=12)
    assert asyncio.run(learning.propose_pattern_candidates(stores)) == []


def test_outcome_evaluation_uses_price_history_at_window_boundaries(stores):
    """Point-in-time prices (ADR-0059): entry = close on/before the anchor
    artifact date, current = close on/before anchor + window; later closes
    and the live price mark must not leak into closed windows."""
    ent = stores.identity.ensure_entity("PXH1")
    thesis_id = stores.artifacts.save_artifact(
        "thesis", {"kind": "thesis", "schema_version": "1.0", "generated_at": now_iso(),
                   "body": {"price": 999.0, "summary": "bulk-priced idea"}},
        ticker="PXH1", entity_id=ent["id"])
    anchor = datetime.now(timezone.utc) - timedelta(days=200)
    _set(stores, "UPDATE artifacts SET created_at = ? WHERE id = ?",
         (anchor.isoformat(timespec="seconds"), thesis_id))

    def day(offset: int) -> str:
        return (anchor + timedelta(days=offset)).date().isoformat()

    stores.bulk.upsert_prices([
        {"ticker": "PXH1", "date": day(-3), "close": 40.0},    # pre-anchor noise
        {"ticker": "PXH1", "date": day(0), "close": 50.0},     # entry boundary
        {"ticker": "PXH1", "date": day(85), "close": 60.0},    # last close ≤ 3m (90d)
        {"ticker": "PXH1", "date": day(95), "close": 70.0},    # outside the 3m window
        {"ticker": "PXH1", "date": day(178), "close": 75.0},   # last close ≤ 6m (180d)
        {"ticker": "PXH1", "date": day(195), "close": 130.0},  # latest, must not leak
    ])
    stores.portfolio.mark_price("PXH1", 500.0)  # fallback mark must not be used

    assert learning.run_outcome_evaluations(stores) == 2
    evals = {e["window_months"]: e["payload"] for e in stores.learning.records(
        kind="outcome_evaluation", ticker="PXH1")}
    assert set(evals) == {3, 6}
    for p in evals.values():
        assert p["price_source"] == "price_history"
        assert p["entry_price"] == pytest.approx(50.0)  # not 999 body, not 40 pre-anchor
    assert evals[3]["current_price"] == pytest.approx(60.0)
    assert evals[3]["return_pct"] == pytest.approx(20.0)
    assert evals[6]["current_price"] == pytest.approx(75.0)
    assert evals[6]["return_pct"] == pytest.approx(50.0)


# --- 6. company bulk-data endpoints (api-contract "Bulk data additions") --------------------

def test_company_prices_and_ownership_endpoints(stores):
    from fastapi.testclient import TestClient

    from backend.api import create_app

    def day(days_back: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat()

    stores.bulk.upsert_prices([
        {"ticker": "ENDP", "date": day(400), "close": 80.0, "volume": 1000},  # outside 1y
        {"ticker": "ENDP", "date": day(10), "close": 90.0, "volume": 1100},
        {"ticker": "ENDP", "date": day(1), "close": 95.0, "volume": 1200},
    ])
    stores.bulk.add_ownership("ENDP", "insider_transaction", "2026-05-01", "Jane Doe",
                              shares=1000, value=95000.0, owner_role="CFO", txn_type="buy")

    with TestClient(create_app()) as client:
        out = client.get("/api/company/endp/prices", params={"range": "1y"})
        assert out.status_code == 200
        body = out.json()
        assert body["ticker"] == "ENDP" and body["range"] == "1y"
        assert [p["close"] for p in body["prices"]] == [90.0, 95.0]
        assert body["prices"][0] == {"date": day(10), "close": 90.0, "volume": 1100}
        five = client.get("/api/company/ENDP/prices", params={"range": "5y"}).json()
        assert len(five["prices"]) == 3
        # No history → empty list, never 404.
        empty = client.get("/api/company/NOPE/prices")
        assert empty.status_code == 200 and empty.json()["prices"] == []

        own = client.get("/api/company/ENDP/ownership")
        assert own.status_code == 200
        body = own.json()
        assert body["insiders"] == [{"as_of": "2026-05-01", "owner_name": "Jane Doe",
                                     "owner_role": "CFO", "txn_type": "buy",
                                     "shares": 1000.0, "value": 95000.0}]
        # 13F panel dropped: institutions is no longer a (hardcoded-empty) key;
        # a reason is surfaced instead. Insiders-but-no-holders -> holders_reason.
        assert "institutions" not in body and body["institutions_reason"]
        assert "empty_reason" not in body and body["holders_reason"]
        bare = client.get("/api/company/NOPE/ownership").json()
        assert bare["insiders"] == [] and bare["largest_holders"] == []
        assert bare["empty_reason"].startswith("No ownership history retained yet")


# --- 3c. ungrounded baselines explain themselves + raise an attention item ----------------

def test_data_gap_baseline_surfaces_reason_and_attention(stores):
    """A memo whose watch-item metric has no retained history grounds nothing:
    the Company Page explains why instead of a bare 'Not Checked', and a
    low-severity attention item flags the gap (the QA blind spot). When evidence
    later arrives and a filing gates the recalc, both clear."""
    from backend.workflows.memo import _create_thesis_health_plan

    memo_id = _memo(stores, "TSLA", [_quant("revenue", ">=", 1000.0)])
    _create_thesis_health_plan(stores, memo_id, "TSLA")

    view = thesis_health.thesis_health_view(stores, "TSLA")
    assert "baseline evidence is missing for revenue" in (view["empty_reason"] or "")

    gaps = stores.ws.query(
        "SELECT * FROM dashboard_items WHERE source_type = 'thesis_health_gap' "
        "AND status = 'open'")
    assert gaps and gaps[0]["ticker"] == "TSLA"

    # Evidence arrives + a relevant filing gates the recalc → grounded → resolved.
    _seed_obs(stores, "TSLA", "revenue", "2026-03-31", 1200.0)
    _seed_filing(stores, "TSLA", "10-Q")
    thesis_health.refresh_for(stores, ["TSLA"], trigger="filing")
    assert thesis_health.thesis_health_view(stores, "TSLA")["summary_label"] == "Intact"
    assert not stores.ws.query(
        "SELECT * FROM dashboard_items WHERE source_type = 'thesis_health_gap' "
        "AND status = 'open'")
