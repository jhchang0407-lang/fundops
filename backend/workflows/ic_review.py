"""IC Review workflow (ADR-0012, ADR-0036).

Semantic review is ONE deep model call per ticker returning component
judgments against the fixed component lists in backend.domain.ic_gate; all
arithmetic (pillar scores, blend, cutoff, hurdle verdicts) is deterministic in
domain code. Hard hurdles are pre-checked deterministically where the metric
is measurable; a deterministically-confirmed result always wins over the
model's interpretation — the model may only judge ambiguous (unevaluable)
signals. Every verdict persists as a typed row plus an ic_verdict artifact
whose payload is the saved IC Verdict Evidence.
"""

from __future__ import annotations

import json

from backend.core.ai import PROMPT_VERSION, get_ai
from backend.core.workspace import now_iso
from backend.domain import artifact_schemas, labels
from backend.domain.criteria import Criterion, evaluate, ic_hurdles
from backend.domain.ic_gate import (
    CONVICTION_COMPONENTS, DATA_QUALITY_COMPONENTS, FIT_COMPONENTS,
    ComponentJudgment, HurdleFinding, score_gate,
)
from backend.workflows import evidence_packets as ep
from backend.workflows import stage

CAPABILITY = "ic_review"
WORKBENCH_KEY = "ic"
INTAKE_KEY = "ic_intake"
MEMO_INTAKE_KEY = "memo_intake"
MAX_ATTEMPTS = 3

# Thesis-level return fields resolved from the thesis artifact, not financials.
_THESIS_METRICS = ("expected_return", "base_return", "discount_pct", "bear_return")

SYSTEM = (
    "You are the FundOps investment committee reviewer. Judge the thesis evidence "
    "package semantically, component by component. For every named component report "
    "state supported|unknown|contradicted with a 0-100 score and a one-line note that "
    "cites concrete evidence from the package (a figure, trend, peer comparison, or "
    "constitution-check outcome) — e.g. 'thesis growth claim consistent with 11% "
    "revenue CAGR', never generic praise. Use 'unknown' when evidence is absent — "
    "never guess. Deterministic hurdle pre-check results are authoritative evidence: "
    "a confirmed miss stays a miss. Write metric names in plain English (Free Cash "
    "Flow Yield, Gross Margin) — never raw identifiers like fcf_yield."
)

SHAPE = (
    '{"conviction_components": [{"component": str, "state": "supported|unknown|contradicted", '
    '"score": 0-100, "note": "evidence-citing one-liner"}], '
    '"fit_components": [same shape], "data_quality_components": [same shape], '
    '"hurdle_findings": [{"criterion_id": str, "met": bool, "explanation": str, '
    '"observed": number|null, "threshold": number|null}], '
    '"rationale": "3-5 sentence verdict rationale citing concrete evidence and '
    'hurdle outcomes"}'
)


# --- run lifecycle ------------------------------------------------------------------

def prepare_run(stores, trigger: str = "user") -> str:
    active = stores.constitution.active_version()
    rid = stores.runs.start_run(
        CAPABILITY, trigger, constitution_version_id=active["id"] if active else None,
    )
    wb = stores.runs.get_workbench(WORKBENCH_KEY) or {}
    stores.runs.set_workbench(WORKBENCH_KEY, {**wb, "run_id": rid, "status": "running"})
    return rid


async def run_ic(stores, trigger: str = "user") -> str:
    rid = prepare_run(stores, trigger)
    await execute_run(stores, rid)
    return rid


async def execute_run(stores, run_id: str) -> None:
    try:
        await _execute(stores, run_id)
    except Exception as exc:  # noqa: BLE001
        stores.runs.finish_run(run_id, "failed", error=str(exc))
        wb = stores.runs.get_workbench(WORKBENCH_KEY) or {}
        if wb.get("run_id") == run_id:
            stores.runs.set_workbench(
                WORKBENCH_KEY, {**wb, "status": "failed", "error": str(exc)}
            )


async def _execute(stores, run_id: str) -> None:
    run = stores.runs.get_run(run_id) or {}
    cv_id = run.get("constitution_version_id")
    active = stores.constitution.active_version() or {}
    proj = stores.constitution.projection(CAPABILITY, cv_id) if cv_id else None
    settings = (proj or {}).get("settings") or {}
    hurdles = [Criterion.from_dict(d) for d in settings.get("hurdles") or []]
    if proj is None and cv_id:
        hurdles = ic_hurdles(stores.constitution.criteria_objects(cv_id))
    ctx = {
        "cv_id": cv_id,
        "run_id": run_id,
        "hurdles": hurdles,
        "blend": settings.get("gate_score_blend"),
        "cutoff": settings.get("pass_cutoff"),
        "north_star": settings.get("north_star") or active.get("north_star") or "",
        "criteria": [
            {k: c.get(k) for k in ("criterion_id", "kind", "metric", "operator",
                                   "value", "interpretation")}
            for c in (active.get("criteria") or [])
        ],
    }

    intake = stores.runs.get_workbench(INTAKE_KEY) or {}
    items = intake.get("items") or [
        {"ticker": t} for t in intake.get("tickers") or []
    ]
    order = [str(i["ticker"]).upper() for i in items]
    prior_rows = {
        r["ticker"]: r
        for r in (stores.runs.get_workbench(WORKBENCH_KEY) or {}).get("rows") or []
    }

    rows: dict[str, dict] = {}
    reviewed = 0
    for item in items:
        t = str(item["ticker"]).upper()
        prior = prior_rows.get(t)
        if prior and prior.get("verdict") in ("pass", "fail"):
            rows[t] = prior  # never re-judge in the same run context
            continue
        rows[t] = await _review_one(stores, t, item, ctx)
        reviewed += 1

    wb = {
        "run_id": run_id,
        "status": "completed",
        "order": order,
        "rows": [rows[t] for t in order],
    }
    stores.runs.set_workbench(WORKBENCH_KEY, wb)
    selection = _selection(wb)
    _refresh_memo_intake(stores, wb)
    failed = [t for t in order if rows[t].get("state") == "failed"]
    stores.runs.finish_run(run_id, "completed", stats={
        "intake": len(order), "reviewed": reviewed,
        "passes": len(selection),
        "fails": len([t for t in order if rows[t].get("verdict") == "fail"]),
        "failed_steps": len(failed),
    })


async def _review_one(stores, ticker: str, item: dict, ctx: dict) -> dict:
    run_id = ctx["run_id"]
    step_id = stores.runs.add_step(run_id, CAPABILITY, ticker)
    thesis_art = None
    if item.get("thesis_artifact_id"):
        thesis_art = stores.artifacts.get(item["thesis_artifact_id"])
    if thesis_art is None:
        thesis_art = stores.artifacts.latest_for_ticker(ticker, "thesis")
    if thesis_art is None:
        stores.runs.finish_step(step_id, "failed", error="no completed thesis artifact")
        return {"ticker": ticker, "state": "failed", "verdict": None,
                "error": "no completed thesis artifact"}

    ent = stores.identity.ensure_entity(ticker)
    packet = ep.build_company_packet(stores, ticker, ent["id"])
    metrics = packet["latest"]
    price = packet["price_context"].get("price")
    body = (thesis_art.get("payload") or {}).get("body") or {}
    rp = body.get("return_potential") or {}

    pre = _deterministic_hurdles(ctx["hurdles"], rp, metrics, price)
    # IC Review Evidence Package: full thesis payload + constitution + hurdles
    # + return components + company evidence (trends, peers, constitution
    # check) so component notes can cite evidence. Memo content is NOT
    # consumed here.
    package = {
        "ticker": ticker,
        "thesis": body,
        "constitution": {"north_star": ctx["north_star"], "criteria": ctx["criteria"]},
        "ic_hurdles": [
            {"criterion_id": c.criterion_id, "metric": c.metric,
             "operator": c.operator, "threshold": c.value,
             "deterministic_pre_check": p}
            for c, p in zip(ctx["hurdles"], pre)
        ],
        "return_components": rp.get("components") or {},
        "expected_return_pct": rp.get("expected_return_pct"),
        "company_evidence": {
            "trends": packet["trends"],
            "peers": packet["peers"],
            "constitution_check": packet["constitution_check"]["rows"],
            "data_quality_notes": packet["data_quality_notes"],
        },
    }
    user = (
        "Review this IC evidence package and judge exactly these components:\n"
        f"conviction: {list(CONVICTION_COMPONENTS)}\n"
        f"constitution_fit: {list(FIT_COMPONENTS)}\n"
        f"data_quality: {list(DATA_QUALITY_COMPONENTS)}\n\n"
        "Each component note must cite a specific figure, trend, peer position, "
        "constitution-check row, or hurdle outcome from the package. The rationale "
        "is 3-5 sentences referencing the decisive evidence and every hurdle "
        "outcome.\n\n"
        f"Evidence package:\n{json.dumps(package, default=str)}"
    )
    stub = _stub_review(rp.get("expected_return_pct") or 0.0, pre, packet)

    last_error: str | None = None
    result = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            stores.runs.retry_step(step_id)
        try:
            result = await get_ai().complete_json(
                CAPABILITY, SYSTEM, user, SHAPE, tier="deep", run_id=run_id, stub=stub,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_error = f"model call failed: {exc}"
            result = None
    if result is None:
        stores.runs.finish_step(step_id, "failed", error=last_error or "review failed")
        return {"ticker": ticker, "state": "failed", "verdict": None, "error": last_error}
    result = result if isinstance(result, dict) else {}

    conv = _judgments(result.get("conviction_components"), CONVICTION_COMPONENTS)
    fit = _judgments(result.get("fit_components"), FIT_COMPONENTS)
    dq = _judgments(result.get("data_quality_components"), DATA_QUALITY_COMPONENTS)
    findings = _merge_hurdles(ctx["hurdles"], pre, result.get("hurdle_findings"))
    gate = score_gate(conv, fit, dq, findings, blend=ctx["blend"], cutoff=ctx["cutoff"])
    rationale = str(result.get("rationale") or "").strip() or (
        gate.fail_reason
        or f"gate score {gate.gate_score:.0f} meets cutoff {gate.cutoff:.0f}"
    )
    # Raw metric ids must never reach the user-facing record (same safety net
    # as chat replies — the model sees ids in the evidence and echoes them).
    rationale = labels.humanize_chat_text(rationale)
    # Honest record when the Constitution wires no hard hurdles: the verdict
    # is score-based only, and the artifact must say so rather than show an
    # unexplained empty findings list.
    hurdle_note = None
    if not ctx["hurdles"]:
        hurdle_note = (
            "No hard hurdles are wired in this Constitution — this verdict is "
            "score-based only (conviction, constitution fit, and data quality "
            "against the cutoff), with no deterministic hurdle layer.")

    bundle_id = stores.evidence.freeze_bundle({
        "kind": "ic_review",
        "ticker": ticker,
        "thesis_artifact_id": thesis_art["id"],
        "constitution_version": ctx["cv_id"],
        "hurdles": [c.criterion_id for c in ctx["hurdles"]],
        "prompt_version": PROMPT_VERSION,
    })
    kernel = artifact_schemas.make_kernel(
        "ic_verdict", ticker, ent["id"], ctx["cv_id"], bundle_id, now_iso(),
    )
    payload = {**kernel, "body": {
        **gate.to_dict(),
        "rationale": rationale,
        "thesis_artifact_id": thesis_art["id"],
        "return_potential": rp,
        **({"hurdle_note": hurdle_note} if hurdle_note else {}),
    }}
    payload["validation"] = artifact_schemas.validate_ic_verdict(payload).to_dict()
    rendered = rationale + (f"\n\n_{hurdle_note}_" if hurdle_note else "")
    aid = stores.artifacts.save_artifact(
        "ic_verdict", payload, ticker=ticker, entity_id=ent["id"], run_id=run_id,
        rendered_md=rendered, evidence_bundle_id=bundle_id,
        constitution_version_id=ctx["cv_id"],
    )
    vid = stores.artifacts.save_ic_verdict(
        ticker=ticker, verdict=gate.verdict, run_id=run_id, entity_id=ent["id"],
        thesis_artifact_id=thesis_art["id"], conviction=gate.conviction,
        constitution_fit=gate.constitution_fit, data_quality=gate.data_quality,
        gate_score=gate.gate_score, blend=gate.blend, cutoff=gate.cutoff,
        components=gate.components, hurdle_findings=[h.to_dict() for h in findings],
        rationale=rationale, constitution_version_id=ctx["cv_id"], artifact_id=aid,
    )
    stores.runs.finish_step(step_id, "completed", detail={
        "verdict": gate.verdict, "gate_score": round(gate.gate_score, 1),
    })
    return {
        "ticker": ticker, "company_name": ent.get("name") or ticker, "price": price,
        "state": "completed", "verdict": gate.verdict,
        "gate_score": round(gate.gate_score, 1), "conviction": round(gate.conviction, 1),
        "constitution_fit": round(gate.constitution_fit, 1),
        "data_quality": round(gate.data_quality, 1), "rationale": rationale,
        "hurdle_findings": [h.to_dict() for h in findings],
        "is_override": False, "artifact_id": aid,
        "thesis_artifact_id": thesis_art["id"], "verdict_id": vid,
    }


# --- deterministic pieces --------------------------------------------------------------

def _deterministic_hurdles(hurdles: list[Criterion], rp: dict, metrics: dict,
                           price: float | None) -> list[dict]:
    """Deterministic hurdle pre-check: evaluate measurable metrics (thesis
    return fields from the thesis payload; financials from the latest
    projection). satisfied None = ambiguous, left to semantic review."""
    out = []
    for c in hurdles:
        observed = None
        if c.metric in _THESIS_METRICS:
            if c.metric in ("expected_return", "base_return"):
                observed = rp.get("expected_return_pct")
            elif c.metric == "discount_pct":
                fv = rp.get("fair_value")
                if isinstance(fv, (int, float)) and fv and price:
                    observed = (fv - price) / fv * 100.0
        else:
            observed = metrics.get(c.metric)
        r = evaluate(c, observed)
        out.append({
            "criterion_id": c.criterion_id, "metric": c.metric,
            "operator": c.operator, "threshold": c.value,
            "observed": r.observed, "met": r.satisfied, "reason": r.reason,
        })
    return out


def _merge_hurdles(hurdles: list[Criterion], pre: list[dict],
                   model_findings) -> list[HurdleFinding]:
    """Deterministically-confirmed results win; the model only decides
    ambiguous (unevaluable) hurdles."""
    by_id = {
        f.get("criterion_id"): f for f in (model_findings or []) if isinstance(f, dict)
    }
    findings = []
    for c, p in zip(hurdles, pre):
        mf = by_id.get(c.criterion_id) or {}
        if p["met"] is not None:
            met = bool(p["met"])
            explanation = (f"deterministic check: observed {p['observed']} vs "
                           f"{c.operator} {c.value}")
            if not met:
                explanation = "confirmed miss — " + explanation
            if mf.get("explanation"):
                explanation += f"; reviewer note: {mf['explanation']}"
            observed = p["observed"]
        else:
            met = bool(mf.get("met", False))
            explanation = (mf.get("explanation")
                           or f"not deterministically measurable ({p['reason']}); "
                              "semantic judgment applied")
            observed = mf.get("observed")
        findings.append(HurdleFinding(
            criterion_id=c.criterion_id, metric=c.metric, met=met,
            explanation=explanation, observed=observed, threshold=c.value,
        ))
    return findings


def _judgments(raw, expected: tuple[str, ...]) -> list[ComponentJudgment]:
    by_name: dict[str, ComponentJudgment] = {}
    for r in raw or []:
        if not isinstance(r, dict) or r.get("component") not in expected:
            continue
        state = r.get("state")
        if state not in ("supported", "unknown", "contradicted"):
            state = "unknown"
        try:
            score = None if r.get("score") is None else float(r["score"])
        except (TypeError, ValueError):
            score = None
        by_name[r["component"]] = ComponentJudgment(
            r["component"], state, score, str(r.get("note") or ""),
        )
    return [by_name.get(n) or ComponentJudgment(n, "unknown", None, "not judged")
            for n in expected]


def _stub_review(expected_return: float, pre: list[dict], packet: dict) -> dict:
    """Offline deterministic judgments: scores scale from the thesis return
    profile (so the stub pipeline produces a sensible pass/fail mix) while
    every component note cites concrete packet evidence — trends, peer
    position, constitution-check rows, retained-data counts."""
    base = max(5.0, min(95.0, 40.0 + float(expected_return or 0.0) * 2.5))
    exp = f"{float(expected_return or 0.0):.1f}%"
    latest = packet["latest"]
    ident = packet["identity"]
    trends = packet["trends"]
    cc = packet["constitution_check"]
    measured = [r for r in cc["rows"] if r["satisfied"] is not None]
    passes = [r for r in measured if r["satisfied"]]
    misses = [r for r in measured if not r["satisfied"]]
    n_annual = max((len(s.get("annual") or []) for s in packet["history"].values()),
                   default=0)
    n_quarterly = max((len(s.get("quarterly") or []) for s in packet["history"].values()),
                      default=0)
    n_metrics = sum(1 for v in latest.values() if v is not None)
    latest_period = next(
        (s["annual"][0]["period_end"] for s in packet["history"].values()
         if s.get("annual")), "n/a",
    )

    growth_fact = (f"{trends['revenue_cagr_pct']}% revenue CAGR over "
                   f"{trends['revenue_cagr_years']}y"
                   if trends.get("revenue_cagr_pct") is not None
                   else f"revenue growth {ep.fmt_value('revenue_growth', latest.get('revenue_growth'))}")
    strongest = ("; ".join(f"{r['rule']} observed {r['observed_display']}"
                           for r in passes[:2])
                 or "no measured constitution passes")
    miss_fact = ("; ".join(f"{r['rule']} observed {r['observed_display']}"
                           for r in misses[:2])
                 or "no measured constitution misses")
    de_fact = (f"debt/equity {latest['debt_equity']:.2f}"
               if isinstance(latest.get("debt_equity"), (int, float))
               else "leverage unmeasured in retained data")
    roic_rank = ep.peer_rank(packet, "roic")
    peer_fact = (f"ROIC {ep.fmt_value('roic', latest.get('roic'))} above "
                 f"{roic_rank[0]} of {roic_rank[1]} retained sector peers"
                 if roic_rank else "no retained peer comparison rows")

    notes = {
        "argument_strength": (f"thesis {exp} return claim consistent with "
                              f"{growth_fact} and "
                              f"{ep.trend_phrase(packet, 'gross_margin')}"),
        "evidence_support": f"strongest constitution evidence: {strongest}",
        "catalyst_or_path_clarity": (f"path is reported execution; {n_quarterly} "
                                     "quarterly period(s) retained for confirmation"),
        "risk_adjusted_downside": f"{de_fact}; {peer_fact}",
        "assumption_sensitivity": (f"{exp} expected return leans on "
                                   f"{growth_fact} persisting"),
        "precedent_support": (f"{n_annual} annual period(s) retained as "
                              "base-rate evidence"),
        "exact_criteria_alignment": (f"{len(passes)} of {len(measured)} measurable "
                                     f"criteria satisfied; {miss_fact}"),
        "north_star_alignment": (f"north star \"{cc.get('north_star') or 'n/a'}\" vs "
                                 f"{strongest}"),
        "anti_signal_avoidance": miss_fact,
        "data_support_confidence": (f"{len(measured)} of {len(cc['rows'])} active "
                                    "criteria deterministically measurable"),
        "data_freshness": f"latest retained observations dated {latest_period}",
        "financial_completeness": (f"{n_metrics} latest metrics, {n_annual} annual / "
                                   f"{n_quarterly} quarterly periods retained"),
        "source_grounding": ("all figures from retained financial observations "
                             "and price marks; no external claims"),
        "entity_correctness": (f"identity resolved: {ident['name']} "
                               f"({ident['ticker']}), sector "
                               f"{ident.get('sector') or 'n/a'}"),
        "return_source_validation": (f"{exp} decomposes into FCF yield "
                                     f"{ep.fmt_value('fcf_yield', latest.get('fcf_yield'))} "
                                     f"plus growth "
                                     f"{ep.fmt_value('revenue_growth', latest.get('revenue_growth'))}"),
        "contradictions": (f"{len(misses)} measured constitution miss(es): {miss_fact}"
                           if misses else "no contradicting evidence rows retained"),
    }

    def comps(names: tuple[str, ...], offset: float) -> list[dict]:
        s = max(5.0, min(95.0, base + offset))
        return [{"component": n, "state": "supported", "score": round(s, 1),
                 "note": notes.get(n, growth_fact)} for n in names]

    pre_misses = [p["criterion_id"] for p in pre if p["met"] is False]
    rationale = (
        f"Deterministic review: thesis expected return {exp} maps to component "
        f"strength {base:.0f}/100. {len(passes)} of {len(measured)} measurable "
        f"constitution criteria are satisfied ({strongest}), and the return claim "
        f"is consistent with {growth_fact}. Hurdle pre-checks: "
        f"{sum(1 for p in pre if p['met'])} met, "
        f"{len(pre_misses)} missed"
        + (f" ({', '.join(pre_misses)})" if pre_misses else "")
        + f", with {n_annual} annual and {n_quarterly} quarterly period(s) of "
          "retained evidence behind the data-quality view."
    )
    return {
        "conviction_components": comps(CONVICTION_COMPONENTS, 0.0),
        "fit_components": comps(FIT_COMPONENTS, 2.0),
        "data_quality_components": comps(DATA_QUALITY_COMPONENTS, 4.0),
        "hurdle_findings": [
            {"criterion_id": p["criterion_id"],
             "met": p["met"] if p["met"] is not None else True,
             "explanation": "stub mirrors deterministic pre-check"}
            for p in pre
        ],
        "rationale": rationale,
    }


# --- reads + override ------------------------------------------------------------------

def _selection(wb: dict) -> list[str]:
    """IC Selection = every pass (no cap) including user promotions."""
    return [r["ticker"] for r in wb.get("rows") or [] if r.get("verdict") == "pass"]


def _intake_rows(stores) -> list[dict]:
    """Handed-off Thesis selection shown as pending IC rows before Run IC
    Review — the selection is immediately visible without a separate send
    (CONTEXT: Thesis→IC handoff)."""
    intake = stores.runs.get_workbench(INTAKE_KEY) or {}
    items = intake.get("items") or [
        {"ticker": t, "provenance": "thesis_selection"} for t in intake.get("tickers") or []
    ]
    order = [str(i["ticker"]).upper() for i in items]
    if not order:
        return []
    by_ticker = {str(i["ticker"]).upper(): i for i in items}
    prices = stores.portfolio.prices()
    rows = []
    for t in order:
        ent = stores.identity.resolve_ticker(t) or {}
        rows.append({
            "ticker": t, "company_name": ent.get("name") or t,
            "state": "pending", "verdict": None, "price": prices.get(t),
            "thesis_artifact_id": (by_ticker.get(t) or {}).get("thesis_artifact_id"),
        })
    return rows


def ic_current(stores) -> dict:
    wb = stores.runs.get_workbench(WORKBENCH_KEY)
    status = stage.stage_status(wb)
    if not wb:
        # No IC Run yet: surface the Thesis handoff as pending rows so the
        # candidates are immediately visible and Run IC Review is meaningful.
        return {"status": "idle", "selection": [], "remaining": _intake_rows(stores)}
    rows = wb.get("rows") or []
    if status != "completed":
        # While running, keep candidates visible — passes promote as they land,
        # everything else stays in the remaining block.
        return {"status": status,
                "selection": [r for r in rows if r.get("verdict") == "pass"],
                "remaining": [r for r in rows if r.get("verdict") != "pass"],
                "run_id": wb.get("run_id"), "error": wb.get("error")}
    return {
        "status": status,
        "run_id": wb.get("run_id"),
        "selection": [r for r in rows if r.get("verdict") == "pass"],
        "remaining": [r for r in rows if r.get("verdict") != "pass"],
    }


def ic_override(stores, ticker: str, action: str) -> dict:
    """User override: a NEW verdict row with is_override=1 and the prior
    verdict preserved (the original verdict and artifact are never mutated).
    Updates IC selection + Memo intake and records the selection event."""
    if action not in ("promote", "remove"):
        raise ValueError(f"unknown override action {action!r} (expected promote|remove)")
    wb = stores.runs.get_workbench(WORKBENCH_KEY)
    if not wb or wb.get("status") != "completed":
        raise ValueError("no completed IC stage output to override")
    ticker = ticker.upper()
    rows = wb.get("rows") or []
    row = next((r for r in rows if r.get("ticker") == ticker), None)
    if row is None or row.get("verdict") not in ("pass", "fail"):
        raise ValueError(f"no IC verdict for {ticker} in the current stage output")
    new_verdict = "pass" if action == "promote" else "fail"
    if row["verdict"] != new_verdict:
        prior = row["verdict"]
        vid = stores.artifacts.save_ic_verdict(
            ticker=ticker, verdict=new_verdict, run_id=wb.get("run_id"),
            thesis_artifact_id=row.get("thesis_artifact_id"),
            conviction=row.get("conviction"), constitution_fit=row.get("constitution_fit"),
            data_quality=row.get("data_quality"), gate_score=row.get("gate_score"),
            hurdle_findings=row.get("hurdle_findings"),
            rationale=f"user override ({action}); prior verdict: {prior}",
            is_override=True, prior_verdict=prior,
            constitution_version_id=(stores.runs.get_run(wb.get("run_id")) or {})
            .get("constitution_version_id"),
            artifact_id=row.get("artifact_id"),
        )
        row.update({"verdict": new_verdict, "is_override": True,
                    "prior_verdict": prior, "verdict_id": vid})
        stores.runs.set_workbench(WORKBENCH_KEY, wb)
    stores.runs.record_selection(
        CAPABILITY, wb.get("run_id"), ticker,
        "promote" if action == "promote" else "dismiss",
    )
    _refresh_memo_intake(stores, wb)
    return ic_current(stores)


def _refresh_memo_intake(stores, wb: dict) -> None:
    rows = {r["ticker"]: r for r in wb.get("rows") or []}
    selection = _selection(wb)
    stores.runs.set_workbench(MEMO_INTAKE_KEY, {
        "source": "ic_review", "source_run_id": wb.get("run_id"),
        "tickers": list(selection),
        "items": [
            {"ticker": t, "provenance": "ic_selection",
             "thesis_artifact_id": (rows.get(t) or {}).get("thesis_artifact_id")}
            for t in selection
        ],
    })
