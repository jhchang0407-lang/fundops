"""Investment Memo workflow (ADR-0013, ADR-0014, ADR-0036).

Fixed seven-section outline (domain.artifact_schemas.MEMO_OUTLINE), generated
in MEMO_GENERATION_ORDER (risks before valuation; synthesis sections last) —
ONE deep model call per section (7) plus one monitoring-plan call (8 total per
memo). Each section gets a section-scoped evidence package sliced from the
shared company evidence packet (workflows.evidence_packets): history + trends
+ peers for financial quality, sector peers + growth trends for industry,
price context + recent quarters + ownership for current setup, deterministic
anchors + scenario math for valuation, leverage + constitution misses for
risks. Completed Thesis and IC outputs are provenance only, never writer
inputs. Valuation carries deterministic anchors AND a deterministic
bear/base/bull scenario table computed before the model call; sections may
carry optional `tables` and `key_figures` (new optional fields — the
validate_memo contract on subsections is unchanged). The monitoring plan is a
separate structured output validated against the Supported Thesis Health
Field Catalog.
"""

from __future__ import annotations

import json
import logging

from backend.core import web_research
from backend.core.ai import PROMPT_VERSION, get_ai
from backend.core.workspace import now_iso
from backend.domain import artifact_schemas, metric_catalog
from backend.domain.artifact_schemas import (
    MEMO_DECISIONS, MEMO_GENERATION_ORDER, MEMO_OUTLINE,
)
from backend.domain.thesis_health import validate_plan
from backend.workflows import evidence_packets as ep
from backend.workflows import stage

log = logging.getLogger("fundops.workflows.memo")

CAPABILITY = "memo"
INTAKE_KEY = "memo_intake"

SECTION_TITLES = {sec_id: title for sec_id, title, _ in MEMO_OUTLINE}
SECTION_SUBS = {sec_id: subs for sec_id, _, subs in MEMO_OUTLINE}

SECTION_MAX_OUTPUT_TOKENS = 3500
SECTION_MIN_WORDS = 70  # prompt asks 120-280; below this triggers one repair pass

SYSTEM_WRITER = (
    "You are the FundOps investment memo writer producing institutional-depth "
    "research. Write analytical, evidence-first prose grounded ONLY in the section "
    "evidence package — cite the numbers you were given and never invent data. "
    "Each subsection is 120-280 words of markdown prose (paragraphs allowed) citing "
    "at least 2 specific figures; take a view in institutional memo voice — no "
    "hedging filler, no generic claims without numbers. The section_thesis is one "
    "sharp argument sentence."
)

SYSTEM_PLAN = (
    "You are the FundOps monitoring-plan designer. Convert the memo's assumptions, "
    "return drivers, risks, and kill criteria into trackable watch items. Quantitative "
    "items MUST use only metric/cadence/lookback combinations from the Supported Thesis "
    "Health Field Catalog provided; anything else must be qualitative. Each why_matters "
    "states the metric's role in the thesis and the consequence of a breach.\n\n"
    "CRITICAL — comparator direction: each quantitative item's comparator + threshold "
    "must express the HEALTHY/intact condition, i.e. the band the metric should STAY "
    "in while the thesis holds, NEVER the breach trigger. A breach is when the metric "
    "leaves that healthy band. Even when the title names the breach (kill criteria and "
    "risks usually do — 'revenue growth turns negative', 'leverage rises above 1.6x'), "
    "the comparator must still describe HEALTH:\n"
    "  - 'Revenue growth turns negative'  -> comparator '>=', threshold 0.0  "
    "(healthy while growth is non-negative; do NOT write '<' 0.0).\n"
    "  - 'Debt/equity rises above 1.6x'   -> comparator '<=', threshold 1.6  "
    "(healthy while leverage stays at/under the ceiling; do NOT write '>' 1.6).\n"
    "  - 'Gross margin holds above 40%'   -> comparator '>=', threshold 0.40."
)

PLAN_SHAPE = (
    '[{"item_type": "assumption|return_driver|risk|kill_criterion", "title": str, '
    '"tracking_mode": "quantitative|qualitative", "metric": str|null, '
    '"comparator": ">=|<=|>|<"|null  // expresses the HEALTHY band, never the breach, '
    '"threshold": number|null, '
    '"cadence": "quarterly|annual|ttm|slower", '
    '"lookback": "latest|yoy|ttm|annual|multi_period_avg", '
    '"confirmation_periods": int, "immediate_kill": bool, "why_matters": str}]'
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


async def run_memo(stores, ticker: str | None = None, trigger: str = "user",
                   provenance: str = "ic_selection") -> str:
    """Pinned contract entrypoint: write memos for the whole Memo intake, or a
    single ticker (directed research / portfolio coverage with provenance)."""
    rid = prepare_run(stores, trigger)
    await execute_run(stores, rid, ticker=ticker, provenance=provenance)
    return rid


async def execute_run(stores, run_id: str, ticker: str | None = None,
                      provenance: str = "ic_selection") -> None:
    try:
        await _execute(stores, run_id, ticker, provenance)
    except Exception as exc:  # noqa: BLE001
        stores.runs.finish_run(run_id, "failed", error=str(exc))
        wb = stores.runs.get_workbench(CAPABILITY) or {}
        if wb.get("run_id") == run_id:
            stores.runs.set_workbench(
                CAPABILITY, {**wb, "status": "failed", "error": str(exc)}
            )


async def _execute(stores, run_id: str, only_ticker: str | None, provenance: str) -> None:
    run = stores.runs.get_run(run_id) or {}
    cv_id = run.get("constitution_version_id")
    proj = stores.constitution.projection(CAPABILITY, cv_id) if cv_id else None
    emphasis = ((proj or {}).get("settings") or {}).get("strategy_emphasis") or ""

    intake = stores.runs.get_workbench(INTAKE_KEY) or {}
    items = intake.get("items") or [
        {"ticker": t, "provenance": "ic_selection"} for t in intake.get("tickers") or []
    ]
    if only_ticker:
        t = only_ticker.upper()
        match = next((i for i in items if str(i.get("ticker")).upper() == t), None)
        targets = [match or {"ticker": t, "provenance": provenance}]
    else:
        targets = items
    prior_rows = {
        r["ticker"]: r for r in (stores.runs.get_workbench(CAPABILITY) or {}).get("rows") or []
    }

    rows: dict[str, dict] = dict(prior_rows)
    order = [str(i["ticker"]).upper() for i in items]
    for item in targets:
        t = str(item["ticker"]).upper()
        if t not in order:
            order.append(t)
        rows.setdefault(t, {"ticker": t, "state": "pending"})

    def _push(status: str) -> None:
        # Snapshot live per-ticker progress to the workbench so the Memo page
        # (which polls memo/current) shows which ticker is writing and how many
        # are done, instead of a single generic 'Generating…' until the end
        # (ISSUE-010).
        stores.runs.set_workbench(CAPABILITY, {
            "run_id": run_id, "status": status,
            "rows": [rows[t] for t in order if t in rows],
        })

    _push("running")
    written = 0
    for item in targets:
        t = str(item["ticker"]).upper()
        prior = prior_rows.get(t)
        if prior and prior.get("state") == "completed" and prior.get("artifact_id"):
            rows[t] = prior  # re-run = resume; completed memos are never re-spent
            continue
        rows[t] = {"ticker": t, "state": "running"}
        _push("running")
        rows[t] = await _write_memo(
            stores, run_id, t, item.get("provenance") or provenance, cv_id, emphasis,
        )
        written += 1
        _push("running")

    completed = [t for t in rows if rows[t].get("state") == "completed"]
    failed_tickers = [t for t in rows if rows[t].get("state") == "failed"]
    # A run with operational failures is not a clean completion. Surface the
    # failed tickers in stats so the Runs list can flag it as partial (and name
    # them) without API spelunking (ISSUE-009). The whole-run status only flips
    # to failed when nothing was written — a mixed result stays a completion the
    # UI marks "partial", because the memos that did write are real artifacts.
    run_status = "failed" if (failed_tickers and not completed) else "completed"
    _push(run_status)
    stores.runs.finish_run(run_id, run_status, stats={
        "intake": len(targets), "written": written, "memos": len(completed),
        "failed": len(failed_tickers), "failed_tickers": failed_tickers,
    })


async def _write_memo(stores, run_id: str, ticker: str, provenance: str,
                      cv_id: str | None, emphasis: str) -> dict:
    step_id = stores.runs.add_step(run_id, CAPABILITY, ticker)
    try:
        ent = stores.identity.ensure_entity(ticker)
        packet = ep.build_company_packet(stores, ticker, ent["id"])
        metrics = packet["latest"]
        price = packet["price_context"].get("price")
        anchors = ep.deterministic_anchors(metrics, price)
        # Memo is the deep-research stage: SEC filings carry every figure, but
        # a 10-K is a yearly snapshot — augment with what happened SINCE.
        # Two bounded web passes (recent developments + competitive outlook),
        # deduped by URL; plus the retained recency layer below.
        name = packet["identity"]["name"]
        seen_urls: set[str] = set()
        web_results: list[dict] = []
        for q in (f"{name} {ticker} stock latest news developments earnings",
                  f"{name} {ticker} competitive outlook analysis"):
            out = await web_research.search(q, 4, ticker=ticker)
            for r in out["results"]:
                if r.get("url") and r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    web_results.append(r)
        web_block, web_sources = (web_research.context_block(web_results[:8])
                                  if web_results else ("", []))

        # Retained recency layer: filings since the last annual report (8-Ks,
        # 10-Qs), known events (earnings/dividends), and recent price action —
        # the "what changed lately" the annual statements can't show. The local
        # filings index only holds entries since bootstrap, so fall back to the
        # keyless EDGAR submissions list when it's empty for this company.
        recent_filings = [
            {"form": f.get("form"), "filed": str(f.get("filed_at") or "")[:10]}
            for f in stores.bulk.filings_for(ticker, limit=8)
        ]
        if not recent_filings:
            cik = ent.get("cik")
            if cik:
                try:
                    import asyncio as _asyncio

                    from backend.services.ingest import filing_text
                    rows = await _asyncio.to_thread(
                        filing_text.latest_filings_by_cik, cik,
                        ("8-K", "10-Q", "10-K"), 6)
                    recent_filings = [
                        {"form": r["form"], "filed": str(r.get("filed_at") or "")[:10]}
                        for r in rows
                    ]
                except Exception as exc:  # recency is best-effort, never fatal
                    log.debug("submissions recency fetch failed for %s: %s", ticker, exc)
        events = [
            {"kind": e.get("kind"), "label": e.get("label"), "date": e.get("event_date")}
            for e in stores.context.events_for(ticker, limit=6)
        ]
        market_recent = {
            k: metrics.get(k) for k in
            ("momentum_1m", "momentum_3m", "momentum_6m", "momentum_12m",
             "pct_below_52w_high", "volatility_90d", "avg_dollar_volume_3m")
            if metrics.get(k) is not None
        }
        recent_context = {
            **({"recent_filings": recent_filings} if recent_filings else {}),
            **({"known_events": events} if events else {}),
            **({"price_action": market_recent} if market_recent else {}),
        }

        ctx = {
            "ticker": ticker,
            "company_name": packet["identity"]["name"],
            "sector": packet["identity"].get("sector"),
            "price": price,
            "metrics": metrics,
            "packet": packet,
            "annual": {m: s["annual"] for m, s in packet["history"].items()
                       if s.get("annual")},
            "quarterly": {m: s["quarterly"] for m, s in packet["history"].items()
                          if s.get("quarterly")},
            "emphasis": emphasis,
            "anchors": anchors,
            "scenarios": ep.valuation_scenarios(anchors, metrics, price),
            "run_id": run_id,
            "web_context": web_block,
            "web_sources": web_sources,
            "recent_context": recent_context,
        }

        # Generation order: risks before valuation, synthesis sections last.
        sections: dict[str, dict] = {}
        for sec_id in MEMO_GENERATION_ORDER:
            sections[sec_id] = await _write_section(stores, sec_id, ctx, sections)
        _attach_deterministic_extras(sections, ctx)
        warnings = _apply_decision_default(sections)

        plan_items = await _monitoring_plan(stores, ticker, sections, ctx)
        warnings += [f"monitoring item {it['title']!r}: {note}"
                     for it in plan_items for note in it.get("normalizations") or []]

        bundle_id = stores.evidence.freeze_bundle({
            "kind": "investment_memo",
            "ticker": ticker,
            "constitution_version": cv_id,
            "provenance": provenance,
            "metrics_used": sorted(k for k, v in metrics.items() if v is not None),
            "observation_history": {"annual": sorted(ctx["annual"]),
                                    "quarterly": sorted(ctx["quarterly"])},
            "peers": [p["ticker"] for p in packet["peers"]],
            "prompt_version": PROMPT_VERSION,
        })
        kernel = artifact_schemas.make_kernel(
            "investment_memo", ticker, ent["id"], cv_id, bundle_id, now_iso(),
        )
        decision = sections["decision_summary"]["fields"]["decision"]
        payload = {**kernel, "body": {
            "sections": sections,
            "valuation": ctx["anchors"],
            "monitoring_plan_items": plan_items,
            "provenance": {"path": provenance},
            "decision": decision,
            **({"web_sources": ctx["web_sources"]} if ctx.get("web_sources") else {}),
            **({"recent_context": ctx["recent_context"]} if ctx.get("recent_context") else {}),
        }}
        vr = artifact_schemas.validate_memo(payload)
        if not vr.ok:
            # Retry only the failed sections once, with the errors in the prompt.
            for sec_id in _sections_with_errors(vr.errors):
                sections[sec_id] = await _write_section(
                    stores, sec_id, ctx, sections,
                    repair_errors=[e for e in vr.errors if f"{sec_id!r}" in e],
                )
            _attach_deterministic_extras(sections, ctx)
            warnings += _apply_decision_default(sections)
            payload["body"]["decision"] = sections["decision_summary"]["fields"]["decision"]
            vr = artifact_schemas.validate_memo(payload)
        payload["validation"] = {
            "ok": vr.ok, "errors": vr.errors, "warnings": vr.warnings + warnings,
        }
        if not vr.ok:
            stores.ops.record_provenance(
                step=CAPABILITY, kind="validation", run_id=run_id,
                validation=vr.to_dict(),
                rejected_output=json.dumps(payload["body"], default=str)[:4000],
            )
            stores.runs.finish_step(
                step_id, "failed", error="memo validation failed: " + "; ".join(vr.errors),
            )
            return {"ticker": ticker, "state": "failed",
                    "error": "validation failed"}

        rendered = _render_md(ctx, payload)
        aid = stores.artifacts.save_artifact(
            "investment_memo", payload, ticker=ticker, entity_id=ent["id"],
            run_id=run_id, rendered_md=rendered, evidence_bundle_id=bundle_id,
            constitution_version_id=cv_id,
        )
        _create_thesis_health_plan(stores, aid, ticker)
        stores.runs.finish_step(step_id, "completed", detail={
            "artifact_id": aid, "decision": decision,
            "monitoring_items": len(plan_items),
        })
        return {"ticker": ticker, "state": "completed", "artifact_id": aid,
                "decision": decision, "provenance": provenance}
    except Exception as exc:  # noqa: BLE001 — one memo failing never sinks the run
        stores.runs.finish_step(step_id, "failed", error=str(exc))
        return {"ticker": ticker, "state": "failed", "error": str(exc)}


def _create_thesis_health_plan(stores, memo_artifact_id: str, ticker: str) -> None:
    """Hand the saved memo to the thesis-health workflow (built in parallel;
    skip silently when the module is absent).

    A plan-creation failure, or a plan that can ground no watch item, is
    surfaced as a low-severity Dashboard attention item instead of leaving the
    Company Page silently 'Not Checked' — so the user can tell a missing thesis
    health is a real gap, not a working 'all clear' (the QA blind spot)."""
    try:
        from backend.workflows import thesis_health
    except ImportError:
        return
    try:
        plan_id = thesis_health.create_plan_for_memo(stores, memo_artifact_id)
    except Exception as exc:  # noqa: BLE001 — plan creation must not undo the memo
        log.warning("thesis-health plan creation failed for %s: %s", memo_artifact_id, exc)
        _flag_thesis_health_gap(
            stores, ticker, memo_artifact_id, "plan_failed",
            "thesis-health plan could not be generated",
            f"The memo saved, but building its monitoring plan failed ({exc}). Thesis "
            "health stays unavailable until the memo is regenerated.")
        return
    if plan_id and not thesis_health.plan_ready(stores, plan_id):
        _flag_thesis_health_gap(
            stores, ticker, memo_artifact_id, "plan_not_ready",
            "thesis-health baseline is missing data",
            "The monitoring plan was created but no watch item could be grounded in "
            "retained financials, so thesis health reads 'Not Checked'. It populates "
            "once the next filing or data refresh provides the history.")
    elif plan_id:
        stores.dashboard.resolve_source("thesis_health_gap", ticker.upper())


def _flag_thesis_health_gap(stores, ticker: str, memo_id: str, version: str,
                            title: str, body: str) -> None:
    try:
        stores.dashboard.upsert_item(
            "attention", "needs_attention", "thesis_health_gap", ticker.upper(), version,
            title=f"{ticker.upper()}: {title}", body=body, ticker=ticker, severity="low",
            evidence_refs=[{"kind": "memo", "id": memo_id}],
        )
    except Exception as exc:  # noqa: BLE001 — observability must never sink the memo
        log.warning("thesis-health gap flag failed for %s: %s", ticker, exc)


# --- section generation -----------------------------------------------------------------

async def _write_section(stores, sec_id: str, ctx: dict, done: dict,
                         repair_errors: list[str] | None = None) -> dict:
    subs = SECTION_SUBS[sec_id]
    shape = (
        '{"section_thesis": str, "subsections": {'
        + ", ".join(f'"{s}": "120-280 words markdown"' for s in subs) + "}"
        + (', "fields": {"decision": "attractive|watchlist|avoid|needs_more_evidence", '
           '"open_questions": [str], "evidence_gaps": [str]}'
           if sec_id == "decision_summary" else ', "fields": {}')
        + ', "tables": {"<table_name>": {"columns": [str], "rows": [[str|number]]}}, '
          '"key_figures": [{"label": str, "value": str}]}'
    )
    evidence = _section_evidence(sec_id, ctx, done)
    user = (
        f"Write the '{SECTION_TITLES[sec_id]}' section of the institutional "
        f"investment memo for {ctx['company_name']} ({ctx['ticker']}).\n"
        f"Required subsections: {list(subs)}\n\n"
        "Writing requirements:\n"
        "- Each subsection: 120-280 words of analytical markdown prose "
        "(paragraphs allowed).\n"
        "- Every subsection MUST cite at least 2 specific figures from the section "
        "evidence package; never invent data.\n"
        "- Take a view in institutional memo voice — no hedging filler, no generic "
        "claims without numbers.\n"
        "- section_thesis: ONE sharp argument sentence for the section.\n"
        "- Optionally return 'tables' and 'key_figures' built ONLY from package "
        "data (omit or leave empty otherwise).\n\n"
        f"Section evidence package:\n{json.dumps(evidence, default=str)}"
    )
    if sec_id == "decision_summary":
        user += ("\n\nAlso return fields.decision (attractive|watchlist|avoid|"
                 "needs_more_evidence) plus the top 3-5 open_questions and "
                 "evidence_gaps as lists.")
    if repair_errors:
        user += ("\n\nYour previous output failed validation; fix exactly these "
                 "errors:\n- " + "\n- ".join(repair_errors))
    result = await get_ai().complete_json(
        CAPABILITY, SYSTEM_WRITER, user, shape, tier="deep", run_id=ctx["run_id"],
        max_output_tokens=SECTION_MAX_OUTPUT_TOKENS, stub=_stub_section(sec_id, ctx),
    )
    result = result if isinstance(result, dict) else {}
    out = {
        "title": SECTION_TITLES[sec_id],
        "section_thesis": str(result.get("section_thesis") or "").strip(),
        "subsections": {s: str((result.get("subsections") or {}).get(s) or "").strip()
                        for s in subs},
        "fields": result.get("fields") if isinstance(result.get("fields"), dict) else {},
        "tables": _sanitize_tables(result.get("tables")),
        "key_figures": _sanitize_key_figures(result.get("key_figures")),
    }
    # Depth enforcement (model path only — the offline stub is a deliberate
    # placeholder): the prompt demands 120-280 words per subsection; a model
    # that returns thin prose gets exactly one targeted repair pass.
    if repair_errors is None and get_ai().provider != "stub":
        thin = [s for s, text in out["subsections"].items()
                if len(text.split()) < SECTION_MIN_WORDS]
        if thin:
            retry = await _write_section(
                stores, sec_id, ctx, done,
                repair_errors=[f"subsection '{s}' was only "
                               f"{len(out['subsections'][s].split())} words — expand to "
                               "120-280 words of figure-citing analysis" for s in thin])
            for s in thin:
                if len(retry["subsections"].get(s, "").split()) > len(out["subsections"][s].split()):
                    out["subsections"][s] = retry["subsections"][s]
    return out


def _sanitize_tables(raw) -> dict:
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for name, t in raw.items():
        if (isinstance(t, dict) and isinstance(t.get("columns"), list)
                and isinstance(t.get("rows"), list)):
            rows = [r for r in t["rows"] if isinstance(r, list)]
            if t["columns"] and rows:
                out[str(name)] = {"columns": [str(c) for c in t["columns"]],
                                  "rows": rows}
    return out


def _sanitize_key_figures(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    return [{"label": str(k["label"]), "value": str(k.get("value"))}
            for k in raw if isinstance(k, dict) and k.get("label") is not None]


def _section_evidence(sec_id: str, ctx: dict, done: dict) -> dict:
    """Bounded section-scoped evidence package sliced from the shared company
    packet. Thesis/IC artifacts are provenance only and never appear here.
    Every section carries the strategy emphasis + research-review criteria."""
    m = ctx["metrics"]
    packet = ctx["packet"]
    trends = packet["trends"]
    cc = packet["constitution_check"]

    def pick(*keys):
        return {k: m.get(k) for k in keys if m.get(k) is not None}

    def theses():
        return {s: (done.get(s) or {}).get("section_thesis") for s in done}

    evidence: dict = {
        "company": ctx["company_name"], "ticker": ctx["ticker"],
        "sector": ctx["sector"], "price": ctx["price"],
        "strategy": {
            "emphasis": ctx["emphasis"],
            "north_star": cc.get("north_star"),
            "research_review_criteria": cc.get("research_review") or [],
        },
        "data_quality_notes": packet["data_quality_notes"],
    }
    if ctx.get("web_context"):
        evidence["recent_web_context"] = (
            "SUPPLEMENTARY ONLY — never a source of figures; cite web-derived "
            "claims as [Wn]:\n" + ctx["web_context"])
    if ctx.get("recent_context"):
        # What happened since the last annual report: retained filings (8-K/10-Q),
        # known events, and recent price action — annual statements can't show it.
        evidence["since_last_annual_report"] = ctx["recent_context"]
    if sec_id == "business_quality":
        evidence["profitability"] = pick("gross_margin", "operating_margin", "net_margin",
                                         "fcf_margin", "roic", "roe", "roa")
        evidence["margin_trends"] = {k: v for k, v in trends.items()
                                     if k.endswith("_trajectory")}
        evidence["annual_history"] = {k: ctx["annual"][k]
                                      for k in ("gross_margin", "operating_margin",
                                                "roic", "eps")
                                      if k in ctx["annual"]}
        evidence["ownership"] = packet["ownership"]
    elif sec_id == "industry_growth":
        evidence["growth"] = pick("revenue", "revenue_growth", "revenue_growth_3y",
                                  "eps_growth", "fcf_growth")
        evidence["growth_trends"] = {k: trends[k]
                                     for k in ("revenue_cagr_pct", "revenue_cagr_years",
                                               "latest_quarter_revenue_yoy_pct")
                                     if k in trends}
        evidence["sector_peers"] = packet["peers"]
        evidence["annual_history"] = {k: ctx["annual"][k] for k in ("revenue", "eps")
                                      if k in ctx["annual"]}
    elif sec_id == "financial_quality":
        evidence["financials"] = pick("gross_margin", "operating_margin", "fcf_margin",
                                      "fcf_conversion", "debt_equity", "net_debt_ebitda",
                                      "interest_coverage", "current_ratio",
                                      "sbc_to_revenue", "capex_to_revenue", "roic")
        evidence["annual_history"] = ctx["annual"]
        evidence["trends"] = trends
        evidence["peer_comparison"] = packet["peers"]
    elif sec_id == "risks":
        evidence["leverage"] = pick("debt_equity", "net_debt_ebitda", "interest_coverage")
        evidence["margin_trends"] = {k: v for k, v in trends.items()
                                     if k.endswith("_trajectory")}
        evidence["trend_history"] = {k: ctx["annual"][k]
                                     for k in ("revenue", "gross_margin", "fcf_margin")
                                     if k in ctx["annual"]}
        evidence["growth"] = pick("revenue_growth")
        evidence["constitution_misses"] = [r for r in cc["rows"]
                                           if r["satisfied"] is False]
        evidence["downside_anchor"] = {"downside_pct": ctx["anchors"].get("downside_pct")}
    elif sec_id == "valuation":
        evidence["market"] = pick("pe", "pb", "ps", "ev_ebitda", "fcf_yield",
                                  "earnings_yield", "eps", "market_cap")
        evidence["deterministic_anchors"] = ctx["anchors"]
        evidence["scenarios"] = ctx["scenarios"]
        evidence["peer_multiples"] = [{"ticker": p["ticker"], "pe": p.get("pe")}
                                      for p in packet["peers"]]
        evidence["price_context"] = packet["price_context"]
        evidence["instruction"] = ("Reference the deterministic anchors and the "
                                   "scenario table explicitly; they are the "
                                   "base/bear/bull math.")
    elif sec_id == "current_setup":
        evidence["price_context"] = packet["price_context"]
        evidence["recent_quarters"] = ctx["quarterly"]
        evidence["ownership"] = packet["ownership"]
        evidence["completed_section_theses"] = theses()
    elif sec_id == "decision_summary":
        evidence["completed_section_theses"] = theses()
        evidence["deterministic_anchors"] = ctx["anchors"]
        evidence["scenarios"] = ctx["scenarios"]
        evidence["constitution_check"] = cc["rows"]
    return evidence


def _apply_decision_default(sections: dict) -> list[str]:
    """Memo Decision must be one of the fixed values; invalid decisions default
    to needs_more_evidence with a recorded warning."""
    ds = sections.setdefault("decision_summary", {})
    fields = ds.setdefault("fields", {})
    if fields.get("decision") not in MEMO_DECISIONS:
        bad = fields.get("decision")
        fields["decision"] = "needs_more_evidence"
        return [f"invalid memo decision {bad!r}; defaulted to needs_more_evidence"]
    return []


def _sections_with_errors(errors: list[str]) -> list[str]:
    found = []
    for sec_id in SECTION_SUBS:
        if any(f"{sec_id!r}" in e for e in errors) and sec_id not in found:
            found.append(sec_id)
    return found


# --- deterministic tables + key figures ----------------------------------------------------

_DEFAULT_KEY_FIGURES = {
    "business_quality": ("gross_margin", "operating_margin", "roic", "roe"),
    "industry_growth": ("revenue", "revenue_growth"),
    "financial_quality": ("fcf_margin", "debt_equity", "interest_coverage", "roic"),
    "risks": ("debt_equity", "net_debt_ebitda", "interest_coverage"),
    "current_setup": ("pe", "fcf_yield", "market_cap"),
}


def _attach_deterministic_extras(sections: dict, ctx: dict) -> None:
    """Deterministic tables/key_figures attached to sections regardless of
    provider: the scenario table, the financial-history table, and per-section
    key-figure defaults when the writer returned none. Stored under the NEW
    optional section fields — validate_memo's subsection contract is untouched."""
    m = ctx["metrics"]
    for sec_id, sec in sections.items():
        sec.setdefault("tables", {})
        sec.setdefault("key_figures", [])
        if not sec["key_figures"]:
            sec["key_figures"] = [
                {"label": ep.display_name(k), "value": ep.fmt_value(k, m[k])}
                for k in _DEFAULT_KEY_FIGURES.get(sec_id, ()) if m.get(k) is not None
            ]
    if ctx["scenarios"] and "valuation" in sections:
        sections["valuation"]["tables"]["scenarios"] = ctx["scenarios"]
        if not sections["valuation"]["key_figures"]:
            a = ctx["anchors"]
            sections["valuation"]["key_figures"] = [
                {"label": "Base fair value", "value": f"{a['fair_value_base']:,.2f}"},
                {"label": "Upside vs price", "value": f"{a['upside_pct']:+.1f}%"},
            ]
    history_table = _financial_history_table(ctx)
    if history_table and "financial_quality" in sections:
        sections["financial_quality"]["tables"]["financial_history"] = history_table
    if "decision_summary" in sections and not sections["decision_summary"]["key_figures"]:
        figures = [{"label": "Decision",
                    "value": str(sections["decision_summary"]["fields"].get("decision"))}]
        if ctx["anchors"].get("upside_pct") is not None:
            figures.append({"label": "Base-case upside",
                            "value": f"{ctx['anchors']['upside_pct']:+.1f}%"})
        sections["decision_summary"]["key_figures"] = figures


def _financial_history_table(ctx: dict) -> dict | None:
    """Markdown-ready annual history table (metric rows × period columns)."""
    annual = ctx["annual"]
    if not annual:
        return None
    periods: list[str] = []
    for series in annual.values():
        for p in series:
            if p["period_end"] not in periods:
                periods.append(p["period_end"])
    periods = sorted(periods, reverse=True)[:ep.ANNUAL_PERIODS]
    if not periods:
        return None
    rows = []
    for metric, series in annual.items():
        by_period = {p["period_end"]: p["value"] for p in series}
        rows.append([ep.display_name(metric)]
                    + [ep.fmt_value(metric, by_period.get(p)) for p in periods])
    return {"columns": ["Metric"] + [p[:7] for p in periods], "rows": rows}


# --- monitoring plan ---------------------------------------------------------------------

async def _monitoring_plan(stores, ticker: str, sections: dict, ctx: dict) -> list[dict]:
    """Separate structured monitoring-plan output: one deep call, validated
    against the Supported Thesis Health Field Catalog; one bounded repair
    attempt covers invalid quantitative items only."""
    catalog = metric_catalog.thesis_health_catalog()
    theses = {s: (sections.get(s) or {}).get("section_thesis") for s in sections}
    kill = (sections.get("risks") or {}).get("subsections", {}).get("kill_criteria", "")
    user = (
        f"Design the monitoring plan for the {ticker} memo.\n\n"
        f"Section theses:\n{json.dumps(theses, default=str)}\n\n"
        f"Kill criteria prose:\n{kill}\n\n"
        f"Supported Thesis Health Field Catalog (the ONLY valid quantitative "
        f"combinations):\n{json.dumps(catalog)}\n\n"
        "Return 4-8 watch items covering assumptions, return drivers, risks and at "
        "least one kill criterion. Each why_matters must explain the metric's role "
        "in this memo's thesis (cite the baseline figure) and what a breach implies.\n\n"
        "Each quantitative comparator + threshold MUST describe the HEALTHY band the "
        "metric should STAY in, not the breach. Worked examples: 'Revenue growth turns "
        "negative' -> metric revenue_growth, comparator '>=', threshold 0.0. "
        "'Debt/equity rises above 1.6x' -> metric debt_equity, comparator '<=', "
        "threshold 1.6. 'Gross margin holds above 40%' -> comparator '>=', "
        "threshold 0.40."
    )
    raw = await get_ai().complete_json(
        "memo_monitoring", SYSTEM_PLAN, user, PLAN_SHAPE, tier="deep",
        run_id=ctx["run_id"], stub=_stub_plan(ctx["metrics"]),
    )
    if isinstance(raw, dict):
        raw = raw.get("items") or []
    raw = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
    specs = validate_plan(raw)
    invalid_idx = [
        i for i, s in enumerate(specs)
        if s.validation_errors and raw[i].get("tracking_mode") == "quantitative"
    ]
    if invalid_idx:
        repair_user = (
            "Repair ONLY these invalid monitoring-plan items (return the corrected "
            "items as a JSON array, same order):\n"
            + json.dumps([{
                "item": raw[i],
                "errors": specs[i].validation_errors,
            } for i in invalid_idx], default=str)
            + f"\n\nSupported catalog:\n{json.dumps(catalog)}"
        )
        repaired = await get_ai().complete_json(
            "memo_monitoring", SYSTEM_PLAN, repair_user, PLAN_SHAPE, tier="deep",
            run_id=ctx["run_id"], stub=[],
        )
        if isinstance(repaired, list):
            for i, item in zip(invalid_idx, repaired):
                if isinstance(item, dict):
                    raw[i] = item
            specs = validate_plan(raw)
    return [{
        "item_type": s.item_type, "title": s.title, "tracking_mode": s.tracking_mode,
        "metric": s.metric, "comparator": s.comparator, "threshold": s.threshold,
        "cadence": s.cadence, "lookback": s.lookback,
        "confirmation_periods": s.confirmation_periods,
        "immediate_kill": s.immediate_kill, "why_matters": s.why_matters,
        "validation_errors": s.validation_errors,
        "normalizations": s.normalizations,
    } for s in specs]


# --- deterministic stubs ------------------------------------------------------------------

def _stub_section(sec_id: str, ctx: dict) -> dict:
    """Deterministic offline section: every subsection gets DIFFERENT prose
    derived from the relevant slice of the shared evidence packet, citing
    actual levels/trends/peer rows/constitution outcomes — the same grounding
    a real model receives. The offline-mode note appears in the Evidence
    Quality subsection only."""
    f = _stub_facts(ctx)
    builders = {
        "current_setup": _stub_current_setup,
        "business_quality": _stub_business_quality,
        "industry_growth": _stub_industry_growth,
        "financial_quality": _stub_financial_quality,
        "valuation": _stub_valuation,
        "risks": _stub_risks,
        "decision_summary": _stub_decision_summary,
    }
    section_thesis, subs = builders[sec_id](ctx, f)
    out = {"section_thesis": section_thesis,
           "subsections": {s: subs[s] for s in SECTION_SUBS[sec_id]},
           "fields": {}}
    if sec_id == "decision_summary":
        notes = ctx["packet"]["data_quality_notes"]
        out["fields"] = {
            "decision": _stub_decision(ctx["anchors"], ctx["packet"]),
            "open_questions": [
                f"How durable is the {f['gm']} gross margin under competitive pressure?",
                f"Is the {f['growth']} reported growth organic or acquisition-driven?",
                "What does management guide for the next fiscal year?",
            ],
            "evidence_gaps": (list(notes) if notes
                              else ["No filing-level citations attached",
                                    "No recent market/news context retained"]),
        }
    return out


def _stub_facts(ctx: dict) -> dict:
    """Preformatted packet facts shared by the section stubs."""
    packet = ctx["packet"]
    m = ctx["metrics"]
    trends = packet["trends"]
    cc = packet["constitution_check"]
    measured = [r for r in cc["rows"] if r["satisfied"] is not None]
    price = ctx["price"]

    def v(metric):
        return ep.fmt_value(metric, m.get(metric))

    return {
        "name": ctx["company_name"],
        "sector": packet["identity"].get("sector") or "the retained universe",
        "price_s": f"{price:,.2f}" if isinstance(price, (int, float)) else "n/a",
        "rev": v("revenue"), "growth": v("revenue_growth"), "gm": v("gross_margin"),
        "om": v("operating_margin"), "nm": v("net_margin"), "fcfm": v("fcf_margin"),
        "fy": v("fcf_yield"), "roic": v("roic"), "roe": v("roe"), "de": v("debt_equity"),
        "pe": v("pe"), "eps": v("eps"), "mcap": v("market_cap"),
        "gm_trend": ep.trend_phrase(packet, "gross_margin"),
        "om_trend": ep.trend_phrase(packet, "operating_margin"),
        "cagr": trends.get("revenue_cagr_pct"),
        "cagr_years": trends.get("revenue_cagr_years"),
        "qtr_yoy": trends.get("latest_quarter_revenue_yoy_pct"),
        "roic_rank": ep.peer_rank(packet, "roic"),
        "gm_rank": ep.peer_rank(packet, "gross_margin"),
        "growth_rank": ep.peer_rank(packet, "revenue_growth"),
        "peers": packet["peers"],
        "n_peers": len(packet["peers"]),
        "measured": measured,
        "passes": [r for r in measured if r["satisfied"]],
        "misses": [r for r in measured if not r["satisfied"]],
        "holders": packet["ownership"]["largest_holders"],
        "insiders": packet["ownership"]["insider_transactions_recent"],
        "n_annual": max((len(s.get("annual") or [])
                         for s in packet["history"].values()), default=0),
        "n_quarterly": max((len(s.get("quarterly") or [])
                            for s in packet["history"].values()), default=0),
        "n_metrics": sum(1 for x in m.values() if x is not None),
        "latest_period": next((s["annual"][0]["period_end"]
                               for s in packet["history"].values()
                               if s.get("annual")), "n/a"),
    }


def _rule_facts(rows: list[dict], n: int = 2) -> str:
    return ("; ".join(f"{r['rule']} (observed {r['observed_display']})"
                      for r in rows[:n]) or "none")


def _stub_current_setup(ctx: dict, f: dict) -> tuple[str, dict]:
    a = ctx["anchors"]
    pc = ctx["packet"]["price_context"]
    gap = (f"{a['upside_pct']:+.1f}% from the deterministic fair-value anchor of "
           f"{a['fair_value_base']:,.2f}" if a.get("upside_pct") is not None
           else "an unquantified distance from fair value (no anchor computable)")
    range_s = (f"The shares sit {pc['pct_off_52w_high']:+.1f}% versus the 52-week high "
               f"of {pc['high_52w']:,.2f}."
               if pc.get("pct_off_52w_high") is not None
               else "No 52-week price range is retained to frame the entry point.")
    quarters = ctx["quarterly"].get("revenue") or []
    recent = (f"The most recent retained quarter ({quarters[0]['period_end']}) shows "
              f"revenue of {ep.fmt_value('revenue', quarters[0]['value'])}, one of "
              f"{len(quarters)} quarterly periods on record"
              + (f"; latest-quarter revenue is {f['qtr_yoy']:+.1f}% year over year."
                 if f["qtr_yoy"] is not None else ".")
              if quarters else
              f"No quarterly observations are retained; the latest annual period is "
              f"{f['latest_period']}, which sets the confirmation cadence.")
    holders_s = (f"The largest retained holders are "
                 + ", ".join(h["owner_name"] for h in f["holders"][:3])
                 + f", with {f['insiders']} recent insider transactions on file."
                 if f["holders"] else
                 f"No beneficial-ownership records are retained; {f['insiders']} "
                 "recent insider transactions are on file.")
    subs = {
        "why_now": (
            f"At {f['price_s']}, {f['name']} trades {gap}. The setup rests on the "
            f"{f['growth']} revenue growth and {f['gm']} gross margin in the latest "
            f"retained period persisting rather than improving. {range_s}"),
        "recent_events": (
            f"{recent} Reported fundamentals, not news flow, are the retained "
            f"record: {f['n_metrics']} current metrics across {f['n_annual']} annual "
            "period(s)."),
        "market_view": (
            f"The market values {f['name']} at {f['pe']} earnings with a {f['fy']} "
            f"free-cash-flow yield, implying limited credit for the {f['growth']} "
            f"growth baseline. That pricing treats the {f['gm']} gross margin "
            "structure as at risk rather than durable."),
        "variant_view": (
            f"The variant view is that the retained record — {f['gm_trend']}, ROIC of "
            f"{f['roic']} — supports durability the multiple does not pay for. "
            f"Constitution evidence backs this: strongest rows are "
            f"{_rule_facts(f['passes'])}."),
        "evidence_quality": (
            f"Evidence base: {f['n_metrics']} retained metrics, {f['n_annual']} annual "
            f"and {f['n_quarterly']} quarterly period(s), {f['n_peers']} same-sector "
            f"peer row(s); latest observations dated {f['latest_period']}. "
            f"{holders_s} Generated in deterministic offline mode (no model provider "
            "configured), so figures come exclusively from retained observations."),
    }
    thesis = (f"{f['name']} at {f['price_s']} offers {gap} while the market "
              f"under-credits a {f['gm']}-gross-margin, {f['growth']}-growth franchise.")
    return thesis, subs


def _stub_business_quality(ctx: dict, f: dict) -> tuple[str, dict]:
    rank_s = (f"ROIC of {f['roic']} ranks above {f['roic_rank'][0]} of "
              f"{f['roic_rank'][1]} retained {f['sector']} peers"
              if f["roic_rank"] else
              f"ROIC stands at {f['roic']} with no retained peer rows to rank against")
    subs = {
        "business_model": (
            f"{f['name']} converts {f['rev']} of revenue into a {f['gm']} gross margin "
            f"and a {f['om']} operating margin, with {f['fcfm']} of revenue reaching "
            f"free cash flow. That spread between gross and operating margin defines "
            "the cost structure the thesis depends on."),
        "products_and_value_chain": (
            f"A {f['gm']} gross margin is the cleanest retained proxy for value "
            f"capture in {f['sector']}: it prices the product above its direct "
            f"cost stack. {f['gm_trend'].capitalize()}, which indicates the value "
            "proposition is holding rather than being competed away."),
        "moat_and_defensibility": (
            f"{rank_s}. Returns above the cost of capital sustained at {f['roic']} "
            f"alongside a {f['gm']} gross margin are the structural signature of a "
            "defensible position; the retained record contains no margin break that "
            "would contradict it."),
        "management_and_capital_allocation": (
            f"Capital discipline reads through the numbers: ROIC of {f['roic']} versus "
            f"ROE of {f['roe']} on debt/equity of {f['de']} shows how much of the "
            f"equity return is operational rather than leverage. {f['insiders']} "
            "recent insider transactions are retained as the governance signal."),
        "quality_watch_items": (
            f"Watch the two quality anchors: gross margin (now {f['gm']}) and ROIC "
            f"(now {f['roic']}). A sustained slide in either — particularly gross "
            f"margin below roughly 80% of the current level — would say the moat is "
            "narrowing before the income statement headline shows it."),
    }
    thesis = (f"{f['name']}'s {f['gm']} gross margin and {f['roic']} ROIC mark a "
              f"business earning well above its cost of capital — {rank_s}.")
    return thesis, subs


def _stub_industry_growth(ctx: dict, f: dict) -> tuple[str, dict]:
    peers = f["peers"]
    peer_table_s = (
        "; ".join(
            f"{p['ticker']} (ROIC {ep.fmt_value('roic', p.get('roic'))}, growth "
            f"{ep.fmt_value('revenue_growth', p.get('revenue_growth'))})"
            for p in peers[:3])
        if peers else "no same-sector peers with retained financials")
    cagr_s = (f"a {f['cagr']}% revenue CAGR over {f['cagr_years']} retained year(s)"
              if f["cagr"] is not None
              else f"reported revenue growth of {f['growth']} in the latest period")
    growth_rank_s = (
        f"Revenue growth of {f['growth']} beats {f['growth_rank'][0]} of "
        f"{f['growth_rank'][1]} retained peers."
        if f["growth_rank"] else
        f"Revenue growth stands at {f['growth']} with no peer growth rows retained.")
    subs = {
        "industry_structure": (
            f"The retained {f['sector']} comparison set holds {f['n_peers']} peer(s): "
            f"{peer_table_s}. {f['name']}'s {f['gm']} gross margin against that set "
            "indicates where it sits in the industry's profit pool."),
        "customer_and_demand_dynamics": (
            f"Demand evidence is {cagr_s}"
            + (f", with the latest quarter at {f['qtr_yoy']:+.1f}% year over year"
               if f["qtr_yoy"] is not None else "")
            + f". Sustained growth at a {f['gm']} gross margin implies demand that "
              "does not require price concessions to clear."),
        "growth_drivers": (
            f"The quantifiable growth driver in the retained record is {cagr_s}, "
            f"compounding on a {f['rev']} revenue base. With {f['om']} operating "
            "margins, incremental revenue should carry meaningful operating leverage "
            "if the cost structure holds."),
        "competitive_position": (
            f"{growth_rank_s} Combined with ROIC of {f['roic']}"
            + (f" (above {f['roic_rank'][0]} of {f['roic_rank'][1]} peers)"
               if f["roic_rank"] else "")
            + ", the company is taking profitable share rather than buying growth."),
        "growth_watch_items": (
            f"Watch revenue growth against the {f['growth']} baseline and the peer "
            f"set's trajectory. Deceleration below that baseline for two consecutive "
            f"periods — or peer growth converging on {f['name']}'s — would undercut "
            "the growth leg of the return decomposition."),
    }
    thesis = (f"{f['name']} pairs {cagr_s} with profitability ahead of its retained "
              f"{f['sector']} peer set.")
    return thesis, subs


def _stub_financial_quality(ctx: dict, f: dict) -> tuple[str, dict]:
    annual = ctx["annual"]
    rev_series = annual.get("revenue") or []
    history_s = (
        f"Across {len(rev_series)} retained annual periods, revenue moved from "
        f"{ep.fmt_value('revenue', rev_series[-1]['value'])} to "
        f"{ep.fmt_value('revenue', rev_series[0]['value'])}"
        + (f" (a {f['cagr']}% CAGR)" if f["cagr"] is not None else "")
        if len(rev_series) >= 2 else
        f"Only the latest annual period is retained (revenue {f['rev']}), so quality "
        "is judged on levels rather than trajectory")
    peer_s = (f"Against {f['n_peers']} retained peer(s), gross margin of {f['gm']} "
              f"beats {f['gm_rank'][0]} of {f['gm_rank'][1]} and ROIC of {f['roic']} "
              f"beats {f['roic_rank'][0]} of {f['roic_rank'][1]}."
              if f["gm_rank"] and f["roic_rank"] else
              "No retained peer rows are available for benchmarking, so the absolute "
              f"levels — {f['gm']} gross margin, {f['roic']} ROIC — carry the "
              "comparison.")
    subs = {
        "revenue_and_margin_quality": (
            f"{history_s}. {f['gm_trend'].capitalize()} and "
            f"{f['om_trend']} — margin quality is read from those trajectories, not "
            "a single print."),
        "cash_flow_and_balance_sheet": (
            f"Free cash flow runs at {f['fcfm']} of revenue with a {f['fy']} yield on "
            f"the market value, against debt/equity of {f['de']}. Cash conversion at "
            "that level funds the growth baseline internally without stressing the "
            "balance sheet."),
        "returns_on_capital": (
            f"ROIC of {f['roic']} and ROE of {f['roe']} both clear a 10% "
            f"cost-of-capital reference, and the gap between them on {f['de']} "
            "debt/equity shows the return is earned operationally rather than "
            "financially engineered."),
        "peer_benchmarking": (
            f"{peer_s} The financial-history table below carries the full retained "
            "record."),
        "financial_watch_items": (
            f"Track three lines: gross margin against the {f['gm']} baseline, FCF "
            f"margin against {f['fcfm']}, and debt/equity against {f['de']}. Two "
            "consecutive deteriorating periods in any of them reopens the quality "
            "question this section answers."),
    }
    thesis = (f"{f['name']}'s financial record — {f['gm']} gross margin, {f['fcfm']} "
              f"FCF margin, {f['roic']} ROIC — is institutional-quality on the "
              "retained evidence.")
    return thesis, subs


def _stub_valuation(ctx: dict, f: dict) -> tuple[str, dict]:
    a = ctx["anchors"]
    sc = ctx["scenarios"]
    if a.get("fair_value_base") is not None:
        base_s = (f"The deterministic base case puts fair value at "
                  f"{a['fair_value_base']:,.2f} via {a['method']}, "
                  f"{a['upside_pct']:+.1f}% versus the current price of "
                  f"{f['price_s']}.")
    else:
        base_s = ("No deterministic fair value is computable: the retained record "
                  "lacks positive EPS and a usable FCF yield, leaving 0 valuation "
                  "anchors.")
    if sc:
        rows = {r[0]: r for r in sc["rows"]}
        cases_s = (f"The scenario math spans {rows['bear'][2]:,.2f} in the bear case "
                   f"({rows['bear'][3]:+.1f}% vs price) to {rows['bull'][2]:,.2f} in "
                   f"the bull case ({rows['bull'][3]:+.1f}%), with the base case at "
                   f"{rows['base'][2]:,.2f} ({rows['base'][3]:+.1f}%).")
        skew_s = (f"Payoff skew is {rows['bull'][3] + rows['bear'][3]:+.1f} points "
                  "(bull plus bear), which frames the risk/reward.")
    else:
        cases_s = ("No scenario table is computable without a base fair value and a "
                   "current price; 0 of 3 cases are quantified.")
        skew_s = "Risk/reward cannot be framed numerically on the retained data."
    subs = {
        "valuation_method": (
            f"The anchor method is {a.get('method') or 'unavailable on retained data'}"
            f" — chosen because it prices the retained earnings power (EPS {f['eps']})"
            f" against the {f['growth']} growth baseline deterministically, with no "
            "model judgment in the arithmetic."),
        "base_case": (
            f"{base_s} The market currently pays {f['pe']} for those earnings with a "
            f"{f['fy']} free-cash-flow yield."),
        "upside_and_downside_cases": (
            f"{cases_s} {skew_s}"),
        "memo_return_drivers": (
            f"The return decomposes into the {f['fy']} cash-flow yield, the "
            f"{f['growth']} growth baseline, and any closing of the gap to the "
            f"anchor fair value"
            + (f" ({a['upside_pct']:+.1f}%)" if a.get("upside_pct") is not None
               else "")
            + ". No re-rating beyond the scenario bands is assumed."),
        "key_assumptions": (
            f"Three assumptions carry the math: gross margin holds near {f['gm']}, "
            f"revenue growth holds near {f['growth']}, and the justified multiple "
            f"stays within the scenario band around the current {f['pe']}. Each is "
            "trackable against retained observations."),
    }
    thesis = (f"Deterministic valuation puts {f['name']} at "
              + (f"{a['fair_value_base']:,.2f} base fair value "
                 f"({a['upside_pct']:+.1f}% vs price)"
                 if a.get("fair_value_base") is not None and a.get("upside_pct") is not None
                 else "an uncomputable fair value on retained data")
              + ", with the bear/base/bull band quantified below.")
    return thesis, subs


def _stub_risks(ctx: dict, f: dict) -> tuple[str, dict]:
    a = ctx["anchors"]
    sc = ctx["scenarios"]
    bear = next((r for r in (sc or {}).get("rows", []) if r[0] == "bear"), None)
    miss_s = (f"The active constitution flags {len(f['misses'])} measured miss(es): "
              f"{_rule_facts(f['misses'])}."
              if f["misses"] else
              f"All {len(f['measured'])} measured constitution criteria are currently "
              "satisfied, so the named risks are forward-looking rather than present "
              "breaches.")
    leverage_s = (f"debt/equity of {f['de']}" if f["de"] != "n/a"
                  else "unmeasured leverage (a risk in itself)")
    subs = {
        "key_risks": (
            f"The thesis concentrates risk in two lines: the {f['gm']} gross margin "
            f"and the {f['growth']} growth baseline — both feed the return math "
            f"directly. Balance-sheet risk sits at {leverage_s}. {miss_s}"),
        "bear_case": (
            f"The quantified bear case marks fair value at "
            + (f"{bear[2]:,.2f} ({bear[3]:+.1f}% vs the current price), assuming "
               f"{bear[1]}." if bear else
               "n/a — no deterministic anchor exists to discount, which itself "
               "widens the downside band.")
            + " The bear case is margin-led: compression does double damage through "
              "earnings and the multiple."),
        "sensitivity_factors": (
            f"Sensitivity is highest to gross margin (every 100bps off the {f['gm']} "
            f"baseline flows straight through the {f['om']} operating margin) and to "
            f"growth (each point below {f['growth']} removes a point from the return "
            "decomposition). Multiple compression compounds either."),
        "kill_criteria": (
            f"Kill criteria are numeric: gross margin sustained below ~60% of the "
            f"{f['gm']} baseline, revenue growth turning negative against the "
            f"{f['growth']} baseline, or leverage materially above the current "
            f"{f['de']}. Any of these invalidates the quality-compounding premise "
            "rather than merely delaying it."),
        "risk_watch_items": (
            f"The monitoring plan tracks the same lines quarterly: gross margin vs "
            f"{f['gm']}, growth vs {f['growth']}, leverage vs {f['de']}"
            + (f", plus the downside anchor at {a['downside_pct']:+.1f}%"
               if a.get("downside_pct") is not None else "")
            + ". Confirmation across two periods separates noise from break."),
    }
    thesis = (f"Risk is concentrated in margin durability ({f['gm']}) and growth "
              f"persistence ({f['growth']}); the quantified bear case is "
              + (f"{bear[3]:+.1f}% vs price" if bear else "not computable") + ".")
    return thesis, subs


def _stub_decision_summary(ctx: dict, f: dict) -> tuple[str, dict]:
    a = ctx["anchors"]
    decision = _stub_decision(a, ctx["packet"])
    upside_s = (f"{a['upside_pct']:+.1f}% base-case upside"
                if a.get("upside_pct") is not None
                else "no computable base-case upside")
    cc_s = (f"{len(f['passes'])} of {len(f['measured'])} measured constitution "
            "criteria satisfied")
    subs = {
        "investment_case_summary": (
            f"{f['name']} at {f['price_s']} presents {upside_s} against a "
            f"deterministic anchor"
            + (f" of {a['fair_value_base']:,.2f}"
               if a.get("fair_value_base") is not None else "")
            + f", built on a {f['gm']} gross margin, {f['roic']} ROIC, and "
              f"{f['growth']} revenue growth. {cc_s.capitalize()}, and the financial "
              "record contains no current breach of the quality premise."),
        "decision": (
            f"The decision is {decision.replace('_', ' ')}: {upside_s} with {cc_s} "
            f"and {f['n_annual']} annual period(s) of supporting record. The decision "
            "rule weighs quantified upside against constitution fit, so it moves "
            "with the evidence rather than sentiment."),
        "open_questions": (
            f"Three questions remain open: whether the {f['gm']} gross margin "
            f"survives competitive pressure, whether {f['growth']} growth is organic, "
            "and what management guides next — none answerable from the retained "
            "record alone."),
        "evidence_gaps": (
            (f"Known gaps in the evidence base ({len(f['measured'])} criteria "
             "measured): " + "; ".join(ctx["packet"]["data_quality_notes"]) + ".")
            if ctx["packet"]["data_quality_notes"] else
            f"No structural gaps flagged: {f['n_metrics']} metrics, {f['n_annual']} "
            f"annual and {f['n_quarterly']} quarterly period(s), and "
            f"{f['n_peers']} peer row(s) are retained."),
    }
    thesis = (f"On {upside_s} and {cc_s}, {f['name']} resolves to "
              f"{decision.replace('_', ' ')}.")
    return thesis, subs


def _stub_decision(anchors: dict, packet: dict) -> str:
    """Offline decision rule: quantified upside gated by the active
    constitution — upside >15% with every measured criterion passing is
    attractive; positive upside is watchlist; negative is avoid; no anchor is
    needs_more_evidence."""
    upside = anchors.get("upside_pct")
    if upside is None:
        return "needs_more_evidence"
    if upside > 15 and packet["constitution_check"].get("measured_all_pass", True):
        return "attractive"
    if upside > 0:
        return "watchlist"
    return "avoid"


def _stub_plan(metrics: dict) -> list[dict]:
    items: list[dict] = []
    gm = metrics.get("gross_margin")
    if isinstance(gm, (int, float)):
        items.append({
            "item_type": "assumption", "title": "Gross margin holds near current level",
            "tracking_mode": "quantitative", "metric": "gross_margin",
            "comparator": ">=", "threshold": round(gm * 0.8, 4),
            "cadence": "quarterly", "lookback": "latest", "confirmation_periods": 2,
            "immediate_kill": False,
            "why_matters": (
                f"The {gm * 100:.1f}% gross margin is the quality anchor of the "
                f"thesis — it carries both the margin-durability assumption and the "
                f"valuation multiple. Erosion below {gm * 0.8 * 100:.1f}% (80% of "
                "baseline) undermines the economics the fair value rests on."),
        })
        items.append({
            "item_type": "kill_criterion", "title": "Gross margin collapse",
            "tracking_mode": "quantitative", "metric": "gross_margin",
            "comparator": ">=", "threshold": round(gm * 0.6, 4),
            "cadence": "quarterly", "lookback": "latest", "confirmation_periods": 1,
            "immediate_kill": True,
            "why_matters": (
                f"A collapse below {gm * 0.6 * 100:.1f}% (60% of the "
                f"{gm * 100:.1f}% baseline) breaks the unit economics outright — the "
                "thesis has no version that survives it, so it triggers immediate "
                "exit review."),
        })
    growth = metrics.get("revenue_growth")
    if isinstance(growth, (int, float)):
        items.append({
            "item_type": "return_driver", "title": "Revenue growth stays on thesis path",
            "tracking_mode": "quantitative", "metric": "revenue_growth",
            "comparator": ">=", "threshold": round(max(growth - 0.05, 0.0), 4),
            "cadence": "annual", "lookback": "yoy", "confirmation_periods": 2,
            "immediate_kill": False,
            "why_matters": (
                f"Revenue growth ({growth * 100:.1f}% baseline) is a direct component "
                f"of the expected-return decomposition; a fall below "
                f"{max(growth - 0.05, 0.0) * 100:.1f}% removes the growth leg of the "
                "return and forces the thesis back onto yield alone."),
        })
    de = metrics.get("debt_equity")
    if isinstance(de, (int, float)):
        items.append({
            "item_type": "risk", "title": "Leverage stays controlled",
            "tracking_mode": "quantitative", "metric": "debt_equity",
            "comparator": "<=", "threshold": round(max(de * 1.5, 1.0), 4),
            "cadence": "quarterly", "lookback": "latest", "confirmation_periods": 2,
            "immediate_kill": False,
            "why_matters": (
                f"Debt/equity of {de:.2f} underwrites the bear-case floor; above "
                f"{max(de * 1.5, 1.0):.2f} the balance sheet starts financing the "
                "return and downside protection erodes."),
        })
    items.append({
        "item_type": "risk", "title": "Competitive intensity shifts",
        "tracking_mode": "qualitative", "metric": None, "comparator": None,
        "threshold": None, "cadence": "quarterly", "lookback": "latest",
        "confirmation_periods": 2, "immediate_kill": False,
        "why_matters": (
            "Structural competitive change is not capturable in a single retained "
            "metric, but it is the most likely root cause if the quantitative margin "
            "and growth items above start breaking together."),
    })
    return items


# --- rendering + reads --------------------------------------------------------------------

def _render_md(ctx: dict, payload: dict) -> str:
    """Render markdown from sections in READING order (derivative of the
    canonical stored payload): title block with decision and fair value vs
    price up front, key-figure lines, and the deterministic tables (scenarios,
    financial history) inline in their sections."""
    body = payload.get("body") or {}
    sections = body.get("sections") or {}
    a = body.get("valuation") or {}
    title_bits = [f"**Decision: {body.get('decision')}**"]
    if isinstance(ctx.get("price"), (int, float)):
        title_bits.append(f"Price {ctx['price']:,.2f}")
    if isinstance(a.get("fair_value_base"), (int, float)):
        fv = f"Base fair value {a['fair_value_base']:,.2f}"
        if a.get("upside_pct") is not None:
            fv += f" ({a['upside_pct']:+.1f}% vs price)"
        title_bits.append(fv)
    lines = [
        f"# Investment Memo — {ctx['company_name']} ({ctx['ticker']})", "",
        " · ".join(title_bits), "",
    ]
    for sec_id, title, subs in MEMO_OUTLINE:
        sec = sections.get(sec_id) or {}
        lines += [f"## {title}", "", sec.get("section_thesis", ""), ""]
        key_figures = sec.get("key_figures") or []
        if key_figures:
            lines += ["**Key figures:** " + " · ".join(
                f"{k['label']} {k['value']}" for k in key_figures), ""]
        for sub in subs:
            lines += [f"### {sub.replace('_', ' ').title()}", "",
                      (sec.get("subsections") or {}).get(sub, ""), ""]
        for name, table in (sec.get("tables") or {}).items():
            lines += _md_table(name, table)
    if a.get("fair_value_base") is not None:
        lines += [
            "---", "",
            f"*Deterministic valuation anchors: base fair value "
            f"{a['fair_value_base']:,.2f} ({a.get('method')}); upside "
            f"{a.get('upside_pct')}%, downside {a.get('downside_pct')}%.*", "",
        ]
    return "\n".join(lines)


def _md_table(name: str, table: dict) -> list[str]:
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    if not cols or not rows:
        return []
    out = [f"**{name.replace('_', ' ').title()}**", "",
           "| " + " | ".join(str(c) for c in cols) + " |",
           "|" + "---|" * len(cols)]
    out += ["| " + " | ".join("n/a" if x is None else str(x) for x in r) + " |"
            for r in rows]
    out.append("")
    return out


def memo_current(stores) -> dict:
    wb = stores.runs.get_workbench(CAPABILITY)
    intake_wb = stores.runs.get_workbench(INTAKE_KEY) or {}
    status = stage.stage_status(wb)
    rows = {r["ticker"]: r for r in (wb or {}).get("rows") or []}
    order = [str(i["ticker"]).upper() for i in intake_wb.get("items") or []]
    for t in rows:
        if t not in order:
            order.append(t)
    intake = [{
        "ticker": t,
        "state": (rows.get(t) or {}).get("state", "pending"),
        "artifact_id": (rows.get(t) or {}).get("artifact_id"),
        "decision": (rows.get(t) or {}).get("decision"),
    } for t in order]
    return {"status": status, "intake": intake, "run_id": (wb or {}).get("run_id"),
            "error": (wb or {}).get("error")}
