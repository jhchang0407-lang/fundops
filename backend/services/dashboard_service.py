"""Dashboard projection service.

The Dashboard is a decision/attention queue projected from sources — it never
duplicates truth (CONTEXT). `rebuild` reprojects Needs Decision, Portfolio
Review (Portfolio Pressure + Constitution-Fit Opportunity lists with visible
rank sources), and Needs Attention; `overview` is a cheap read shaped to the
api-contract. Idempotent via the dashboard store's source-version dedupe.
Evidence-first language only — never buy/sell instructions.
"""

from __future__ import annotations

import logging

log = logging.getLogger("fundops.dashboard")

# Pressure ranking: broken > watching-with-change > concentration > stale coverage.
# Severity order for the Portfolio Pressure List, matched against the item's
# rank_source label (see _project_portfolio_pressure rank_label values).
_PRESSURE_RANK_PREFIXES = [
    ("Thesis health broken", 0),
    ("Thesis health watching", 1),
    ("Concentration", 2),
    ("Coverage", 3),
]
RECENT_ACTIVITY_LIMIT = 15


def rebuild(stores) -> dict:
    """Reproject all dashboard sections from their sources (idempotent)."""
    holdings = stores.portfolio.holdings()
    held = {h["ticker"] for h in holdings}
    _project_needs_decision(stores)
    _project_portfolio_pressure(stores, holdings)
    _project_constitution_fit(stores, held)
    _project_needs_attention(stores, holdings)
    open_items = stores.dashboard.open_items()
    return {"ok": True, "open_items": len(open_items)}


# --- Needs Decision -------------------------------------------------------------------

def _project_needs_decision(stores) -> None:
    proposal = stores.constitution.pending_proposal()
    if proposal:
        payload = proposal.get("payload") or {}
        stores.dashboard.upsert_item(
            "decision", "needs_decision", "strategy_proposal",
            proposal["id"], proposal["created_at"],
            title="Strategy proposal awaiting your decision",
            body=payload.get("summary") or proposal.get("rationale"),
            severity="normal",
            rank_source="Pending strategy proposal",
            evidence_refs=[{"kind": "strategy_proposal", "id": proposal["id"]}],
        )
    for rec in stores.learning.records(kind="recommendation"):
        if rec.get("confidence_label") != "recommendation_ready":
            continue
        payload = rec.get("payload") or {}
        change = payload.get("proposed_change") or {}
        stores.dashboard.upsert_item(
            "decision", "needs_decision", "learning_recommendation",
            rec["id"], rec["created_at"],
            title=f"Learning recommendation: {change.get('summary', 'review a suggested change')}",
            body=payload.get("teaching_note"),
            severity="normal",
            rank_source=(f"Pattern across {len(payload.get('supporting_tickers') or [])} "
                         f"outcome evaluations"),
            evidence_refs=[{"kind": "learning_record", "id": rec["id"]}],
        )


# --- Portfolio Review: pressure (held) -------------------------------------------------

def _project_portfolio_pressure(stores, holdings: list[dict]) -> None:
    from backend.workflows import thesis_health  # lazy: avoids import cycles
    proj = stores.constitution.projection("portfolio_review")
    settings = (proj or {}).get("settings") or {}
    conc_pct = float(settings.get("concentration_flag_pct", 20.0))
    for h in holdings:
        ticker = h["ticker"]
        # (rank, severity, category_title, rank_label, full_description)
        reasons: list[tuple[int, str, str, str, str]] = []
        refs: list[dict] = []
        plan = thesis_health.active_plan(stores, ticker)
        label = thesis_health.summary_for(stores, ticker)
        if plan:
            refs.append({"kind": "thesis_health_plan", "id": plan["id"]})
            refs.append({"kind": "memo", "id": plan["memo_artifact_id"]})
        if label in ("Broken", "Watching"):
            items = thesis_health.plan_items(stores, plan["id"]) if plan else []
            status = "broken" if label == "Broken" else "watch"
            hits = [i for i in items
                    if i["tracking_mode"] == "quantitative" and i["status"] == status]
            detail = "; ".join(
                f"{i['item_type'].replace('_', ' ')} {i['metric'] or i['title']} "
                + (f"confirmed {i['consecutive_breaches']} period(s)" if status == "broken"
                   else f"breached {i['consecutive_breaches']} period(s)")
                for i in hits[:2]
            ) or "status-driving watch items under pressure"
            if label == "Broken":
                reasons.append((0, "high", "Thesis pressure", "Thesis health broken",
                                f"Thesis health Broken — {detail}"))
            else:
                reasons.append((1, "normal", "Thesis pressure", "Thesis health watching",
                                f"Thesis health Watching — {detail}"))
        if h["weight"] is not None and h["weight"] * 100 > conc_pct:
            reasons.append((2, "normal", "Sizing pressure",
                            f"Concentration {h['weight'] * 100:.1f}% (limit {conc_pct:.0f}%)",
                            f"Concentration: {h['weight'] * 100:.1f}% of portfolio, "
                            f"above the {conc_pct:.0f}% flag threshold"))
        if h["coverage_state"] in ("stale", "failed", "queued", "none"):
            reasons.append((3, "normal", "Coverage gap",
                            f"Coverage {h['coverage_state']}",
                            f"Memo-backed thesis coverage is {h['coverage_state']} — "
                            f"no fresh thesis-health-ready memo"))
        if not reasons:
            stores.dashboard.resolve_source("portfolio_pressure", ticker)
            continue
        reasons.sort()
        _rank, severity, category, rank_label, _desc = reasons[0]
        refresh = stores.ws.query_one(
            "SELECT id FROM thesis_health_refreshes WHERE ticker = ? "
            "ORDER BY ran_at DESC LIMIT 1", (ticker,),
        )
        stores.dashboard.upsert_item(
            "attention", "portfolio_review", "portfolio_pressure", ticker,
            refresh["id"] if refresh else h["updated_at"],
            ticker=ticker,
            title=category,
            body="Worth reviewing: " + "; ".join(r[4] for r in reasons) + ".",
            severity=severity,
            rank_source=rank_label,
            evidence_refs=refs,
        )


# --- Portfolio Review: constitution-fit opportunities (non-held) ------------------------

def _project_constitution_fit(stores, held: set[str]) -> None:
    from backend.workflows import thesis_health  # lazy
    candidates: dict[str, dict] = {}

    def cand(ticker: str) -> dict:
        return candidates.setdefault(
            ticker, {"parts": [], "refs": [], "score": 0.0, "version": None})

    # Latest IC pass verdict per ticker, constitution-fit ranked by gate score.
    seen: set[str] = set()
    for r in stores.ws.query("SELECT * FROM ic_verdicts ORDER BY created_at DESC"):
        ticker = r["ticker"]
        if ticker in seen:
            continue
        seen.add(ticker)
        if r["verdict"] != "pass" or ticker in held:
            continue
        c = cand(ticker)
        vnum = None
        if r["constitution_version_id"]:
            version = stores.constitution.get_version(r["constitution_version_id"])
            vnum = version["version_number"] if version else None
        gate = r["gate_score"] or 0.0
        c["parts"].append(f"IC pass {gate:.0f}/100" + (f" under v{vnum}" if vnum else ""))
        c["score"] = max(c["score"], gate)
        c["refs"].append({"kind": "ic_verdict", "id": r["id"], "gate_score": gate})
        c["version"] = c["version"] or r["artifact_id"] or r["id"]

    # Memo-backed tickers with intact thesis health.
    memo_tickers = [r["ticker"] for r in stores.ws.query(
        "SELECT DISTINCT ticker FROM artifacts WHERE kind = 'investment_memo' "
        "AND ticker IS NOT NULL")]
    for ticker in memo_tickers:
        if ticker in held:
            continue
        if thesis_health.summary_for(stores, ticker) != "Intact":
            continue
        memo = stores.artifacts.latest_for_ticker(ticker, "investment_memo")
        if not memo:
            continue
        decision = ((((memo.get("payload") or {}).get("body") or {})
                     .get("sections") or {}).get("decision_summary") or {})
        decision = (decision.get("fields") or {}).get("decision")
        c = cand(ticker)
        c["parts"].append((f"memo {decision}" if decision else "memo-backed")
                          + "; thesis health Intact")
        c["refs"].append({"kind": "memo", "id": memo["id"]})
        c["version"] = c["version"] or memo["id"]

    # Top-5 latest screener ranking.
    run = stores.runs.latest_run("screener")
    if run:
        for r in stores.artifacts.screener_results(run["id"])[:5]:
            ticker = r["ticker"]
            if ticker in held or not r["passed"]:
                continue
            c = cand(ticker)
            c["parts"].append(f"screener rank #{r['rank']} in latest run")
            c["refs"].append({"kind": "screener_result", "id": r["id"]})
            c["version"] = c["version"] or r["snapshot_artifact_id"] or r["id"]

    for ticker, c in candidates.items():
        if not c["parts"]:
            continue
        parts = c["parts"]
        stores.dashboard.upsert_item(
            "attention", "portfolio_review", "constitution_fit", ticker, c["version"],
            ticker=ticker,
            title="Constitution-fit opportunity",
            body="Retained evidence worth reviewing: " + "; ".join(parts) + ".",
            severity="normal",
            # Rank source is the strongest single signal (parts are appended in
            # priority order: IC pass, then memo, then screener rank).
            rank_source=parts[0],
            evidence_refs=c["refs"],
        )
    # An opportunity that became held is no longer a non-held opportunity.
    for ticker in held:
        stores.dashboard.resolve_source("constitution_fit", ticker)


# --- Needs Attention --------------------------------------------------------------------

def _project_needs_attention(stores, holdings: list[dict]) -> None:
    from backend.workflows import thesis_health  # lazy
    # Workflow run failures (operational failure ≠ investment judgment).
    for run in stores.runs.recent_runs(30):
        if run["status"] != "failed":
            continue
        stores.dashboard.upsert_item(
            "attention", "needs_attention", "workflow_failure",
            run["id"], run.get("finished_at") or run["started_at"],
            title=f"{run['kind']} run failed",
            body=run.get("error") or "Workflow run ended in a failed state.",
            severity="normal",
            evidence_refs=[{"kind": "workflow_run", "id": run["id"]}],
        )
    # Coverage failures still visible on holdings (dedupe with queue-time items).
    open_attention = stores.dashboard.open_items("needs_attention")
    covered_failures = {i["source_id"] for i in open_attention
                        if i["source_type"] == "coverage_failure"}
    for h in holdings:
        if h["coverage_state"] == "failed" and h["ticker"] not in covered_failures:
            stores.dashboard.upsert_item(
                "attention", "needs_attention", "coverage_failure",
                h["ticker"], h["updated_at"], ticker=h["ticker"],
                title=f"Coverage memo failed — {h['ticker']}",
                body="This holding lacks usable memo-backed thesis coverage.",
                severity="normal",
            )
    # Repeated data gaps degrade monitoring quality (same key as refresh-time).
    for plan in thesis_health.active_plans(stores):
        for item in thesis_health.plan_items(stores, plan["id"]):
            if item["tracking_mode"] == "quantitative" and item["data_gap_count"] >= 2:
                stores.dashboard.upsert_item(
                    "attention", "needs_attention", "data_gap",
                    item["id"], str(item["data_gap_count"]), ticker=plan["ticker"],
                    title=f"Repeated thesis-health data gaps — {plan['ticker']}",
                    body=(f"Watch item '{item['title']}' has {item['data_gap_count']} "
                          f"consecutive data gaps; its prior status is preserved."),
                    severity="low",
                    evidence_refs=[{"kind": "thesis_health_plan", "id": plan["id"]}],
                )


# --- overview ----------------------------------------------------------------------------

def _pressure_sort_key(item: dict) -> tuple:
    rank = 4
    for prefix, r in _PRESSURE_RANK_PREFIXES:
        if (item.get("rank_source") or "").startswith(prefix):
            rank = r
            break
    return (rank, item.get("ticker") or "")


def _opportunity_sort_key(item: dict) -> tuple:
    score = max((ref.get("gate_score") or 0.0 for ref in item.get("evidence_refs") or []
                 if isinstance(ref, dict)), default=0.0)
    return (-score, item.get("ticker") or "")


def overview(stores) -> dict:
    """GET /api/dashboard payload (read-only; nothing expensive on page view)."""
    review = stores.dashboard.open_items("portfolio_review")
    pressure = sorted((i for i in review if i["source_type"] == "portfolio_pressure"),
                      key=_pressure_sort_key)
    opportunities = sorted((i for i in review if i["source_type"] == "constitution_fit"),
                           key=_opportunity_sort_key)
    activity: list[dict] = []
    for run in stores.runs.recent_runs(RECENT_ACTIVITY_LIMIT):
        activity.append({"kind": "run", "title": f"{run['kind']} run {run['status']}",
                         "ticker": None, "run_id": run["id"], "artifact_id": None,
                         "created_at": run["started_at"]})
    for art in stores.artifacts.recent(limit=RECENT_ACTIVITY_LIMIT):
        title = art["kind"].replace("_", " ")
        if art.get("ticker"):
            title += f" — {art['ticker']}"
        activity.append({"kind": art["kind"], "title": title, "ticker": art.get("ticker"),
                         "run_id": art.get("run_id"), "artifact_id": art["id"],
                         "created_at": art["created_at"]})
    activity.sort(key=lambda a: a["created_at"], reverse=True)
    # The pressure list is a frozen projection; weights drift as the portfolio
    # changes. Attach each held ticker's LIVE weight and flag the section stale
    # when the concentration picture has moved since it was last rebuilt — so a
    # 2-year-old "40%" isn't presented as current (read-only; no reproject here).
    holdings = {h["ticker"]: h for h in stores.portfolio.holdings()}
    proj = stores.constitution.projection("portfolio_review")
    conc_pct = float(((proj or {}).get("settings") or {}).get("concentration_flag_pct", 20.0))
    for item in pressure:
        h = holdings.get(item.get("ticker"))
        if h and h.get("weight") is not None:
            item["live_weight_pct"] = round(h["weight"] * 100, 1)
    live_over = {t for t, h in holdings.items()
                 if h.get("weight") is not None and h["weight"] * 100 > conc_pct}
    flagged = {i.get("ticker") for i in pressure if "Concentration" in (i.get("title") or "")}
    review_tickers = {i.get("ticker") for i in pressure if i.get("ticker")}
    stale = live_over != flagged or bool(review_tickers - set(holdings))
    return {
        "needs_decision": stores.dashboard.open_items("needs_decision"),
        "portfolio_review": {"pressure": pressure, "opportunities": opportunities,
                             "stale": stale},
        "needs_attention": stores.dashboard.open_items("needs_attention"),
        "recent_activity": activity[:RECENT_ACTIVITY_LIMIT],
    }


def respond_item(stores, item_id: str, response: str, payload: dict | None = None) -> dict:
    """Record a Dashboard Item Response; judgment-revealing responses become
    learning feedback signals, decision responses become approval records."""
    res = stores.dashboard.respond(item_id, response, payload)
    item = res["item"]
    if res.get("duplicate"):
        # Already settled (double-click / stale tab): no learning signal, no
        # approval record, no proposal effect — just report the settled state.
        return {"ok": True, "status": res["status"], "already_responded": True}
    if res["kind"] in ("feedback", "both"):
        stores.learning.add_record(
            "feedback_signal",
            {"response": response, "item_title": item["title"],
             "source_type": item["source_type"], "source_id": item["source_id"],
             "payload": payload},
            ticker=item.get("ticker"),
            lineage={"dashboard_item_id": item_id,
                     "source_version": item["source_version"]},
        )
    if item["source_type"] in ("strategy_proposal", "learning_recommendation") \
            and response in ("accept", "reject"):
        stores.dashboard.record_approval(
            item["source_type"], item["source_id"], response,
            target_version=item["source_version"],
        )
    out: dict = {"ok": True, "status": res["status"]}
    if item["source_type"] == "strategy_proposal" and response in ("accept", "reject"):
        # The Dashboard is a real approval surface: accepting here activates
        # the proposal exactly like Chat approval (guardrails re-validated
        # inside accept_proposal); rejecting cancels it. An approval record
        # must never exist without its effect.
        from backend.services import strategy_service
        try:
            if response == "accept":
                version = strategy_service.accept_proposal(stores, item["source_id"])
                out["version_id"] = version["id"]
                out["note"] = (f"Constitution v{version['version_number']} is now "
                               "active and wired.")
            else:
                stores.constitution.decide_proposal(item["source_id"], "rejected")
                out["note"] = "Proposal rejected — nothing was changed."
        except (ValueError, LookupError) as exc:
            out["note"] = (f"Decision recorded but not applied: {exc} "
                           "The proposal may have been superseded — review in Chat.")
    if item["source_type"] == "learning_recommendation" and response == "accept":
        # Learning -> Constitution loop: an accepted recommendation becomes a
        # real pending Strategy Change Proposal (never an auto-applied rule) —
        # exactly what the recommendation's caveats promise.
        proposal = _recommendation_to_proposal(stores, item["source_id"])
        if proposal:
            out["proposal_id"] = proposal["id"]
            out["note"] = ("A strategy proposal was drafted from this recommendation — "
                           "review and approve it in Chat before anything changes.")
        else:
            # Never consume an acceptance silently: say why no draft exists.
            out["note"] = ("Accepted, but no proposal could be drafted — an active "
                           "Constitution is required and the recommendation must "
                           "name a catalog metric not already under review. "
                           "Nothing changed.")
    # Make judgment responses DO what their label implies, and always report
    # back so a feedback action never looks like a silent dismiss. (watch /
    # interested only appear on constitution-fit items, so they never collide
    # with the proposal/recommendation notes set above.)
    ticker = (item.get("ticker") or "").upper()
    if response == "watch" and ticker:
        wl = stores.context.watchlist_by_name("Watching") or stores.context.create_watchlist("Watching")
        stores.context.add_ticker(wl["id"], ticker)
        out["note"] = (f"Added {ticker} to your Watching list — and recorded the "
                       "signal for future strategy learning.")
    elif response == "interested" and ticker:
        from backend.workflows import thesis as _thesis
        intake = stores.runs.get_workbench(_thesis.INTAKE_KEY) or {}
        items = list(intake.get("items") or [])
        if not any(str(i.get("ticker", "")).upper() == ticker for i in items):
            items.append({"ticker": ticker, "provenance": "interested"})
        intake["items"] = items
        intake["tickers"] = [i["ticker"] for i in items]
        stores.runs.set_workbench(_thesis.INTAKE_KEY, intake)
        out["note"] = (f"Queued {ticker} for your next Thesis run — and recorded the "
                       "signal. Nothing runs until you start Thesis.")
    elif res["kind"] in ("feedback", "both") and "note" not in out:
        label = _RESPONSE_LABELS.get(response, response.replace("_", " "))
        out["note"] = (f"Recorded “{label}”" + (f" on {ticker}" if ticker else "")
                       + " — this trains your future strategy suggestions.")
    return out


# Human labels for the toast confirmation of a judgment response.
_RESPONSE_LABELS = {
    "interested": "Interested", "watch": "Watch", "not_strategy_fit": "Not strategy fit",
    "too_risky": "Too risky", "already_know": "Already know", "reviewed": "Reviewed",
    "not_material": "Not material", "thesis_still_intact": "Thesis still intact",
    "already_acted": "Already acted", "keep_watching": "Keep watching", "dismiss": "Dismissed",
}


def _recommendation_to_proposal(stores, record_id: str) -> dict | None:
    """Convert an accepted learning recommendation into a pending strategy
    proposal: the active Constitution's rules plus the recommended
    research-review criterion. Returns None if the record is unusable."""
    rec = stores.learning.get(record_id)
    if not rec:
        return None
    change = (rec.get("payload") or {}).get("proposed_change") or {}
    metric = change.get("metric")
    if not metric:
        return None
    active = stores.constitution.active_version()
    if not active:
        return None
    rules = []
    for c in active.get("criteria", []):
        rules.append({k: c.get(k) for k in (
            "criterion_id", "kind", "metric", "operator", "value", "weight",
            "data_support_level", "rule_rationale", "rule_source", "interpretation",
        )})
    criterion_id = f"research_review.{metric}_learning"
    if any(r["criterion_id"] == criterion_id for r in rules):
        return None  # already proposed/active — don't stack duplicates
    rules.append({
        "criterion_id": criterion_id,
        "kind": change.get("kind") or "research_review",
        "metric": metric,
        "operator": None,
        "value": None,
        "weight": None,
        "data_support_level": "research_review",
        "rule_rationale": (rec.get("payload") or {}).get("teaching_note")
                          or change.get("summary") or "learning recommendation",
        "rule_source": f"learning_recommendation:{record_id}",
        "interpretation": change.get("summary"),
    })
    universe = stores.constitution.active_universe() or {}
    payload = {
        "summary": f"Learning recommendation accepted: {change.get('summary', metric)}",
        "north_star": active.get("north_star"),
        "style_blend": active.get("style_blend"),
        "narrative": active.get("narrative"),
        "rules": rules,
        "universe": {"name": universe.get("name"), "tickers": universe.get("tickers")}
                    if universe else None,
    }
    from backend.domain import guardrails
    validation = guardrails.validate_proposal(payload)
    if validation.errors:
        log.warning("recommendation %s could not become a proposal: %s",
                    record_id, validation.errors)
        return None
    proposal = stores.constitution.create_proposal(
        payload, validation.to_dict(),
        rationale=payload["summary"], chat_session_id=None, kind="learning",
    )
    stores.dashboard.upsert_item(
        "decision", "needs_decision", "strategy_proposal",
        proposal["id"], proposal["created_at"],
        title="Strategy proposal from accepted learning recommendation",
        body=payload["summary"], severity="normal",
        rank_source="Learning recommendation",
        evidence_refs=[{"kind": "learning_record", "id": record_id}],
    )
    return proposal
