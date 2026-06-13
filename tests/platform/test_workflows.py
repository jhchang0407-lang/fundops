"""End-to-end workflow tests: offline (stub-mode AI, fake market data),
deterministic, no network. Covers screener evaluation/ranking/selection,
thesis generation + score cap + failure isolation, IC gate + hurdles +
override, memo sections + monitoring plan, and the full pipeline."""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.core import ai
from backend.domain.artifact_schemas import (
    MEMO_DECISIONS, MEMO_OUTLINE, validate_memo, validate_thesis,
)
from backend.workflows import ic_review, pipeline, screener, thesis
from backend.workflows import memo as memo_wf


def _run(coro):
    return asyncio.run(coro)


def _tickers(rows):
    return [r["ticker"] for r in rows]


# --- thesis return math (RC7) ---------------------------------------------------------


def test_reconcile_return_clamps_dedups_and_flags():
    """RC7 unit: _reconcile_return sanitizes the model's return math before it is
    persisted or read by the IC gate. The stub path never exercises these
    branches, so cover them directly."""
    # (a) implausible headline clamped into the band; clamped value is what flows
    exp, comps, warn = thesis._reconcile_return(790.0, {"growth": 790.0})
    assert exp == 200.0 and warn and "clamp" in warn.lower()
    assert abs(sum(comps.values()) - 200.0) <= 1.5  # attribution rescaled to match
    exp, _, warn = thesis._reconcile_return(-697.0, {"valuation_gap": -697.0})
    assert exp == -200.0 and warn

    # (b) doubled valuation/re-rating component collapsed; CORRECT headline kept
    exp, comps, warn = thesis._reconcile_return(
        -21.6, {"valuation_gap": -21.6, "multiple_rerating": -21.6})
    assert exp == -21.6                       # preserved, NOT corrupted to -43.2
    assert "multiple_rerating" not in comps   # duplicate dropped
    assert comps["valuation_gap"] == -21.6
    assert warn and "duplicat" in warn.lower()

    # (c) attribution gap flagged + rescaled, headline preserved
    exp, comps, warn = thesis._reconcile_return(20.0, {"growth": 40.0})
    assert exp == 20.0 and warn
    assert abs(sum(comps.values()) - 20.0) <= 1.5

    # clean profile: components already sum to the headline -> no warning, no change
    exp, comps, warn = thesis._reconcile_return(
        18.0, {"valuation_gap": 12.0, "growth": 6.0})
    assert exp == 18.0 and warn is None and comps == {"valuation_gap": 12.0, "growth": 6.0}


def test_build_payload_clamps_and_is_auditor_clean():
    """A clamped/reconciled thesis payload surfaces coherence_warning on the body
    AND passes the deterministic artifact auditor (no implausible-return / return-
    math problem) — generation and CI agree."""
    from scripts.quality_audit import audit_artifact
    from backend.domain.artifact_schemas import THESIS_SCOPE_FIELDS

    result = {
        "summary": "Thesis summary with a 12.3% figure.",
        "scope": {f: "Cites a 10% figure and a 2x peer rank." for f in THESIS_SCOPE_FIELDS},
        "return_potential": {"expected_return_pct": 790.0, "components": {"growth": 790.0},
                             "fair_value": 100.0, "valuation_method": "DCF"},
        "evidence_notes": [],
    }
    payload = thesis._build_payload(
        "AKBA", {"id": "ent_1"}, {"cv_id": None}, "bundle_1", result, 50.0, {})
    rp = payload["body"]["return_potential"]
    assert rp["expected_return_pct"] == 200.0           # clamped — what the IC gate reads
    assert payload["body"].get("coherence_warning")     # surfaced on body top-level
    problems = audit_artifact({"kind": "thesis", "payload": payload, "rendered_md": ""})
    assert not any("implausible expected return" in p for p in problems), problems
    assert not any(p.startswith("return math") for p in problems), problems


# --- screener -------------------------------------------------------------------------


def test_screener_run_review_set_and_evidence(stores, fake_market, constitution):
    rid = _run(screener.run_screener(stores))
    run = stores.runs.get_run(rid)
    assert run["status"] == "completed"
    assert run["constitution_version_id"] == constitution["id"]
    assert run["universe_version_id"]

    cur = screener.screener_current(stores)
    assert cur["status"] == "completed"
    assert cur["summary"] == {"universe_size": 6, "passed": 4, "shown": 4}

    # Ranking by weighted metric percentiles: AAA > BBB > FFF > CCC.
    shown = _tickers(cur["top_picks"]) + _tickers(cur["remaining"])
    assert shown == ["AAA", "BBB", "FFF", "CCC"]
    # Top Picks = top handoff_count (3), selection_order = rank.
    assert _tickers(cur["top_picks"]) == ["AAA", "BBB", "FFF"]
    assert [r["selection_order"] for r in cur["top_picks"]] == [1, 2, 3]
    assert all(r["selected"] for r in cur["top_picks"])
    assert not any(r["selected"] for r in cur["remaining"])

    top = cur["top_picks"][0]
    assert top["company_name"] == "Alpha Corp"
    assert top["price"] == 100.0
    assert top["rank"] == 1
    assert "Ranked #1 of 4" in top["ranking_explanation"]
    assert {e["criterion"] for e in top["pass_evidence"]} == {
        "screen.roic_min", "screen.gross_margin_min",
    }
    assert [k["metric"] for k in top["key_financials"]]

    # Snapshot artifacts exist for the whole review set, with ranking components.
    snapshots = [a for a in stores.artifacts.for_run(rid)
                 if a["kind"] == "screener_snapshot"]
    assert len(snapshots) == 4
    aaa = next(a for a in snapshots if a["ticker"] == "AAA")
    body = aaa["payload"]["body"]
    assert body["rank"] == 1 and body["top_picks"] is True
    comps = {c["criterion_id"]: c for c in body["ranking_components"]}
    assert comps["rank.fcf_yield"]["weight"] == pytest.approx(0.6)
    assert comps["rank.fcf_yield"]["percentile"] == pytest.approx(87.5)
    assert aaa["payload"]["validation"]["ok"] is True
    assert aaa["evidence_bundle_id"]

    # Failed companies retained as Screener Run Evidence with ALL reasons.
    results = {r["ticker"]: r for r in stores.artifacts.screener_results(rid, passed_only=False)}
    assert len(results) == 6
    ddd = results["DDD"]
    assert ddd["passed"] == 0
    assert {f["criterion"] for f in ddd["fail_reasons"]} == {
        "screen.roic_min", "screen.gross_margin_min",
    }
    assert all(f["observed"] is not None and f["threshold"] for f in ddd["fail_reasons"])
    eee = results["EEE"]  # no data => unevaluable, not a failed company
    assert eee["passed"] == 0
    assert all(f["reason"] == "missing data" for f in eee["fail_reasons"])

    # Handoff refreshed thesis intake without executing thesis.
    intake = stores.runs.get_workbench("thesis_intake")
    assert intake["tickers"] == ["AAA", "BBB", "FFF"]
    assert stores.runs.get_workbench("thesis") is None

    # Handoff is immediately visible: thesis_current surfaces the picks as
    # pending intake rows before any Run Thesis, so the next stage is populated.
    cur = thesis.thesis_current(stores)
    assert [r["ticker"] for r in cur["rows"]] == ["AAA", "BBB", "FFF"]
    assert all(r["state"] == "pending" for r in cur["rows"])
    assert all(r.get("company_name") for r in cur["rows"])


def test_screener_selection_promote_and_dismiss_reflow(stores, fake_market, constitution):
    _run(screener.run_screener(stores))

    # Promote appends to the end of the selection and expands the count.
    cur = screener.screener_select(stores, "CCC", "promote")
    assert _tickers(cur["top_picks"]) == ["AAA", "BBB", "FFF", "CCC"]
    assert cur["top_picks"][-1]["selection_order"] == 4

    # Dismissing a default-selection member reflows: ranks never change, the
    # next-ranked eligible candidate moves in (pool already exhausted here, so
    # the default block simply shrinks while the promotion stays appended).
    cur = screener.screener_select(stores, "BBB", "dismiss")
    assert _tickers(cur["top_picks"]) == ["AAA", "FFF", "CCC"]
    assert [r["rank"] for r in cur["top_picks"]] == [1, 3, 4]  # rank untouched

    # Dismissing a promoted member just removes the promotion (no refill).
    cur = screener.screener_select(stores, "CCC", "dismiss")
    assert _tickers(cur["top_picks"]) == ["AAA", "FFF"]

    # Re-promoting a dismissed default member appends it at the end.
    cur = screener.screener_select(stores, "BBB", "promote")
    assert _tickers(cur["top_picks"]) == ["AAA", "FFF", "BBB"]

    # Selection feedback recorded; thesis intake + typed rows follow selection.
    events = stores.runs.selection_events("screener")
    assert {(e["ticker"], e["action"]) for e in events} == {
        ("CCC", "promote"), ("BBB", "dismiss"), ("CCC", "dismiss"), ("BBB", "promote"),
    }
    assert len(events) == 4
    assert stores.runs.get_workbench("thesis_intake")["tickers"] == ["AAA", "FFF", "BBB"]
    wb = stores.runs.get_workbench("screener")
    rows = {r["ticker"]: r for r in
            stores.artifacts.screener_results(wb["run_id"], passed_only=True)}
    assert rows["BBB"]["selected"] == 1 and rows["BBB"]["selection_order"] == 3
    assert rows["CCC"]["selected"] == 0

    with pytest.raises(ValueError):
        screener.screener_select(stores, "DDD", "promote")  # not in stage output


def test_dismiss_from_default_pulls_next_ranked_in(stores, fake_market, constitution):
    _run(screener.run_screener(stores))
    # Default selection [AAA, BBB, FFF]; dismissing BBB pulls CCC (next ranked).
    cur = screener.screener_select(stores, "BBB", "dismiss")
    assert _tickers(cur["top_picks"]) == ["AAA", "FFF", "CCC"]


# --- thesis ---------------------------------------------------------------------------


def _screener_with_ccc(stores):
    _run(screener.run_screener(stores))
    screener.screener_select(stores, "CCC", "promote")  # intake AAA BBB FFF CCC


def test_thesis_run_artifacts_ranking_and_cap(stores, fake_market, constitution):
    _screener_with_ccc(stores)
    rid = _run(thesis.run_thesis(stores))
    assert stores.runs.get_run(rid)["status"] == "completed"

    cur = thesis.thesis_current(stores)
    assert cur["status"] == "completed"
    rows = {r["ticker"]: r for r in cur["rows"]}
    assert rows["AAA"]["expected_return_pct"] == pytest.approx(18.0)
    assert rows["BBB"]["expected_return_pct"] == pytest.approx(13.0)
    assert rows["CCC"]["expected_return_pct"] == pytest.approx(3.0)
    assert rows["CCC"]["capped"] is True          # below return cap threshold 5.0
    assert rows["AAA"]["capped"] is False

    # Selection ranking by expected return; capped ranked last, never auto-selected.
    assert cur["selection"] == ["AAA", "BBB", "FFF"]
    assert cur["remaining"] == ["CCC"]
    assert _tickers(cur["rows"]) == ["AAA", "BBB", "FFF", "CCC"]

    # Artifacts validate against the fixed Thesis Research Scope schema.
    art = stores.artifacts.get(rows["AAA"]["artifact_id"])
    assert art["kind"] == "thesis"
    assert validate_thesis(art["payload"]).ok
    body = art["payload"]["body"]
    assert body["return_potential"]["components"]
    assert art["evidence_bundle_id"]

    # Valuation fields are ALWAYS populated at predictable paths (readers
    # never render empty price/fair-value): body.price + return_potential.
    assert body["price"] == 100.0
    rp = body["return_potential"]
    assert isinstance(rp["fair_value"], (int, float))
    assert isinstance(rp["valuation_method"], str) and rp["valuation_method"]

    # Stub scope answers are data-grounded (cite figures), substantive, and
    # mention offline mode ONLY in evidence_freshness.
    scope = body["scope"]
    for field, answer in scope.items():
        assert any(ch.isdigit() for ch in answer), f"{field} cites no figures"
        assert len(answer) > 80, f"{field} is a one-line stub"
        if field != "evidence_freshness":
            assert "offline" not in answer.lower()
    assert "offline" in scope["evidence_freshness"].lower()
    assert "AAA" in art["rendered_md"] and "| Metric | Value | Trend |" in art["rendered_md"]

    # Handoff: IC intake = selection with thesis artifact references.
    intake = stores.runs.get_workbench("ic_intake")
    assert intake["tickers"] == ["AAA", "BBB", "FFF"]
    assert all(i["thesis_artifact_id"] for i in intake["items"])

    # Handoff is immediately visible: ic_current surfaces the selection as
    # pending rows (in the remaining block) before any Run IC Review.
    ic_cur = ic_review.ic_current(stores)
    assert [r["ticker"] for r in ic_cur["remaining"]] == ["AAA", "BBB", "FFF"]
    assert all(r["state"] == "pending" and r["verdict"] is None
               for r in ic_cur["remaining"])

    # Capped theses are promotable; dismissal reflows without stigma.
    cur = thesis.thesis_select(stores, "CCC", "promote")
    assert cur["selection"] == ["AAA", "BBB", "FFF", "CCC"]
    cur = thesis.thesis_select(stores, "BBB", "dismiss")
    assert cur["selection"] == ["AAA", "FFF", "CCC"]
    assert stores.runs.get_workbench("ic_intake")["tickers"] == ["AAA", "FFF", "CCC"]
    events = stores.runs.selection_events("thesis")
    assert {(e["ticker"], e["action"]) for e in events} == {
        ("CCC", "promote"), ("BBB", "dismiss"),
    }


def test_thesis_rerun_resumes_without_regenerating(stores, fake_market, constitution):
    _run(screener.run_screener(stores))
    _run(thesis.run_thesis(stores))
    first = {r["ticker"]: r["artifact_id"] for r in thesis.thesis_current(stores)["rows"]}
    rid2 = _run(thesis.run_thesis(stores))
    second = {r["ticker"]: r["artifact_id"] for r in thesis.thesis_current(stores)["rows"]}
    assert first == second  # completed artifacts never regenerated in-context
    assert (stores.runs.get_run(rid2)["stats"] or {})["generated"] == 0


def test_thesis_operational_failure_is_isolated(stores, fake_market, constitution, monkeypatch):
    _run(screener.run_screener(stores))
    gateway = ai.get_ai()
    original = gateway.complete_json

    async def flaky(capability, system, user, *args, **kwargs):
        if capability == "thesis" and "(BBB)" in user:
            raise ai.AIError("synthetic provider outage")
        return await original(capability, system, user, *args, **kwargs)

    monkeypatch.setattr(gateway, "complete_json", flaky)
    rid = _run(thesis.run_thesis(stores))

    run = stores.runs.get_run(rid)
    assert run["status"] == "completed"  # one bad ticker never fails the run
    cur = thesis.thesis_current(stores)
    rows = {r["ticker"]: r for r in cur["rows"]}
    assert rows["BBB"]["state"] == "failed"
    assert rows["AAA"]["state"] == "completed"
    assert rows["FFF"]["state"] == "completed"
    assert "BBB" not in cur["selection"]  # ops failure excluded from selection

    steps = [s for s in stores.runs.steps_for(rid) if s["item_ref"] == "BBB"]
    assert steps and steps[-1]["status"] == "failed"
    assert steps[-1]["attempt"] == 3  # retried up to 3 attempts


# --- IC review -------------------------------------------------------------------------


def _through_thesis(stores, include_capped=True):
    _screener_with_ccc(stores)
    _run(thesis.run_thesis(stores))
    if include_capped:
        thesis.thesis_select(stores, "CCC", "promote")


def test_ic_run_verdicts_hurdles_and_override(stores, fake_market, constitution):
    _through_thesis(stores)
    rid = _run(ic_review.run_ic(stores))
    assert stores.runs.get_run(rid)["status"] == "completed"

    cur = ic_review.ic_current(stores)
    assert cur["status"] == "completed"
    assert set(_tickers(cur["selection"])) == {"AAA", "BBB"}      # gate passes
    assert set(_tickers(cur["remaining"])) == {"FFF", "CCC"}      # hurdle misses
    rows = {r["ticker"]: r for r in cur["selection"] + cur["remaining"]}

    aaa = rows["AAA"]
    assert aaa["verdict"] == "pass" and aaa["gate_score"] >= 70
    for k in ("conviction", "constitution_fit", "data_quality"):
        assert 0 <= aaa[k] <= 100
    assert aaa["rationale"]
    assert all(f["met"] for f in aaa["hurdle_findings"])

    # Deterministically-confirmed hurdle miss stays a miss (FFF: 7.0 < 8).
    fff = rows["FFF"]
    assert fff["verdict"] == "fail"
    miss = [f for f in fff["hurdle_findings"] if not f["met"]]
    assert miss and miss[0]["criterion_id"] == "ic.expected_return_min"
    assert "confirmed miss" in miss[0]["explanation"]

    # Typed verdict rows + ic_verdict artifacts persisted.
    verdicts = {v["ticker"]: v for v in stores.artifacts.ic_verdicts_for_run(rid)}
    assert len(verdicts) == 4
    assert verdicts["FFF"]["verdict"] == "fail"
    assert verdicts["AAA"]["artifact_id"]
    art = stores.artifacts.get(verdicts["AAA"]["artifact_id"])
    assert art["kind"] == "ic_verdict"
    assert art["payload"]["validation"]["ok"] is True
    assert art["payload"]["body"]["thesis_artifact_id"]
    assert art["payload"]["body"]["blend"]["conviction"] == pytest.approx(0.45)
    assert art["payload"]["body"]["cutoff"] == 70.0

    # Memo intake = IC selection (every pass, no cap).
    assert set(stores.runs.get_workbench("memo_intake")["tickers"]) == {"AAA", "BBB"}

    # Override promote: NEW verdict row, prior preserved, memo intake updated.
    cur = ic_review.ic_override(stores, "FFF", "promote")
    assert "FFF" in _tickers(cur["selection"])
    latest = stores.artifacts.latest_ic_verdict("FFF")
    assert latest["is_override"] == 1
    assert latest["prior_verdict"] == "fail" and latest["verdict"] == "pass"
    assert "FFF" in stores.runs.get_workbench("memo_intake")["tickers"]

    # Override remove on a pass.
    cur = ic_review.ic_override(stores, "BBB", "remove")
    assert "BBB" not in _tickers(cur["selection"])
    latest = stores.artifacts.latest_ic_verdict("BBB")
    assert latest["is_override"] == 1 and latest["prior_verdict"] == "pass"
    assert "BBB" not in stores.runs.get_workbench("memo_intake")["tickers"]

    events = stores.runs.selection_events("ic_review")
    assert {(e["ticker"], e["action"]) for e in events} == {
        ("FFF", "promote"), ("BBB", "dismiss"),
    }


# --- memo ------------------------------------------------------------------------------


def test_memo_run_sections_plan_and_decision(stores, fake_market, constitution):
    _through_thesis(stores, include_capped=False)
    _run(ic_review.run_ic(stores))
    rid = _run(memo_wf.run_memo(stores))
    assert stores.runs.get_run(rid)["status"] == "completed"

    cur = memo_wf.memo_current(stores)
    assert cur["status"] == "completed"
    intake = {r["ticker"]: r for r in cur["intake"]}
    assert set(intake) == {"AAA", "BBB"}
    assert intake["AAA"]["state"] == "completed"
    assert intake["AAA"]["decision"] in MEMO_DECISIONS

    art = stores.artifacts.get(intake["AAA"]["artifact_id"])
    assert art["kind"] == "investment_memo"
    payload = art["payload"]
    assert validate_memo(payload).ok

    # Fixed 7-section outline, every subsection populated.
    sections = payload["body"]["sections"]
    assert list(sections)  # generation order persisted; reading order rendered
    for sec_id, _title, subs in MEMO_OUTLINE:
        assert sec_id in sections
        assert sections[sec_id]["section_thesis"].strip()
        for sub in subs:
            assert sections[sec_id]["subsections"][sub].strip()

    # Stub subsections are data-grounded, pairwise DIFFERENT prose (no canned
    # repeated sentence), each citing figures from the evidence packet.
    all_subs = [sections[sec_id]["subsections"][sub]
                for sec_id, _t, subs in MEMO_OUTLINE for sub in subs]
    assert len(set(all_subs)) == len(all_subs)
    assert all(any(ch.isdigit() for ch in text) for text in all_subs)
    # ONE offline note, in the Evidence Quality subsection only.
    offline_mentions = [t for t in all_subs if "offline" in t.lower()]
    assert offline_mentions == [sections["current_setup"]["subsections"]["evidence_quality"]]

    # Sections carry the promised key_figures/tables (new optional fields).
    assert sections["business_quality"]["key_figures"]
    scen = sections["valuation"]["tables"]["scenarios"]
    assert scen["columns"] == ["scenario", "assumption", "fair_value",
                               "return_vs_price_pct"]
    assert [r[0] for r in scen["rows"]] == ["bear", "base", "bull"]
    assert all(isinstance(r[2], (int, float)) for r in scen["rows"])
    hist = sections["financial_quality"]["tables"]["financial_history"]
    assert hist["columns"][0] == "Metric" and hist["rows"]

    # Decision varies with metrics: AAA's upside (17.6%) + all measured
    # constitution passes -> attractive; BBB's negative upside -> avoid.
    assert intake["AAA"]["decision"] == "attractive"
    assert intake["BBB"]["decision"] == "avoid"

    # Deterministic valuation anchors attached and referenced.
    val = payload["body"]["valuation"]
    assert isinstance(val["fair_value_base"], (int, float))
    assert val["method"] and val["upside_pct"] is not None

    # Monitoring plan: validated quantitative items from the supported catalog.
    plan = payload["body"]["monitoring_plan_items"]
    assert plan
    quantitative = [p for p in plan if p["tracking_mode"] == "quantitative"]
    assert quantitative and all(not p["validation_errors"] for p in quantitative)
    assert any(p["item_type"] == "kill_criterion" for p in plan)

    # Provenance is recorded; thesis/IC content never enters writer inputs.
    assert payload["body"]["provenance"]["path"] == "ic_selection"
    assert art["rendered_md"] and "## Valuation" in art["rendered_md"]
    assert "**Scenarios**" in art["rendered_md"]          # scenario table rendered
    assert "**Financial History**" in art["rendered_md"]  # history table rendered
    assert "**Decision: attractive**" in art["rendered_md"]
    assert "Base fair value" in art["rendered_md"]        # fair value vs price up front
    assert art["evidence_bundle_id"]

    # Thesis-health plan created via the parallel module when present.
    plan_row = stores.ws.query_one(
        "SELECT * FROM thesis_health_plans WHERE memo_artifact_id = ?", (art["id"],)
    )
    assert plan_row is not None


def test_memo_single_ticker_directed_provenance(stores, fake_market, constitution):
    rid = _run(memo_wf.run_memo(stores, ticker="DDD", trigger="directed",
                                provenance="directed"))
    assert stores.runs.get_run(rid)["status"] == "completed"
    # DDD has no persisted metrics in this test (no screener ran), so the memo
    # still completes deterministically and lands on needs_more_evidence.
    cur = memo_wf.memo_current(stores)
    row = next(r for r in cur["intake"] if r["ticker"] == "DDD")
    assert row["state"] == "completed"
    art = stores.artifacts.get(row["artifact_id"])
    assert art["payload"]["body"]["provenance"]["path"] == "directed"
    assert art["payload"]["body"]["decision"] == "needs_more_evidence"


# --- evidence packets --------------------------------------------------------------------


def test_evidence_packet_history_trends_peers_and_scenarios(stores, constitution):
    """The shared packet computes deterministic trends from multi-period
    history, peer comparison rows, 52-week price context, and the
    constitution check — the grounding every generation workflow shares."""
    from backend.workflows import evidence_packets as ep

    ent = stores.identity.ensure_entity("AAA", name="Alpha Corp", sector="Technology")
    years = [("2022-03-31", 30e9, 0.50), ("2023-03-31", 35e9, 0.52),
             ("2024-03-31", 40e9, 0.53), ("2025-03-31", 45e9, 0.54),
             ("2026-03-31", 50e9, 0.55)]
    for period, rev, gm in years:
        stores.financial.add_observation(ent["id"], "revenue", period, "annual", rev)
        stores.financial.add_observation(ent["id"], "gross_margin", period, "annual", gm)
    quarters = [("2024-06-30", 11.0e9), ("2024-09-30", 11.5e9), ("2024-12-31", 12.0e9),
                ("2025-03-31", 12.5e9), ("2025-06-30", 12.4e9), ("2025-09-30", 12.9e9),
                ("2025-12-31", 13.4e9), ("2026-03-31", 14.0e9)]
    for period, rev in quarters:
        stores.financial.add_observation(ent["id"], "revenue", period, "quarterly", rev)
    for metric, value in (("roic", 0.25), ("eps", 6.0), ("revenue_growth", 0.12),
                          ("fcf_yield", 0.06)):
        stores.financial.add_observation(ent["id"], metric, "2026-03-31", "annual", value)
    peer = stores.identity.ensure_entity("PER1", name="Peer One", sector="Technology")
    stores.financial.store_metrics_snapshot(
        peer["id"], {"roic": 0.15, "gross_margin": 0.40, "revenue_growth": 0.05,
                     "pe": 18.0}, "2026-03-31")
    stores.portfolio.mark_price("AAA", 100.0)
    stores.bulk.upsert_prices([
        {"ticker": "AAA", "date": f"2025-{m:02d}-{d:02d}", "close": 90.0 + m + d % 7}
        for m in range(1, 13) for d in range(1, 28)
    ])

    p = ep.build_company_packet(stores, "AAA", ent["id"])
    # Trends: revenue CAGR over 4 intervals, margin trajectory in bps, YoY quarter.
    assert p["trends"]["revenue_cagr_pct"] == pytest.approx(13.6, abs=0.1)
    assert p["trends"]["revenue_cagr_years"] == 4
    traj = p["trends"]["gross_margin_trajectory"]
    assert traj["direction"] == "expanding" and traj["change_bps"] == 500
    assert p["trends"]["latest_quarter_revenue_yoy_pct"] == pytest.approx(12.0, abs=0.1)
    # Price context from the last ~252 retained closes.
    pc = p["price_context"]
    assert pc["price"] == 100.0 and pc["high_52w"] > pc["low_52w"]
    assert pc["pct_off_52w_high"] is not None
    # Peers + constitution check (strategy-aware for ANY constitution).
    assert [q["ticker"] for q in p["peers"]] == ["PER1"]
    checks = {r["criterion_id"]: r for r in p["constitution_check"]["rows"]}
    assert checks["screen.roic_min"]["satisfied"] is True
    assert checks["ic.expected_return_min"]["satisfied"] is None  # thesis-level
    assert p["constitution_check"]["measured_all_pass"] is True
    assert ep.peer_rank(p, "roic") == (1, 1)

    # Prompt text: tight, information-dense block carrying all of the above.
    text = ep.as_prompt_text(p)
    for fragment in ("ANNUAL HISTORY", "revenue CAGR 13.6% over 4y",
                     "gross margin expanding +500bps", "PER1", "[PASS]",
                     "52w range"):
        assert fragment in text, f"missing {fragment!r}"
    assert len(text) < 3500

    # Deterministic valuation: anchors + bear/base/bull scenario rows.
    anchors = ep.deterministic_anchors(p["latest"], pc["price"])
    assert anchors["fair_value_base"] == pytest.approx(117.6)
    scenarios = ep.valuation_scenarios(anchors, p["latest"], pc["price"])
    fvs = [r[2] for r in scenarios["rows"]]
    assert fvs == sorted(fvs) and len(fvs) == 3  # bear < base < bull


def test_latest_projection_prefers_full_period_for_flow_metrics(stores):
    """Quarterly flow observations (newer period_end) must not displace the
    annual basis in latest_financials: deterministic anchors multiply EPS by
    an ANNUAL justified PE, so quarterly EPS understates fair value ~4x and
    capped nearly every thesis as a weak return profile. Point-in-time
    metrics (price) keep newest-of-any-period; TTM outranks an older annual."""
    from backend.workflows import evidence_packets as ep

    ent = stores.identity.ensure_entity("WINA")
    eid = ent["id"]
    # WINA-shaped repro: FY EPS 11.30 vs newer Q EPS 2.50 at price 395.99.
    stores.financial.add_observation(eid, "eps", "2025-09-30", "annual", 11.30)
    stores.financial.add_observation(eid, "eps", "2026-03-31", "quarterly", 2.50)
    stores.financial.add_observation(eid, "revenue", "2025-09-30", "annual", 8.5e9)
    stores.financial.add_observation(eid, "revenue", "2026-03-31", "quarterly", 2.2e9)
    stores.financial.add_observation(eid, "free_cash_flow", "2025-09-30", "annual", 9.0e8)
    stores.financial.add_observation(eid, "free_cash_flow", "2026-03-31", "quarterly", 2.0e8)
    stores.financial.add_observation(eid, "price", "2025-09-30", "annual", 350.0)
    stores.financial.add_observation(eid, "price", "2026-06-11", "quarterly", 395.99)

    latest = stores.financial.latest(eid)
    assert latest["eps"] == 11.30
    assert latest["revenue"] == 8.5e9
    assert latest["free_cash_flow"] == 9.0e8
    assert latest["price"] == 395.99  # point-in-time: newest of any period

    anchors = ep.deterministic_anchors(latest, 395.99)
    assert anchors["fair_value_base"] == pytest.approx(113.0)  # 11.30 * 10.0x floor
    assert "EPS 11.30" in anchors["method"]
    # The quarterly-EPS artifact produced -93.7%; the annual basis must not.
    assert anchors["upside_pct"] == pytest.approx(-71.5, abs=0.1)

    # A retained TTM observation is a full-period basis too and, being newer,
    # outranks the annual EPS.
    stores.financial.add_observation(eid, "eps", "2026-03-31", "ttm", 12.10)
    assert stores.financial.latest(eid)["eps"] == 12.10


# --- pipeline ---------------------------------------------------------------------------


def test_pipeline_end_to_end(stores, fake_market, constitution):
    rid = _run(pipeline.run_pipeline(stores))
    run = stores.runs.get_run(rid)
    assert run["kind"] == "pipeline"
    assert run["status"] == "completed"
    assert run["stats"] == {
        "candidates": 4,   # AAA BBB CCC FFF pass the screen
        "theses": 3,       # handoff_count 3 -> AAA BBB FFF
        "ic_passes": 2,    # FFF misses the expected-return hurdle
        "memos": 2,
    }
    steps = stores.runs.steps_for(rid)
    assert [s["name"] for s in steps] == ["screener", "thesis", "ic_review", "memo"]
    assert all(s["status"] == "completed" for s in steps)
    # Stage runs are real durable runs chained by handoffs.
    kinds = [r["kind"] for r in stores.runs.recent_runs(10)]
    for kind in ("screener", "thesis", "ic_review", "memo", "pipeline"):
        assert kind in kinds


# --- HTTP routes --------------------------------------------------------------------------


def test_routes_run_poll_select_and_directed(stores, fake_market, constitution):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.routes.workflows import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        rid = client.post("/api/workflows/screener/run").json()["run_id"]
        cur = _poll(client, "/api/workflows/screener/current")
        assert cur["status"] == "completed"
        assert _tickers(cur["top_picks"]) == ["AAA", "BBB", "FFF"]

        resp = client.post("/api/workflows/screener/selection",
                           json={"ticker": "CCC", "action": "promote"})
        assert resp.status_code == 200
        assert "CCC" in _tickers(resp.json()["top_picks"])
        resp = client.post("/api/workflows/screener/selection",
                           json={"ticker": "ZZZ", "action": "promote"})
        assert resp.status_code == 400

        runs = client.get("/api/runs").json()
        assert any(r["id"] == rid for r in runs)
        detail = client.get(f"/api/runs/{rid}").json()
        assert detail["run"]["status"] == "completed"
        assert {s["name"] for s in detail["steps"]} >= {"fetch_metrics", "evaluate"}
        assert client.get("/api/runs/run_nope").status_code == 404

        # Directed research: unknown ticker 404s; known ticker runs thesis for
        # that ticker only with directed provenance.
        assert client.post("/api/research/directed",
                           json={"ticker": "ZZZ", "capability": "thesis"}).status_code == 404
        resp = client.post("/api/research/directed",
                           json={"ticker": "DDD", "capability": "thesis"})
        assert resp.status_code == 200
        cur = _poll(client, "/api/workflows/thesis/current")
        rows = {r["ticker"]: r for r in cur["rows"]}
        assert rows["DDD"]["state"] == "completed"
        assert rows["AAA"]["state"] == "pending"  # directed run touched DDD only
        intake = stores.runs.get_workbench("thesis_intake")
        assert {"ticker": "DDD", "provenance": "directed"} in intake["items"]


def _poll(client, path, timeout_s=15.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        cur = client.get(path).json()
        if cur.get("status") in ("completed", "failed"):
            return cur
        time.sleep(0.05)
    raise AssertionError(f"timed out polling {path}")


def test_wiring_tolerates_null_optional_ic_fields():
    """AI-drafted proposals may emit ic.pass_cutoff / gate_score_blend as
    explicit null; wiring must treat null as absent, not crash (regression)."""
    from backend.domain import wiring
    from backend.domain.criteria import Criterion
    from backend.domain.guardrails import validate_proposal

    crits = [Criterion("screen.pe_max", "screen", "value", "test",
                       metric="pe", operator="<=", value=25.0)]
    proj = wiring.project_settings(
        crits, north_star="value", ic_config={"pass_cutoff": None, "gate_score_blend": None},
        universe={"name": "Russell 2000"},
    )
    assert proj["ic_review"]["settings"]["pass_cutoff"] == wiring.DEFAULT_IC_CUTOFF
    assert proj["ic_review"]["settings"]["gate_score_blend"] == wiring.DEFAULT_IC_BLEND

    payload = {"summary": "Value screen with PE cap", "north_star": "value",
               "rules": [c.to_dict() for c in crits],
               "ic": {"pass_cutoff": None, "gate_score_blend": None}}
    assert validate_proposal(payload).ok
