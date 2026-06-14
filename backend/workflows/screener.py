"""Screener workflow (CONTEXT screener stage; ADR-0036, ADR-0026).

Deterministic end to end: screening requirements and ranking math are owned by
backend.domain.criteria — AI is never consulted to pass or rank a company.
Failed companies are retained as Screener Run Evidence (ALL failure reasons,
threshold + observed) and never displayed as near-misses. The top
review_set_size candidates stay visible; the top handoff_count become Top
Picks and refresh the Thesis intake workbench without executing Thesis.
"""

from __future__ import annotations

from backend.core import opconfig
from backend.core.ai import PROMPT_VERSION
from backend.core.workspace import now_iso
from backend.data.universes import load_preset
from backend.domain import artifact_schemas, labels, metric_catalog
from backend.domain.criteria import (
    Criterion, evaluate, normalized_rank_weights, rank_criteria, screen_criteria,
)
from backend.services.market_data import MarketDataService
from backend.workflows import stage

CAPABILITY = "screener"
INTAKE_KEY = "thesis_intake"

DEFAULT_REVIEW_SET_SIZE = 50
DEFAULT_HANDOFF_COUNT = 20

# Built-in starter universe: ~30 liquid US large caps used when the active
# Constitution has no Universe Version attached.
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "JPM", "V",
    "JNJ", "WMT", "UNH", "XOM", "PG", "MA", "HD", "COST", "ORCL", "KO",
    "PEP", "ABBV", "BAC", "CRM", "AMD", "NFLX", "LIN", "MCD", "CSCO", "ADBE",
]


# --- run lifecycle ------------------------------------------------------------------

def prepare_run(stores, trigger: str = "user") -> str:
    """Create the durable run record + running workbench state synchronously so
    routes can return the run id before execution starts."""
    active = stores.constitution.active_version()
    uni = stores.constitution.active_universe()
    rid = stores.runs.start_run(
        CAPABILITY, trigger,
        constitution_version_id=active["id"] if active else None,
        universe_version_id=uni["id"] if uni else None,
    )
    stores.runs.set_workbench(CAPABILITY, {"run_id": rid, "status": "running"})
    return rid


async def run_screener(stores, trigger: str = "user") -> str:
    """Pinned contract entrypoint: full screener run, returns the run id."""
    rid = prepare_run(stores, trigger)
    await execute_run(stores, rid)
    return rid


async def execute_run(stores, run_id: str) -> None:
    """Execute a prepared screener run; operational failures finish the run as
    failed instead of raising (operational failure is never silent)."""
    try:
        await _execute(stores, run_id)
    except Exception as exc:  # noqa: BLE001 — durable run owns its failure state
        stores.runs.finish_run(run_id, "failed", error=str(exc))
        wb = stores.runs.get_workbench(CAPABILITY) or {}
        if wb.get("run_id") == run_id:
            stores.runs.set_workbench(
                CAPABILITY, {**wb, "status": "failed", "error": str(exc)}
            )


async def _execute(stores, run_id: str) -> None:
    run = stores.runs.get_run(run_id) or {}
    cv_id = run.get("constitution_version_id")
    settings = _settings(stores, cv_id)
    uni = stores.constitution.active_universe()
    universe = [t.upper() for t in ((uni or {}).get("tickers") or [])]
    if not universe and uni and uni.get("name"):
        # Universe Selection by preset name (S&P 500, Nasdaq 100, Russell 2000…)
        # resolves through the bundled constituent lists.
        try:
            universe = [t.upper() for t in load_preset(uni["name"].lower().replace(" ", "_"))]
        except (ValueError, OSError):
            universe = []
    if not universe:
        # No Constitution universe: the configured bulk-ingestion preset is the
        # default Screened Universe scope (ADR-0059, Russell 2000 by default).
        try:
            universe = [t.upper()
                        for t in load_preset(opconfig.load()["data"]["universe_default"])]
        except (ValueError, OSError):
            universe = []
    if not universe:
        universe = list(DEFAULT_UNIVERSE)
    uv_id = (uni or {}).get("id")

    # Phase 1: market data (graceful offline — no data => unevaluable, not failed).
    # After bulk bootstrap, screening ~1,900 names is local computation — the
    # screener never makes live per-company calls (ADR-0059).
    allow_fetch = stores.bulk.get_state("bootstrap_done") != "1"
    step = stores.runs.add_step(run_id, "fetch_metrics")
    metrics = await MarketDataService(stores).metrics_for(universe, allow_fetch=allow_fetch)
    unevaluable = [t for t in universe if not metrics.get(t)]
    stores.runs.finish_step(
        step, detail={"with_data": len(universe) - len(unevaluable),
                      "unevaluable": len(unevaluable)},
    )

    # Phase 2: deterministic screening — pass only if ALL screen criteria satisfied.
    step = stores.runs.add_step(run_id, "evaluate")
    evaluated: dict[str, dict] = {}
    for t in universe:
        evaluated[t] = _evaluate_company(stores, t, metrics.get(t) or {}, settings["screens"])
    candidates = [t for t in universe if evaluated[t]["passed"]]
    stores.runs.finish_step(
        step, detail={"passed": len(candidates), "failed": len(universe) - len(candidates)},
    )

    # Phase 3: ranking over passing candidates only.
    step = stores.runs.add_step(run_id, "rank")
    ranked = _rank(candidates, metrics, settings["ranks"])
    stores.runs.finish_step(step, detail={"ranked": len(ranked)})

    bundle_id = stores.evidence.freeze_bundle({
        "kind": "screener_run",
        "run_id": run_id,
        "constitution_version": cv_id,
        "universe_version": uv_id,
        "prompt_version": PROMPT_VERSION,
        "metrics_evidence": {
            "tickers_evaluated": len(universe),
            "tickers_with_data": sorted(t for t in universe if t not in unevaluable),
            "unevaluable": sorted(unevaluable),
        },
    })

    # Phase 4: review set + Top Picks + snapshot artifacts + typed result rows.
    step = stores.runs.add_step(run_id, "snapshot")
    review = ranked[: settings["review_set_size"]]
    rank_order = [r["ticker"] for r in review]
    state = stage.new_state(settings["handoff_count"])
    selection = stage.compute_selection(rank_order, state)
    sel_order = {t: i + 1 for i, t in enumerate(selection)}
    rows: dict[str, dict] = {}
    for i, r in enumerate(review):
        t = r["ticker"]
        ev = evaluated[t]
        m = metrics.get(t) or {}
        explanation = _ranking_explanation(i + 1, len(ranked), r["components"])
        key_fin = [
            {"metric": k, "label": labels.metric_label(k), "value": m.get(k),
             "display": labels.format_metric_value(k, m.get(k))}
            for k in settings["key_financials"]
        ]
        # Human milestone/markdown summary — never raw criterion ids.
        summary_md = labels.screener_summary(
            ev["pass_evidence"], rank=i + 1, total=len(ranked),
            components=r["components"],
        )
        kernel = artifact_schemas.make_kernel(
            "screener_snapshot", t, ev.get("entity_id"), cv_id, bundle_id, now_iso(),
        )
        payload = {**kernel, "body": {
            "rank": i + 1,
            "score": r["score"],
            "summary": summary_md,
            "pass_evidence": ev["pass_evidence"],
            "ranking_components": r["components"],
            "ranking_explanation": explanation,
            "key_financials": key_fin,
            "top_picks": t in sel_order,
        }}
        payload["validation"] = artifact_schemas.validate_artifact(payload).to_dict()
        aid = stores.artifacts.save_artifact(
            "screener_snapshot", payload, ticker=t, entity_id=ev.get("entity_id"),
            run_id=run_id, rendered_md=summary_md, evidence_bundle_id=bundle_id,
            constitution_version_id=cv_id,
        )
        stores.artifacts.save_screener_result(
            run_id, t, passed=True, entity_id=ev.get("entity_id"), rank=i + 1,
            score=r["score"], ranking_components=r["components"],
            pass_evidence=ev["pass_evidence"], selected=t in sel_order,
            selection_order=sel_order.get(t), snapshot_artifact_id=aid,
        )
        rows[t] = {
            "ticker": t,
            "company_name": m.get("company_name") or t,
            "sector": m.get("sector"),
            "price": m.get("price"),
            "rank": i + 1,
            "score": r["score"],
            "key_financials": key_fin,
            "ranking_explanation": explanation,
            "pass_evidence": ev["pass_evidence"],
            "snapshot_artifact_id": aid,
        }
    # Passing candidates beyond the review set: retained, not shown.
    for i, r in enumerate(ranked[len(review):], start=len(review)):
        t = r["ticker"]
        stores.artifacts.save_screener_result(
            run_id, t, passed=True, entity_id=evaluated[t].get("entity_id"),
            rank=i + 1, score=r["score"], ranking_components=r["components"],
            pass_evidence=evaluated[t]["pass_evidence"],
        )
    # Failed companies: Screener Run Evidence with ALL failure reasons.
    for t in universe:
        if not evaluated[t]["passed"]:
            stores.artifacts.save_screener_result(
                run_id, t, passed=False, entity_id=evaluated[t].get("entity_id"),
                fail_reasons=evaluated[t]["fail_reasons"],
            )
    stores.runs.finish_step(step, detail={"snapshots": len(review)})

    summary = {"universe_size": len(universe), "passed": len(candidates), "shown": len(review)}
    stores.runs.set_workbench(CAPABILITY, {
        "run_id": run_id,
        "status": "completed",
        "summary": summary,
        "rank_order": rank_order,
        "rows": rows,
        "selection_state": state,
        "evidence_bundle_id": bundle_id,
    })
    _refresh_thesis_intake(stores, selection, run_id, preserve_directed=False)
    stores.runs.finish_run(run_id, "completed", stats={
        **summary, "unevaluable": len(unevaluable), "top_picks": len(selection),
    })


# --- reads + selection ---------------------------------------------------------------

def screener_current(stores) -> dict:
    """Current screener stage view per the API contract. Never spends AI."""
    wb = stores.runs.get_workbench(CAPABILITY)
    status = stage.stage_status(wb)
    empty_summary = {"universe_size": 0, "passed": 0, "shown": 0}
    if not wb:
        return {"run": None, "summary": empty_summary, "top_picks": [], "remaining": [],
                "status": "idle"}
    run = stores.runs.get_run(wb.get("run_id"))
    if status != "completed":
        return {"run": run, "summary": wb.get("summary") or empty_summary,
                "top_picks": [], "remaining": [], "status": status,
                "error": wb.get("error")}
    rank_order = wb.get("rank_order") or []
    rows = wb.get("rows") or {}
    selection = stage.compute_selection(rank_order, wb.get("selection_state") or {})
    order = {t: i + 1 for i, t in enumerate(selection)}

    def row(t: str) -> dict:
        r = dict(rows.get(t) or {"ticker": t})
        r["selected"] = t in order
        r["selection_order"] = order.get(t)
        return r

    selected_block, remaining_block = stage.partition(rank_order, selection)
    return {
        "run": run,
        "summary": wb.get("summary") or empty_summary,
        "top_picks": [row(t) for t in selected_block],
        "remaining": [row(t) for t in remaining_block],
        "status": "completed",
    }


def screener_select(stores, ticker: str, action: str) -> dict:
    """Promote/dismiss a candidate in the current Top Picks. Never changes
    rank, snapshot artifacts, or stored pass/fail evidence."""
    wb = stores.runs.get_workbench(CAPABILITY)
    if not wb or wb.get("status") != "completed":
        raise ValueError("no completed screener stage output to select against")
    rank_order = wb.get("rank_order") or []
    state, selection = stage.apply_action(
        stores, CAPABILITY, wb.get("run_id"), wb.get("selection_state") or stage.new_state(0),
        rank_order, ticker, action, promotable=set(rank_order),
    )
    wb["selection_state"] = state
    stores.runs.set_workbench(CAPABILITY, wb)
    order = {t: i + 1 for i, t in enumerate(selection)}
    for t in rank_order:
        stores.artifacts.set_screener_selection(wb["run_id"], t, t in order, order.get(t))
    _refresh_thesis_intake(stores, selection, wb.get("run_id"), preserve_directed=True)
    return screener_current(stores)


def _refresh_thesis_intake(stores, selection: list[str], run_id: str | None,
                           preserve_directed: bool) -> None:
    """Handoff: refresh Thesis intake without executing it. A new screener run
    replaces the intake; selection edits preserve directed-research additions."""
    items = [{"ticker": t, "provenance": "screener"} for t in selection]
    if preserve_directed:
        existing = stores.runs.get_workbench(INTAKE_KEY) or {}
        for item in existing.get("items") or []:
            if item.get("provenance") == "directed" and item.get("ticker") not in set(selection):
                items.append(item)
    stores.runs.set_workbench(INTAKE_KEY, {
        "source": "screener",
        "source_run_id": run_id,
        "tickers": [i["ticker"] for i in items],
        "items": items,
    })


# --- deterministic evaluation/ranking --------------------------------------------------

def _settings(stores, cv_id: str | None) -> dict:
    """Screener settings projection of the active Constitution, with funnel
    defaults when nothing is wired (review item already raised at activation)."""
    proj = stores.constitution.projection(CAPABILITY, cv_id) if cv_id else None
    s = (proj or {}).get("settings") or {}
    screens = [Criterion.from_dict(d) for d in s.get("requirements") or []]
    ranks = [Criterion.from_dict(d) for d in s.get("ranking_blend") or []]
    if proj is None and cv_id:
        crits = stores.constitution.criteria_objects(cv_id)
        screens, ranks = screen_criteria(crits), rank_criteria(crits)
    key_financials = s.get("key_financials")
    if not key_financials:
        seen: list[str] = []
        for c in ranks + screens:
            if c.metric and c.metric not in seen and metric_catalog.is_supported(c.metric):
                seen.append(c.metric)
        key_financials = seen[:6]
    return {
        "screens": screens,
        "ranks": ranks,
        "review_set_size": int(s.get("review_set_size") or DEFAULT_REVIEW_SET_SIZE),
        "handoff_count": int(s.get("handoff_count") or DEFAULT_HANDOFF_COUNT),
        "key_financials": key_financials,
    }


def _evaluate_company(stores, ticker: str, metrics: dict, screens: list[Criterion]) -> dict:
    """Evaluate ALL screen criteria; a company passes only if every criterion is
    satisfied. Unevaluable counts as not-passing with reason 'missing data'.
    All failure reasons are recorded, not just the first."""
    entity_id = metrics.get("entity_id")
    if metrics and not entity_id:
        ent = stores.identity.ensure_entity(
            ticker, name=metrics.get("company_name"), sector=metrics.get("sector"),
        )
        entity_id = ent["id"]
    pass_evidence: list[dict] = []
    fail_reasons: list[dict] = []
    for c in screens:
        result = evaluate(c, metrics.get(c.metric) if metrics else None)
        if result.satisfied is True:
            pass_evidence.append(_evidence_row(c, result.observed))
        else:
            fail_reasons.append({
                **_evidence_row(c, result.observed),
                "reason": result.reason or f"{labels.describe_criterion(c)} not met",
            })
    passed = bool(metrics) and not fail_reasons
    if not metrics:
        fail_reasons = [{
            **_evidence_row(c, None), "reason": "missing data",
        } for c in screens] or [{"criterion": None, "metric": None, "threshold": None,
                                 "observed": None, "reason": "missing data"}]
    return {"passed": passed, "pass_evidence": pass_evidence,
            "fail_reasons": fail_reasons, "entity_id": entity_id}


def _rank(candidates: list[str], metrics: dict, ranks: list[Criterion]) -> list[dict]:
    """Score = weighted sum of percentile-normalized observed values across the
    passing candidates. Lower-is-better metrics (operator < / <=) invert."""
    weights = normalized_rank_weights(ranks)
    values_by_crit: dict[str, list[float]] = {}
    for c in ranks:
        values_by_crit[c.criterion_id] = [
            float(v) for t in candidates
            if isinstance((v := (metrics.get(t) or {}).get(c.metric)), (int, float))
        ]
    out = []
    for t in candidates:
        components, score = [], 0.0
        for c in ranks:
            w = weights.get(c.criterion_id, 0.0)
            v = (metrics.get(t) or {}).get(c.metric)
            if isinstance(v, (int, float)):
                pct = _percentile(values_by_crit[c.criterion_id], float(v),
                                  invert=c.operator in ("<", "<="))
                contribution = round(w * pct / 100.0, 4)
            else:
                pct, contribution = None, 0.0
            components.append({
                "criterion_id": c.criterion_id, "metric": c.metric,
                "label": labels.metric_label(c.metric), "observed": v,
                "percentile": pct, "weight": round(w, 4), "contribution": contribution,
            })
            score += contribution
        out.append({"ticker": t, "score": round(score, 4), "components": components})
    out.sort(key=lambda r: (-r["score"], r["ticker"]))
    return out


def _percentile(values: list[float], v: float, invert: bool) -> float:
    if not values:
        return 50.0
    below = sum(1 for x in values if x < v)
    equal = sum(1 for x in values if x == v)
    pct = (below + 0.5 * equal) / len(values)
    if invert:
        pct = 1.0 - pct
    return round(pct * 100.0, 1)


def _ranking_explanation(rank: int, total: int, components: list[dict]) -> str:
    """Deterministic ranking explanation grounded only in ranking components,
    in product language (metric display names, never raw ids)."""
    def name(c: dict) -> str:
        return c.get("label") or labels.metric_label(c.get("metric"))

    judged = [c for c in components if c.get("percentile") is not None]
    if not judged:
        return (f"Ranked #{rank} of {total}: no ranking priorities evaluable; "
                f"equal-weight ordering applied.")
    best = max(judged, key=lambda c: c["percentile"])
    worst = min(judged, key=lambda c: c["percentile"])
    parts = [
        f"Ranked #{rank} of {total}: strongest on {name(best)} "
        f"({best['percentile']:.0f}th pct, weight {best['weight'] * 100:.0f}%)"
    ]
    if worst is not best:
        parts.append(f"weakest on {name(worst)} ({worst['percentile']:.0f}th pct)")
    missing = [name(c) for c in components if c.get("percentile") is None]
    if missing:
        parts.append("missing data for " + ", ".join(missing))
    return "; ".join(parts) + "."


def _evidence_row(c: Criterion, observed) -> dict:
    """One pass-evidence/fail-reason row: raw fields kept for audit, display
    fields added so the UI never maps criterion ids or formats decimals."""
    return {
        "criterion": c.criterion_id, "metric": c.metric,
        "threshold": f"{c.operator} {c.value}", "observed": observed,
        "label": labels.metric_label(c.metric) if c.metric else c.criterion_id,
        "rule": labels.describe_criterion(c),
        "threshold_display": labels.threshold_display(c.metric, c.operator, c.value),
        "observed_display": (None if observed is None
                             else labels.format_metric_value(c.metric, observed)),
    }
