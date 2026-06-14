"""Run-concurrency guard, orphan reconciliation, and read-time valuation
metric derivation — the fixes for stacked pipeline runs and 0% theses.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.workflows.evidence_packets import _enrich_valuation_metrics


@pytest.fixture
def client(stores, offline_ai):
    with TestClient(create_app()) as c:
        yield c


# --- valuation metric derivation (fixes 0% theses) ---------------------------------

def test_enrich_derives_price_ratios():
    latest = {
        "shares_outstanding": 1_000_000, "free_cash_flow": 5_000_000,
        "net_income": 4_000_000, "eps": 4.0, "revenue": 100_000_000, "roic": 0.2,
    }
    notes: list[str] = []
    _enrich_valuation_metrics(latest, price=40.0,
                              trends={"latest_quarter_revenue_yoy_pct": 12.0}, notes=notes)
    assert latest["market_cap"] == 40_000_000          # price × shares
    assert latest["fcf_yield"] == 5_000_000 / 40_000_000  # fcf / market cap
    assert latest["earnings_yield"] == 4_000_000 / 40_000_000
    assert latest["pe"] == 10.0                        # price / eps
    assert latest["revenue_growth"] == 0.12            # yoy% → decimal


def test_enrich_falls_back_to_cagr_for_growth():
    latest = {"shares_outstanding": 100, "eps": 2.0, "revenue": 5.0}
    notes: list[str] = []
    _enrich_valuation_metrics(latest, price=20.0, trends={"revenue_cagr_pct": 8.0}, notes=notes)
    assert latest["revenue_growth"] == 0.08


def test_enrich_never_overwrites_stored_values():
    latest = {"shares_outstanding": 100, "free_cash_flow": 50, "fcf_yield": 0.99, "eps": 1.0}
    _enrich_valuation_metrics(latest, price=10.0, trends={}, notes=[])
    assert latest["fcf_yield"] == 0.99  # left as-is


def test_enrich_flags_absurd_roic():
    latest = {"roic": 7.57, "eps": 1.5}
    notes: list[str] = []
    _enrich_valuation_metrics(latest, price=100.0, trends={}, notes=notes)
    assert any("unreliable" in n for n in notes)


def test_enrich_notes_missing_growth_history():
    latest = {"shares_outstanding": 100, "eps": 2.0, "revenue": 5.0}
    notes: list[str] = []
    _enrich_valuation_metrics(latest, price=20.0, trends={}, notes=notes)
    assert latest.get("revenue_growth") in (None, 0, 0.0)
    assert any("revenue growth unavailable" in n for n in notes)


# --- run store: active-run lookup + orphan reconciliation ---------------------------

def test_active_run_id_scoped_to_session(stores):
    assert stores.runs.active_run_id("thesis") is None
    rid = stores.runs.start_run("thesis", "user")
    assert stores.runs.active_run_id("thesis") == rid
    stores.runs.finish_run(rid, "completed")
    assert stores.runs.active_run_id("thesis") is None


def test_workbench_survives_server_restart(stores):
    """Stage output is durable: a new server session must still see the last
    session's workbench (stage pages were blanking after every restart)."""
    rid = stores.runs.start_run("thesis", "user")
    stores.runs.finish_run(rid, "completed")
    stores.runs.set_workbench("thesis", {"status": "completed", "run_id": rid, "rows": [1]})
    # Simulate a restart: the row belongs to a prior server session now.
    with stores.ws.transaction() as conn:
        conn.execute("UPDATE workbench_state SET server_session_id = 'prior'")
    wb = stores.runs.get_workbench("thesis")
    assert wb is not None and wb["rows"] == [1]


def test_workbench_never_presents_dead_run_as_live(stores):
    rid = stores.runs.start_run("thesis", "user")
    stores.runs.set_workbench("thesis", {"status": "running", "run_id": rid})
    stores.runs.finish_run(rid, "failed", error="interrupted")
    with stores.ws.transaction() as conn:
        conn.execute("UPDATE workbench_state SET server_session_id = 'prior'")
    wb = stores.runs.get_workbench("thesis")
    assert wb["status"] == "failed"  # synced to run truth, not stale 'running'


def test_reconcile_orphans_fails_prior_session_runs(stores):
    rid = stores.runs.start_run("pipeline", "user")
    # Simulate a run left running by a previous process.
    with stores.ws.transaction() as conn:
        conn.execute("UPDATE workflow_runs SET server_session_id = 'prior' WHERE id = ?", (rid,))
    assert stores.runs.reconcile_orphans() == 1
    run = stores.runs.get_run(rid)
    assert run["status"] == "failed"
    assert "interrupted" in (run["error"] or "")
    # A current-session running run is left alone.
    live = stores.runs.start_run("thesis", "user")
    assert stores.runs.reconcile_orphans() == 0
    assert stores.runs.get_run(live)["status"] == "running"


def test_reconcile_orphans_cascades_non_terminal_steps(stores):
    """A swept run must not leave its steps perpetually 'running' (the Runs
    live-stage-map reads step status)."""
    rid = stores.runs.start_run("thesis", "user")
    sid = stores.runs.add_step(rid, "thesis", "XYZ")  # defaults to 'running'
    with stores.ws.transaction() as conn:
        conn.execute("UPDATE workflow_runs SET server_session_id = 'prior' WHERE id = ?", (rid,))
    stores.runs.reconcile_orphans()
    step = stores.runs.steps_for(rid)[0]
    assert step["status"] == "failed"
    assert "interrupted" in (step["error"] or "")


def test_finish_run_closes_dangling_steps(stores):
    rid = stores.runs.start_run("thesis", "user")
    stores.runs.add_step(rid, "thesis", "XYZ")  # left non-terminal
    stores.runs.finish_run(rid, "failed", error="boom")
    step = stores.runs.steps_for(rid)[0]
    assert step["status"] == "failed"
    # A step that finished normally before the run is left untouched.
    rid2 = stores.runs.start_run("thesis", "user")
    sid2 = stores.runs.add_step(rid2, "thesis", "AAA")
    stores.runs.finish_step(sid2, "completed", detail={"ok": True})
    stores.runs.finish_run(rid2, "completed")
    assert stores.runs.steps_for(rid2)[0]["status"] == "completed"


def test_gc_orphan_bundles(stores):
    # A frozen bundle no artifact references is reclaimed; a referenced one survives.
    orphan = stores.evidence.freeze_bundle({"kind": "thesis", "ticker": "ORP"})
    kept = stores.evidence.freeze_bundle({"kind": "thesis", "ticker": "KEP"})
    stores.artifacts.save_artifact(
        "thesis", {"kind": "thesis", "schema_version": "1.0", "generated_at": "2026-01-01",
                   "body": {"summary": "x"}},
        ticker="KEP", evidence_bundle_id=kept)
    removed = stores.evidence.gc_orphan_bundles()
    assert removed == 1
    assert stores.evidence.get_bundle(orphan) is None
    assert stores.evidence.get_bundle(kept) is not None


def test_dead_evidence_records_table_dropped(stores):
    row = stores.ws.query_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence_records'")
    assert row is None


def test_opportunity_responses_take_action_and_report(stores):
    """Watch/Interested do what their labels say; every feedback response
    returns a human note so the action is never an invisible dismiss."""
    from backend.services.dashboard_service import respond_item
    from backend.workflows import thesis

    iid = stores.dashboard.upsert_item(
        "attention", "portfolio_review", "constitution_fit", "scr_1", "v1",
        "ADBE Constitution-fit opportunity", ticker="ADBE")
    res = respond_item(stores, iid, "watch")
    assert "Watching" in (res["note"] or "")
    wl = stores.context.watchlist_by_name("Watching")
    assert wl and "ADBE" in wl["tickers"]

    iid2 = stores.dashboard.upsert_item(
        "attention", "portfolio_review", "constitution_fit", "scr_2", "v1",
        "V Constitution-fit opportunity", ticker="V")
    res2 = respond_item(stores, iid2, "interested")
    assert "Thesis" in (res2["note"] or "")
    intake = stores.runs.get_workbench(thesis.INTAKE_KEY) or {}
    assert any(i["ticker"] == "V" for i in intake.get("items") or [])

    iid3 = stores.dashboard.upsert_item(
        "attention", "portfolio_review", "constitution_fit", "scr_3", "v1",
        "NVDA Constitution-fit opportunity", ticker="NVDA")
    res3 = respond_item(stores, iid3, "too_risky")
    assert "Recorded" in (res3["note"] or "") and "NVDA" in res3["note"]


def test_clear_pipeline_survives_dropped_table(client):
    # /clear-pipeline used to DELETE FROM evidence_records; after the drop that
    # statement was removed in lockstep, so the endpoint must still succeed.
    resp = client.post("/api/settings/clear-pipeline")
    assert resp.status_code == 200, resp.text


# --- route guards (no stacked duplicates) ------------------------------------------

def test_route_blocks_duplicate_thesis(client, stores):
    rid = stores.runs.start_run("thesis", "user")  # an in-flight run
    body = client.post("/api/workflows/thesis/run").json()
    assert body == {"run_id": rid, "already_running": True}


def test_pipeline_blocked_by_any_funnel_run(client, stores):
    rid = stores.runs.start_run("screener", "user")
    body = client.post("/api/workflows/pipeline/run").json()
    assert body["already_running"] is True
    assert body["blocked_by"] == "screener"
    assert body["run_id"] == rid


# --- dashboard respond: double-submit is a no-op -------------------------------------

def test_dashboard_respond_double_submit_is_noop(stores):
    iid = stores.dashboard.upsert_item(
        "attention", "needs_attention", "filing_event", "f1", "v1", "AAPL: filed",
        ticker="AAPL")
    from backend.services.dashboard_service import respond_item
    first = respond_item(stores, iid, "dismiss")
    assert first["ok"] and "already_responded" not in first
    second = respond_item(stores, iid, "dismiss")
    assert second.get("already_responded") is True
    rows = stores.ws.query(
        "SELECT COUNT(*) AS n FROM dashboard_responses WHERE item_id = ?", (iid,))
    assert rows[0]["n"] == 1  # exactly one record, not two


def test_future_dated_ledger_entries_rejected(stores):
    from backend.services.portfolio_service import PortfolioService
    import pytest as _pytest
    svc = PortfolioService(stores)
    with _pytest.raises(ValueError, match="future"):
        svc.add_lot("AAPL", 5, 100.0, "2099-01-01")
    svc.add_lot("AAPL", 5, 100.0, "2026-06-01")
    with _pytest.raises(ValueError, match="future"):
        svc.record_sale("AAPL", 1, 120.0, "2099-01-02")


def test_universe_inherited_across_strategy_changes(stores):
    """Accepting a proposal that doesn't restate the universe must NOT silently
    fall back to the config default preset (found by the quality bench)."""
    from backend.domain.criteria import Criterion
    c = [Criterion.from_dict({"criterion_id": "screen.roic_min", "kind": "screen",
                              "metric": "roic", "operator": ">=", "value": 0.1})]
    stores.constitution.activate_version(
        "v1", None, None, "init", c, {}, universe={
            "name": "S&P 500", "tickers": ["AAA", "BBB"], "source": "preset"})
    assert stores.constitution.active_universe()["tickers"] == ["AAA", "BBB"]
    # New version, NO universe in the payload → must inherit, not vanish.
    stores.constitution.activate_version("v2", None, None, "change", c, {}, universe=None)
    uni = stores.constitution.active_universe()
    assert uni is not None and uni["tickers"] == ["AAA", "BBB"]
    assert uni["name"] == "S&P 500"
