"""Thesis workflow (CONTEXT thesis stage; ADR-0036, ADR-0034).

Generates one Completed Thesis artifact per intake ticker (ONE deep model call
per ticker; existing completed theses in the current run context are never
regenerated — a re-run resumes). Generation grounds on the shared company
evidence packet (workflows.evidence_packets): multi-period history, computed
trends, peer rows, price context, and the active-constitution check — plus
deterministic valuation anchors the model must reconcile with, so body.price,
fair_value, and valuation_method are always populated. Outputs validate
against the fixed Thesis Research Scope schema; invalid outputs become
rejected provenance, never artifacts. Operational failures retry up to 3
attempts then become a visible failed state excluded from selection
(operational failure ≠ investment judgment). Selection ranks completed theses
by expected return with the Thesis Selection Score Cap for weak/unsupported
return profiles.
"""

from __future__ import annotations

import asyncio
import json

from backend.core import web_research
from backend.core.ai import PROMPT_VERSION, get_ai
from backend.core.workspace import now_iso
from backend.domain import artifact_schemas
from backend.workflows import evidence_packets as ep
from backend.workflows import stage

CAPABILITY = "thesis"
INTAKE_KEY = "thesis_intake"
IC_INTAKE_KEY = "ic_intake"

DEFAULT_SELECTION_COUNT = 10
DEFAULT_RETURN_CAP_THRESHOLD = 5.0
GENERATION_CONCURRENCY = 3
MAX_ATTEMPTS = 3

SYSTEM = (
    "You are the FundOps thesis analyst writing for an institutional investment "
    "committee. Produce a Completed Thesis grounded ONLY in the provided evidence "
    "packet — never invent data. Every research scope answer must cite specific "
    "figures (values, trends, peer comparisons) from the packet; generic filler like "
    "'strong fundamentals' without numbers is rejected. Quantify return potential: "
    "the components must sum approximately to expected_return_pct, and fair_value "
    "must reconcile with the deterministic valuation anchors you are given."
)

SHAPE = (
    '{"summary": "2-3 sentence thesis", '
    '"scope": {"why_opportunity_exists": str, "why_mispriced": str, "return_sources": str, '
    '"constitution_fit": str, "path_or_catalyst": str, "key_risk": str, '
    '"evidence_freshness": str}, '
    '"return_potential": {"expected_return_pct": number, '
    '"components": {"valuation_gap": number?, "growth": number?, "margin_expansion": number?, '
    '"capital_returns": number?, "multiple_rerating": number?}, '
    '"fair_value": number|null, "valuation_method": str|null}, '
    '"evidence_notes": [str]}'
)


# --- run lifecycle ------------------------------------------------------------------

def prepare_run(stores, trigger: str = "user") -> str:
    active = stores.constitution.active_version()
    rid = stores.runs.start_run(
        CAPABILITY, trigger, constitution_version_id=active["id"] if active else None,
    )
    wb = stores.runs.get_workbench(CAPABILITY) or {}
    stores.runs.set_workbench(CAPABILITY, {**wb, "run_id": rid, "status": "running"})
    return rid


async def run_thesis(stores, trigger: str = "user", tickers: list[str] | None = None) -> str:
    """Pinned contract entrypoint: generate theses for the intake (or the given
    subset, e.g. directed research) and refresh IC intake."""
    rid = prepare_run(stores, trigger)
    await execute_run(stores, rid, tickers=tickers)
    return rid


async def execute_run(stores, run_id: str, tickers: list[str] | None = None) -> None:
    try:
        await _execute(stores, run_id, tickers)
    except Exception as exc:  # noqa: BLE001
        stores.runs.finish_run(run_id, "failed", error=str(exc))
        wb = stores.runs.get_workbench(CAPABILITY) or {}
        if wb.get("run_id") == run_id:
            stores.runs.set_workbench(
                CAPABILITY, {**wb, "status": "failed", "error": str(exc)}
            )


async def _execute(stores, run_id: str, only: list[str] | None) -> None:
    run = stores.runs.get_run(run_id) or {}
    cv_id = run.get("constitution_version_id")
    active = stores.constitution.active_version() or {}
    proj = stores.constitution.projection(CAPABILITY, cv_id) if cv_id else None
    settings = (proj or {}).get("settings") or {}
    ctx = {
        "cv_id": cv_id,
        "emphasis": settings.get("research_emphasis") or active.get("north_star") or "",
        "cap_threshold": float(settings.get("return_cap_threshold")
                               or DEFAULT_RETURN_CAP_THRESHOLD),
        "run_id": run_id,
    }
    selection_count = int(settings.get("selection_count") or DEFAULT_SELECTION_COUNT)
    only_set = {t.upper() for t in only} if only else None

    intake = stores.runs.get_workbench(INTAKE_KEY) or {}
    items = intake.get("items") or [
        {"ticker": t, "provenance": "screener"} for t in intake.get("tickers") or []
    ]
    order = [str(i["ticker"]).upper() for i in items]
    prior_rows = {
        r["ticker"]: r for r in (stores.runs.get_workbench(CAPABILITY) or {}).get("rows") or []
    }

    rows: dict[str, dict] = {}
    targets: list[str] = []
    for t in order:
        prior = prior_rows.get(t)
        if prior and prior.get("state") == "completed" and prior.get("artifact_id"):
            rows[t] = prior  # completed artifacts survive; never regenerate in-context
        elif only_set is None or t in only_set:
            targets.append(t)
        else:
            rows[t] = prior or {"ticker": t, "state": "pending"}

    sem = asyncio.Semaphore(GENERATION_CONCURRENCY)

    async def generate(ticker: str) -> dict:
        async with sem:
            return await _generate_one(stores, ticker, ctx)

    for row in await asyncio.gather(*(generate(t) for t in targets)):
        rows[row["ticker"]] = row

    # Thesis Selection Ranking: completed theses by expected return; capped
    # theses ranked last and never auto-selected. Ties break by handoff order.
    handoff_index = {t: i for i, t in enumerate(order)}

    def sort_key(r: dict):
        exp = r.get("expected_return_pct")
        return (-(exp if isinstance(exp, (int, float)) else 0.0),
                handoff_index.get(r["ticker"], 999))

    completed = [rows[t] for t in order if rows.get(t, {}).get("state") == "completed"]
    eligible_rows = sorted([r for r in completed if not r.get("capped")], key=sort_key)
    capped_rows = sorted([r for r in completed if r.get("capped")], key=sort_key)
    other_rows = [rows[t] for t in order if rows.get(t, {}).get("state") != "completed"]
    rank_order = [r["ticker"] for r in eligible_rows + capped_rows]
    eligible = [r["ticker"] for r in eligible_rows]

    state = stage.new_state(selection_count)
    selection = stage.compute_selection(rank_order, state, set(eligible))
    stores.runs.set_workbench(CAPABILITY, {
        "run_id": run_id,
        "status": "completed",
        "rows": eligible_rows + capped_rows + other_rows,
        "rank_order": rank_order,
        "eligible": eligible,
        "selection_state": state,
        "selection_count": selection_count,
    })
    _refresh_ic_intake(stores, selection, rows, run_id)
    failed = [r for r in other_rows if r.get("state") == "failed"]
    stores.runs.finish_run(run_id, "completed", stats={
        "intake": len(order), "generated": len(targets),
        "completed": len(completed), "failed": len(failed),
        "capped": len(capped_rows), "selected": len(selection),
    })


async def _generate_one(stores, ticker: str, ctx: dict) -> dict:
    """One thesis: ONE deep model call per attempt; validation failures retry
    once with errors appended, then become rejected provenance."""
    run_id = ctx["run_id"]
    step_id = stores.runs.add_step(run_id, "thesis", ticker)
    ent = stores.identity.ensure_entity(ticker)
    packet = ep.build_company_packet(stores, ticker, ent["id"])
    metrics = packet["latest"]
    price = packet["price_context"].get("price")
    anchors = ep.deterministic_anchors(metrics, price)
    bundle_id = stores.evidence.freeze_bundle({
        "kind": "thesis",
        "ticker": ticker,
        "constitution_version": ctx["cv_id"],
        "metrics_used": sorted(k for k, v in metrics.items() if v is not None),
        "history_metrics": sorted(packet["history"]),
        "peers": [p["ticker"] for p in packet["peers"]],
        "prompt_version": PROMPT_VERSION,
    })
    stub = _stub_thesis(packet, anchors)

    # Optional web augmentation (Settings toggle): recent context filings can't
    # carry. Supplementary signal only — figures still come from the packet.
    web = await web_research.search(
        f"{packet['identity']['name']} {ticker} stock investment outlook news", 4,
        ticker=ticker)
    web_block, web_sources = (web_research.context_block(web["results"])
                              if web["results"] else ("", []))

    base_user = (
        f"Strategy north star / research emphasis: {ctx['emphasis'] or 'none stated'}\n\n"
        f"Company evidence packet (retained platform data — your ONLY source of figures):\n"
        f"{ep.as_prompt_text(packet)}\n\n"
        + (f"Recent web context (SUPPLEMENTARY ONLY — never a source of figures; "
           f"cite any web-derived claim as [Wn]):\n{web_block}\n\n" if web_block else "")
        + f"Deterministic valuation anchors (computed):\n{json.dumps(anchors)}\n\n"
        "Write the Completed Thesis:\n"
        "- Answer EVERY fixed research scope question with 2-4 substantive sentences "
        "citing specific figures from the packet (levels, trends, peer position, "
        "constitution-check outcomes).\n"
        "- summary: 3-5 sentences stating the argument, the key numbers behind it, "
        "and the return math.\n"
        "- return_potential: decompose expected_return_pct into components that sum "
        "to it; set fair_value and valuation_method anchored on the deterministic "
        "valuation anchors above (state the arithmetic — adjust only with explicit "
        "packet-grounded justification).\n"
        "- evidence_notes: the concrete data points and gaps that most shaped your view."
    )

    last_error: str | None = None
    validation_errors: list[str] = []
    validation_failures = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            stores.runs.retry_step(step_id)
        user = base_user
        if validation_errors:
            user += ("\n\nYour previous output failed validation; fix exactly these "
                     "errors:\n- " + "\n- ".join(validation_errors))
        try:
            result = await get_ai().complete_json(
                CAPABILITY, SYSTEM, user, SHAPE, tier="deep", run_id=run_id, stub=stub,
            )
        except Exception as exc:  # noqa: BLE001 — operational failure, retry
            last_error = f"model call failed: {exc}"
            continue
        payload = _build_payload(ticker, ent, ctx, bundle_id, result, price, anchors)
        if web_sources:
            payload["body"]["web_sources"] = web_sources
        vr = artifact_schemas.validate_thesis(payload)
        if vr.ok:
            payload["validation"] = vr.to_dict()
            aid = stores.artifacts.save_artifact(
                "thesis", payload, ticker=ticker, entity_id=ent["id"], run_id=run_id,
                rendered_md=_render_md(ticker, payload, packet),
                evidence_bundle_id=bundle_id,
                constitution_version_id=ctx["cv_id"],
            )
            rp = payload["body"]["return_potential"]
            expected = rp.get("expected_return_pct")
            capped = (
                not rp.get("components")
                or (isinstance(expected, (int, float)) and expected < ctx["cap_threshold"])
                or bool(vr.warnings)
            )
            stores.runs.finish_step(step_id, "completed", detail={
                "artifact_id": aid, "expected_return_pct": expected, "capped": capped,
            })
            return {
                "ticker": ticker, "company_name": ent.get("name") or ticker,
                "state": "completed", "artifact_id": aid, "price": price,
                "fair_value": rp.get("fair_value"), "expected_return_pct": expected,
                "capped": capped, "summary": payload["body"].get("summary"),
                "return_components": rp.get("components") or {},
            }
        validation_failures += 1
        last_error = "validation failed: " + "; ".join(vr.errors)
        if validation_failures >= 2:
            # Rejected output is retained as provenance, never an artifact (ADR-0034).
            stores.ops.record_provenance(
                step=CAPABILITY, kind="validation", run_id=run_id,
                validation=vr.to_dict(),
                rejected_output=json.dumps(result, default=str)[:4000],
            )
            break
        validation_errors = vr.errors
    stores.runs.finish_step(step_id, "failed", error=last_error or "thesis generation failed")
    return {"ticker": ticker, "company_name": ent.get("name") or ticker,
            "state": "failed", "error": last_error}


def _build_payload(ticker: str, ent: dict, ctx: dict, bundle_id: str, result: dict,
                   price: float | None, anchors: dict) -> dict:
    result = result if isinstance(result, dict) else {}
    rp_in = result.get("return_potential") or {}
    components = {
        k: v for k, v in (rp_in.get("components") or {}).items()
        if k in artifact_schemas.THESIS_RETURN_COMPONENTS and _num(v) is not None
    }
    expected = _num(rp_in.get("expected_return_pct"))
    # fair_value/valuation_method/price are ALWAYS populated (deterministic
    # fallback chain: model -> anchors -> expected-return applied to price) so
    # readers never render empty valuation fields.
    fair_value = _num(rp_in.get("fair_value"))
    method = str(rp_in["valuation_method"]) if rp_in.get("valuation_method") else None
    if fair_value is None:
        fair_value = anchors.get("fair_value_base")
        method = anchors.get("method")
    if fair_value is None and price is not None and expected is not None:
        fair_value = price * (1 + expected / 100.0)
        method = "expected-return applied to current price"
    rp = {
        "expected_return_pct": expected,
        "components": {k: round(_num(v), 2) for k, v in components.items()},
        "fair_value": round(fair_value, 2) if fair_value is not None else None,
        "valuation_method": method,
    }
    kernel = artifact_schemas.make_kernel(
        "thesis", ticker, ent.get("id"), ctx["cv_id"], bundle_id, now_iso(),
    )
    return {**kernel, "body": {
        "summary": str(result.get("summary") or "").strip(),
        "scope": {f: str((result.get("scope") or {}).get(f) or "").strip()
                  for f in artifact_schemas.THESIS_SCOPE_FIELDS},
        "price": price,
        "return_potential": rp,
        "evidence_notes": [str(n) for n in result.get("evidence_notes") or []],
    }}


def _num(v) -> float | None:
    try:
        return None if v is None or isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None


def _stub_thesis(packet: dict, anchors: dict) -> dict:
    """Deterministic offline thesis derived from the shared evidence packet:
    every scope answer cites actual levels, trends, peer position, and
    constitution outcomes, so the funnel reads plausibly (and tests
    deterministically) without an API key. The offline-mode note appears in
    evidence_freshness only."""
    latest = packet["latest"]
    ident = packet["identity"]
    name = ident["name"]
    sector = ident.get("sector") or "the retained universe"
    price = packet["price_context"].get("price")
    fcf_yield = latest.get("fcf_yield") or 0.0
    growth = latest.get("revenue_growth") or 0.0
    components: dict[str, float] = {}
    if fcf_yield:
        components["valuation_gap"] = round(fcf_yield * 100.0, 1)
    if growth:
        components["growth"] = round(min(growth * 100.0, 25.0), 1)
    expected = round(sum(components.values()), 1)
    fair_value = anchors.get("fair_value_base")
    method = anchors.get("method")
    if fair_value is None and price:
        fair_value = round(price * (1 + expected / 100.0), 2)
        method = "expected-return applied to current price"

    fy, g = f"{fcf_yield * 100:.1f}%", f"{growth * 100:.1f}%"
    gm_phrase = ep.trend_phrase(packet, "gross_margin")
    roic_rank = ep.peer_rank(packet, "roic")
    rank_sentence = (
        f"ROIC of {ep.fmt_value('roic', latest.get('roic'))} ranks above "
        f"{roic_rank[0]} of {roic_rank[1]} retained {sector} peers."
        if roic_rank else
        f"No same-sector peer rows are retained, so the "
        f"{ep.fmt_value('roic', latest.get('roic'))} ROIC level itself carries "
        "the quality comparison."
    )
    cc = packet["constitution_check"]
    measured = [r for r in cc["rows"] if r["satisfied"] is not None]
    passes = [r for r in measured if r["satisfied"]]
    misses = [r for r in measured if not r["satisfied"]]
    strongest = "; ".join(f"{r['rule']} (observed {r['observed_display']})"
                          for r in passes[:2])
    fit = (f"Meets {len(passes)} of {len(measured)} measurable constitution criteria"
           + (f", including {strongest}" if strongest else "")
           + ". "
           + (("Misses: " + "; ".join(
               f"{r['rule']} (observed {r['observed_display']})" for r in misses[:2])
               + ".") if misses
              else f"No measurable criterion of the active constitution is missed; "
                   f"{len(cc['rows']) - len(measured)} criterion(s) are thesis-level "
                   "and judged at IC."))
    cagr = packet["trends"].get("revenue_cagr_pct")
    growth_clause = (f"a {cagr}% revenue CAGR over the retained history"
                     if cagr is not None else f"reported revenue growth of {g}")
    valuation_clause = (
        f"The deterministic anchor puts fair value at {fair_value:,.2f} "
        f"({method}), {((fair_value - price) / price * 100):+.1f}% versus the "
        f"current {price:,.2f}." if fair_value and price else
        "No deterministic fair-value anchor is computable from the retained data."
    )
    pe = latest.get("pe")
    pricing_clause = (
        f"At {pe:.1f}x earnings the market capitalizes little of {growth_clause}."
        if isinstance(pe, (int, float)) else
        f"The current price embeds limited credit for {growth_clause}."
    )
    de = latest.get("debt_equity")
    leverage_clause = (
        f"Debt/equity of {de:.2f} keeps balance-sheet risk "
        f"{'modest' if de <= 1.0 else 'elevated if margins slip'}."
        if isinstance(de, (int, float)) else
        "Leverage is unmeasured in the retained data, which widens the risk band."
    )
    n_annual = max((len(s.get("annual") or []) for s in packet["history"].values()),
                   default=0)
    n_quarterly = max((len(s.get("quarterly") or []) for s in packet["history"].values()),
                      default=0)
    latest_period = next(
        (s["annual"][0]["period_end"] for s in packet["history"].values()
         if s.get("annual")), None,
    )

    return {
        "summary": (
            f"{name} offers an estimated {expected:.1f}% return built from a {fy} "
            f"free-cash-flow yield and {g} revenue growth. {valuation_clause} "
            f"{rank_sentence} The thesis holds as long as the margin structure "
            f"({ep.fmt_value('gross_margin', latest.get('gross_margin'))} gross) and "
            f"the growth baseline persist."
        ),
        "scope": {
            "why_opportunity_exists": (
                f"{name} pairs a {fy} free-cash-flow yield with {g} revenue growth, "
                f"a combination the current price does not fully capitalize. "
                f"{gm_phrase.capitalize()}. {rank_sentence}"
            ),
            "why_mispriced": (
                f"{pricing_clause} {valuation_clause} The gap suggests the market "
                "is weighting near-term noise over the retained cash-flow profile."
            ),
            "return_sources": (
                f"Expected return of {expected:.1f}% decomposes into "
                f"{components.get('valuation_gap', 0.0):.1f}% from the cash-flow "
                f"yield and {components.get('growth', 0.0):.1f}% from revenue "
                f"growth. No multiple re-rating or margin expansion beyond the "
                "retained baseline is assumed, which keeps the decomposition "
                "conservative."
            ),
            "constitution_fit": fit,
            "path_or_catalyst": (
                f"The path is continued reported execution: holding gross margin near "
                f"{ep.fmt_value('gross_margin', latest.get('gross_margin'))} and revenue "
                f"growth near {g} over the next 2-4 quarters. "
                + (f"{n_quarterly} retained quarterly periods allow quarterly "
                   "confirmation of the path." if n_quarterly else
                   "With no quarterly observations retained, annual filings are the "
                   "confirmation cadence.")
            ),
            "key_risk": (
                f"Growth deceleration below {g} or compression of the "
                f"{ep.fmt_value('gross_margin', latest.get('gross_margin'))} gross margin "
                f"would undercut both return components at once. {leverage_clause}"
            ),
            "evidence_freshness": (
                f"Latest retained observations dated {latest_period or 'n/a'}; "
                f"{n_annual} annual and {n_quarterly} quarterly period(s) retained. "
                "Generated in deterministic offline mode (no model provider "
                "configured)."
            ),
        },
        "return_potential": {
            "expected_return_pct": expected,
            "components": components,
            "fair_value": fair_value,
            "valuation_method": method,
        },
        "evidence_notes": list(packet["data_quality_notes"]),
    }


_KEY_FIGURE_METRICS = ("revenue", "revenue_growth", "gross_margin", "operating_margin",
                       "roic", "fcf_yield", "eps", "debt_equity")


def _render_md(ticker: str, payload: dict, packet: dict) -> str:
    body = payload.get("body") or {}
    rp = body.get("return_potential") or {}
    latest = packet["latest"]
    trends = packet["trends"]
    lines = [f"# Thesis: {ticker}", "", body.get("summary", ""), ""]

    rows = [(m, ep.fmt_value(m, latest[m]), _trend_cell(m, trends))
            for m in _KEY_FIGURE_METRICS if latest.get(m) is not None]
    if rows:
        lines += ["## Key Figures", "", "| Metric | Value | Trend |", "|---|---|---|"]
        lines += [f"| {ep.display_name(m)} | {v} | {t} |" for m, v, t in rows]
        lines.append("")

    lines += ["## Research Scope", ""]
    for field in artifact_schemas.THESIS_SCOPE_FIELDS:
        lines.append(f"**{field.replace('_', ' ').title()}** — "
                     f"{(body.get('scope') or {}).get(field, '')}")
        lines.append("")
    lines += ["## Return Potential", ""]
    price = body.get("price")
    if price is not None:
        lines.append(f"Price {price:,.2f}"
                     + (f" → fair value {rp['fair_value']:,.2f}"
                        if isinstance(rp.get("fair_value"), (int, float)) else "")
                     + (f" ({rp['valuation_method']})"
                        if rp.get("valuation_method") else ""))
        lines.append("")
    lines.append(f"Expected return: {rp.get('expected_return_pct')}%")
    for k, v in (rp.get("components") or {}).items():
        lines.append(f"- {k.replace('_', ' ')}: {v}%")
    return "\n".join(lines)


def _trend_cell(metric: str, trends: dict) -> str:
    if metric == "revenue" and trends.get("revenue_cagr_pct") is not None:
        return f"{trends['revenue_cagr_pct']:+.1f}% CAGR/{trends['revenue_cagr_years']}y"
    traj = trends.get(f"{metric}_trajectory")
    if traj:
        return f"{traj['direction']} {traj['change_bps']:+d}bps/{traj['periods']}y"
    return "single period"


# --- reads + selection ---------------------------------------------------------------

def _intake_rows(stores) -> list[dict]:
    """Handed-off Screener Top Picks shown as pending Thesis Intake rows before
    Run Thesis — a completed Screener Run makes the default picks visible here
    without a separate send (CONTEXT: Screener→Thesis handoff)."""
    intake = stores.runs.get_workbench(INTAKE_KEY) or {}
    items = intake.get("items") or [
        {"ticker": t, "provenance": "screener"} for t in intake.get("tickers") or []
    ]
    order = [str(i["ticker"]).upper() for i in items]
    if not order:
        return []
    prices = stores.portfolio.prices()
    rows = []
    for t in order:
        ent = stores.identity.resolve_ticker(t) or {}
        rows.append({
            "ticker": t, "company_name": ent.get("name") or t,
            "state": "pending", "price": prices.get(t),
        })
    return rows


def thesis_current(stores) -> dict:
    wb = stores.runs.get_workbench(CAPABILITY)
    status = stage.stage_status(wb)
    if not wb:
        # No Thesis Run yet: surface the Screener handoff as pending intake rows
        # so the picks are immediately visible and Run Thesis is enabled.
        rows = _intake_rows(stores)
        return {"status": "idle", "rows": rows, "selection": [], "remaining": [],
                "selection_count": len(rows)}
    rows = wb.get("rows") or []
    if status != "completed":
        return {"status": status, "rows": rows, "selection": [], "remaining": [],
                "selection_count": wb.get("selection_count", 0),
                "run_id": wb.get("run_id"), "error": wb.get("error")}
    selection = stage.compute_selection(
        wb.get("rank_order") or [], wb.get("selection_state") or {},
        set(wb.get("eligible") or []),
    )
    _, remaining = stage.partition(wb.get("rank_order") or [], selection)
    return {
        "status": status, "rows": rows, "selection": selection, "remaining": remaining,
        "selection_count": wb.get("selection_count"), "run_id": wb.get("run_id"),
    }


def thesis_select(stores, ticker: str, action: str) -> dict:
    """Stage selection: promote appends + expands count (capped theses are
    promotable), dismiss reflows the default ranking. Failed tickers are never
    selectable."""
    wb = stores.runs.get_workbench(CAPABILITY)
    if not wb or wb.get("status") != "completed":
        raise ValueError("no completed thesis stage output to select against")
    rank_order = wb.get("rank_order") or []
    state, selection = stage.apply_action(
        stores, CAPABILITY, wb.get("run_id"),
        wb.get("selection_state") or stage.new_state(0),
        rank_order, ticker, action,
        eligible=set(wb.get("eligible") or []), promotable=set(rank_order),
    )
    wb["selection_state"] = state
    stores.runs.set_workbench(CAPABILITY, wb)
    rows = {r["ticker"]: r for r in wb.get("rows") or []}
    _refresh_ic_intake(stores, selection, rows, wb.get("run_id"))
    return thesis_current(stores)


def _refresh_ic_intake(stores, selection: list[str], rows: dict, run_id: str | None) -> None:
    """Handoff: IC intake = current thesis selection with artifact references.
    Refreshes intake only — IC never executes from here."""
    items = [
        {"ticker": t, "thesis_artifact_id": (rows.get(t) or {}).get("artifact_id"),
         "provenance": "thesis_selection"}
        for t in selection
    ]
    stores.runs.set_workbench(IC_INTAKE_KEY, {
        "source": "thesis", "source_run_id": run_id,
        "tickers": list(selection), "items": items,
    })
