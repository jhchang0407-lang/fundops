"""Memo-Backed Thesis Health workflow (ADR-0014).

Memo generation drafts the Investment Memo Monitoring Plan; this workflow
persists it as separate structured records (plans, watch items, checks,
refreshes), records memo-time baseline checks, and refreshes statuses through
metadata-gated filing checks. Evaluation is purely deterministic
(backend.domain.thesis_health); LLMs never rejudge quantitative status.

No platform store exists for thesis-health operational records, so this
module is their single write path (ADR-0031 boundary lives here).
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.core.workspace import dumps, new_id, now_iso
from backend.domain import thesis_health as th

HELD_REFRESH_DAYS = 7        # Held Thesis Health Review Cadence
NON_HELD_REFRESH_DAYS = 30   # Non-Held Thesis Health Review Cadence (long-horizon tracking)
YOY_TOLERANCE_DAYS = 45      # same-quarter-last-year matching window
# Filing forms that carry new reported fundamentals (ADR-0059 filings index).
RELEVANT_FILING_FORMS = ["10-K", "10-K/A", "10-Q", "10-Q/A"]

PERIOD_TYPE_FOR_CADENCE = {"quarterly": "quarterly", "annual": "annual",
                           "ttm": "ttm", "slower": "annual"}
# Flow metrics sum over four quarters for TTM; ratio/level metrics average.
FLOW_METRICS = {
    "revenue", "free_cash_flow", "operating_cash_flow", "net_income",
    "gross_profit", "operating_income", "ebitda", "eps",
}


def _parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --- operational record access ----------------------------------------------------

def active_plan(stores, ticker: str) -> dict | None:
    row = stores.ws.query_one(
        "SELECT * FROM thesis_health_plans WHERE ticker = ? AND active = 1 "
        "ORDER BY created_at DESC LIMIT 1",
        (ticker.upper(),),
    )
    return dict(row) if row else None


def active_plans(stores) -> list[dict]:
    rows = stores.ws.query(
        "SELECT * FROM thesis_health_plans WHERE active = 1 ORDER BY ticker"
    )
    return [dict(r) for r in rows]


def plan_items(stores, plan_id: str) -> list[dict]:
    rows = stores.ws.query(
        "SELECT * FROM thesis_watch_items WHERE plan_id = ? ORDER BY rowid", (plan_id,)
    )
    return [dict(r) for r in rows]


def plan_ready(stores, plan_id: str) -> bool:
    """Thesis-health ready: ≥1 quantitative watch item with a non-data-gap
    baseline grounding (ADR-0014)."""
    return any(
        i["tracking_mode"] == "quantitative" and i["last_checked_at"]
        and i["status"] != "data_gap"
        for i in plan_items(stores, plan_id)
    )


def summary_for(stores, ticker: str) -> str | None:
    """Thesis Health Summary Label for a ticker, or None when no active plan."""
    plan = active_plan(stores, ticker)
    if not plan:
        return None
    statuses = [i["status"] for i in plan_items(stores, plan["id"])
                if i["tracking_mode"] == "quantitative"]
    return th.summary_label(statuses) if statuses else "Not Checked"


# --- plan creation + baseline checks ----------------------------------------------

def create_plan_for_memo(stores, memo_artifact_id: str) -> str | None:
    """Persist a memo's monitoring plan as the new Active Thesis Health Source.

    Freezes any prior active plan for the ticker (older watch items become
    historical, never carried forward — ADR-0014), stores every item including
    qualitative/unsupported ones (retained but non-status-driving), then runs
    memo-time Thesis Health Baseline Checks for quantitative items.
    """
    memo = stores.artifacts.get(memo_artifact_id)
    if not memo:
        return None
    body = (memo.get("payload") or {}).get("body") or {}
    raw_items = body.get("monitoring_plan_items") or []
    if not raw_items:
        return None
    ticker = (memo.get("ticker") or "").upper()
    entity_id = memo.get("entity_id") or (stores.identity.resolve_ticker(ticker) or {}).get("id")
    specs = th.validate_plan(raw_items)
    plan_id = new_id("thp")
    ts = now_iso()
    with stores.ws.transaction() as conn:
        conn.execute(
            "UPDATE thesis_health_plans SET active = 0 WHERE ticker = ? AND active = 1",
            (ticker,),
        )
        conn.execute(
            "INSERT INTO thesis_health_plans (id, memo_artifact_id, entity_id, ticker, active, "
            "raw_plan, created_at) VALUES (?,?,?,?,1,?,?)",
            (plan_id, memo_artifact_id, entity_id, ticker, dumps(raw_items), ts),
        )
        for spec in specs:
            conn.execute(
                "INSERT INTO thesis_watch_items (id, plan_id, item_type, title, tracking_mode, "
                "metric, comparator, threshold, cadence, lookback, confirmation_periods, "
                "immediate_kill, status, why_matters) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_id("thw"), plan_id, spec.item_type, spec.title, spec.tracking_mode,
                 spec.metric, spec.comparator, spec.threshold, spec.cadence, spec.lookback,
                 spec.confirmation_periods, 1 if spec.immediate_kill else 0, "unknown",
                 spec.why_matters),
            )
    # Memo-time baseline checks ground fresh tracking immediately (ADR-0014).
    # Baseline observation = latest evidence at the item's cadence period type.
    for item in plan_items(stores, plan_id):
        if item["tracking_mode"] != "quantitative":
            continue
        observed, detail = _resolve_observed(stores, entity_id, item["metric"],
                                             item["cadence"], "latest")
        outcome = th.evaluate_item(
            item["threshold"], item["comparator"], observed,
            prior_consecutive_breaches=0,
            confirmation_periods=item["confirmation_periods"], is_baseline=True,
        )
        _record_check(stores, item, None, "baseline", observed, detail, outcome)
    return plan_id


def _record_check(stores, item: dict, refresh_id: str | None, kind: str,
                  observed: float | None, detail: dict, outcome: th.EvaluationOutcome) -> str:
    """Append one Thesis Watch Item Check and update the item's current state.

    A data gap preserves the prior status-driving status and increments the
    consecutive-gap counter instead of overwriting state (ADR-0014).
    """
    is_gap = outcome.status == "data_gap"
    if is_gap:
        prior = item["status"]
        new_status = prior if prior in ("intact", "watch", "broken") else "data_gap"
        gap_count = item["data_gap_count"] + 1
        breaches = item["consecutive_breaches"]
        current_value = item["current_value"]
    else:
        new_status = outcome.status
        gap_count = 0
        breaches = outcome.consecutive_breaches
        current_value = outcome.observed
    cid = new_id("thc")
    ts = now_iso()
    with stores.ws.transaction() as conn:
        conn.execute(
            "INSERT INTO thesis_health_checks (id, item_id, refresh_id, kind, observed, status, "
            "data_gap, checked_at) VALUES (?,?,?,?,?,?,?,?)",
            (cid, item["id"], refresh_id, kind,
             dumps({"value": observed, "note": outcome.note, **detail}),
             new_status, 1 if is_gap else 0, ts),
        )
        conn.execute(
            "UPDATE thesis_watch_items SET status = ?, current_value = ?, "
            "consecutive_breaches = ?, data_gap_count = ?, last_checked_at = ? WHERE id = ?",
            (new_status, current_value, breaches, gap_count, ts, item["id"]),
        )
    item.update(status=new_status, current_value=current_value,
                consecutive_breaches=breaches, data_gap_count=gap_count,
                last_checked_at=ts)
    return cid


def repair_inverted_comparators(stores) -> list[dict]:
    """One-time data repair for plans created before breach-framing
    normalization landed (ADR-0014). Such plans can store a kill-criterion/risk
    comparator in the BREACH direction, so a perfectly healthy current value
    reads as breached (the KO false-positive). Detect those deterministically
    (the same rule validate_plan applies to new memos), flip the stored
    comparator to the healthy band, and re-baseline the item so its persisted
    status reflects reality. Idempotent: a corrected comparator is no longer
    detected as inverted, so re-running is a no-op."""
    repaired: list[dict] = []
    for plan in active_plans(stores):
        for item in plan_items(stores, plan["id"]):
            if item["tracking_mode"] != "quantitative" or item["threshold"] is None:
                continue
            fixed = th.healthy_comparator_fix(item["item_type"], item["title"],
                                              item["comparator"])
            if fixed is None:
                continue
            old = item["comparator"]
            with stores.ws.transaction() as conn:
                conn.execute(
                    "UPDATE thesis_watch_items SET comparator = ?, consecutive_breaches = 0 "
                    "WHERE id = ?", (fixed, item["id"]),
                )
            item["comparator"] = fixed
            item["consecutive_breaches"] = 0
            # Re-baseline against the latest evidence so the corrected band is
            # reflected immediately (baseline semantics: never broken unless an
            # explicit immediate kill).
            observed, detail = _resolve_observed(stores, plan["entity_id"], item["metric"],
                                                 item["cadence"], "latest")
            outcome = th.evaluate_item(
                item["threshold"], fixed, observed, prior_consecutive_breaches=0,
                confirmation_periods=item["confirmation_periods"], is_baseline=True,
            )
            _record_check(stores, item, None, "baseline", observed, detail, outcome)
            repaired.append({"ticker": plan["ticker"], "item_id": item["id"],
                             "title": item["title"], "from": old, "to": fixed,
                             "status": item["status"]})
    return repaired


# --- observation resolution per lookback basis -------------------------------------

def _resolve_observed(stores, entity_id: str | None, metric: str | None,
                      cadence: str, lookback: str) -> tuple[float | None, dict]:
    """Resolve the compared evidence value for one watch item. Returns
    (value | None, detail) — None means data gap."""
    if not entity_id or not metric:
        return None, {"basis": lookback, "gap": "no entity or metric"}
    period_type = PERIOD_TYPE_FOR_CADENCE.get(cadence, "quarterly")

    if lookback == "latest":
        obs = stores.financial.observations(entity_id, metric=metric,
                                            period_type=period_type, limit=1)
        if obs and obs[0]["value"] is not None:
            return obs[0]["value"], {"basis": "latest", "period_end": obs[0]["period_end"]}
        v = stores.financial.latest_value(entity_id, metric)
        if v is not None:
            return v, {"basis": "latest_financials"}
        return None, {"basis": "latest", "gap": f"no observation for {metric}"}

    if lookback == "yoy":
        rows = stores.financial.observations(entity_id, metric=metric,
                                             period_type="quarterly", limit=12)
        if not rows or rows[0]["value"] is None:
            return None, {"basis": "yoy", "gap": "no quarterly history"}
        cur = rows[0]
        cur_dt = _parse_period(cur["period_end"])
        prior = None
        for r in rows[1:]:
            delta = abs((cur_dt - _parse_period(r["period_end"])).days - 365)
            if delta <= YOY_TOLERANCE_DAYS:
                prior = r
                break
        if prior is None or prior["value"] is None:
            return None, {"basis": "yoy", "period_end": cur["period_end"],
                          "gap": "prior-year quarter unavailable"}
        return cur["value"], {"basis": "yoy", "period_end": cur["period_end"],
                              "prior_period_end": prior["period_end"],
                              "prior_value": prior["value"]}

    if lookback == "ttm":
        ttm = stores.financial.observations(entity_id, metric=metric,
                                            period_type="ttm", limit=1)
        if ttm and ttm[0]["value"] is not None:
            return ttm[0]["value"], {"basis": "ttm", "period_end": ttm[0]["period_end"]}
        rows = stores.financial.observations(entity_id, metric=metric,
                                             period_type="quarterly", limit=4)
        vals = [r["value"] for r in rows if r["value"] is not None]
        if len(vals) < 4:
            return None, {"basis": "ttm", "gap": "fewer than 4 quarterly observations"}
        value = sum(vals) if metric in FLOW_METRICS else sum(vals) / 4
        return value, {"basis": "ttm", "derived_from": [r["period_end"] for r in rows],
                       "method": "sum" if metric in FLOW_METRICS else "mean"}

    if lookback == "annual":
        rows = stores.financial.observations(entity_id, metric=metric,
                                             period_type="annual", limit=1)
        if rows and rows[0]["value"] is not None:
            return rows[0]["value"], {"basis": "annual", "period_end": rows[0]["period_end"]}
        return None, {"basis": "annual", "gap": "no annual observation"}

    if lookback == "multi_period_avg":
        rows = stores.financial.observations(entity_id, metric=metric,
                                             period_type="quarterly", limit=4)
        vals = [r["value"] for r in rows if r["value"] is not None]
        if len(vals) >= 4:
            return sum(vals) / len(vals), {"basis": "multi_period_avg",
                                           "derived_from": [r["period_end"] for r in rows]}
        rows = stores.financial.observations(entity_id, metric=metric,
                                             period_type="annual", limit=3)
        vals = [r["value"] for r in rows if r["value"] is not None]
        if len(vals) >= 3:
            return sum(vals) / len(vals), {"basis": "multi_period_avg",
                                           "derived_from": [r["period_end"] for r in rows]}
        return None, {"basis": "multi_period_avg", "gap": "insufficient period history"}

    return None, {"basis": lookback, "gap": f"unsupported lookback {lookback!r}"}


def _parse_period(period_end: str) -> datetime:
    return datetime.fromisoformat(str(period_end)[:10]).replace(tzinfo=timezone.utc)


# --- refresh ------------------------------------------------------------------------

def refresh_all(stores, trigger: str = "manual") -> list[dict]:
    """Thesis Health Refresh for every DUE active plan, held tickers first.

    Each plan gets a Thesis Health Filing Metadata Check; full quantitative
    recalculation only runs when new evidence appeared since the last full
    refresh, otherwise the refresh is recorded metadata-only.
    """
    held = {h["ticker"] for h in stores.portfolio.holdings()}
    out = []
    for ticker in due_tickers(stores):  # held-first ordering preserved
        plan = active_plan(stores, ticker)
        if plan:
            out.append(_refresh_plan(stores, plan, trigger, ticker in held))
    return out


def refresh_for(stores, tickers: list[str], trigger: str = "filing") -> list[dict]:
    """Targeted Thesis Health Refresh for exactly these tickers' active plans —
    the daily data-sync tick entry point for filers (ADR-0059). Tickers without
    an active plan are skipped; input order is preserved."""
    held = {h["ticker"] for h in stores.portfolio.holdings()}
    out = []
    for ticker in (t.upper() for t in tickers):
        plan = active_plan(stores, ticker)
        if plan:
            out.append(_refresh_plan(stores, plan, trigger, ticker in held))
    return out


def _refresh_plan(stores, plan: dict, trigger: str, held: bool) -> dict:
    ticker = plan["ticker"]
    since = _last_full_refresh_at(stores, ticker) or plan["created_at"]
    try:
        has_new, filing_check = _has_new_filing(stores, ticker, since)
    except Exception as exc:  # offline-safe: failure degrades to metadata-only
        has_new, filing_check = False, {"method": "filings_index", "error": str(exc)}
    metadata_only = not has_new
    refresh_id = new_id("thr")
    with stores.ws.transaction() as conn:
        conn.execute(
            "INSERT INTO thesis_health_refreshes (id, entity_id, ticker, trigger, metadata_only, "
            "filing_check, ran_at) VALUES (?,?,?,?,?,?,?)",
            (refresh_id, plan["entity_id"], ticker, trigger,
             1 if metadata_only else 0, dumps(filing_check), now_iso()),
        )
    if not metadata_only:
        _recalculate_plan(stores, plan, refresh_id, held)
        # A baseline that data-gapped at memo time has now grounded — clear the
        # "thesis-health baseline missing" attention item raised for it.
        if plan_ready(stores, plan["id"]):
            stores.dashboard.resolve_source("thesis_health_gap", ticker)
    return {"ticker": ticker, "metadata_only": metadata_only,
            "summary_label": summary_for(stores, ticker) or "Not Checked"}


def _has_new_filing(stores, ticker: str, since: str) -> tuple[bool, dict]:
    """Thesis Health Filing Metadata Check: the bulk filings index is the
    primary signal (ADR-0059) — a relevant 10-K/10-Q row filed after the last
    full refresh warrants a full recalculation. Pre-bulk workspaces (no filing
    rows for the ticker and bootstrap not done) fall back to the old
    stored-observation heuristic so retained evidence still drives refreshes."""
    filings = stores.bulk.filings_for(ticker, forms=RELEVANT_FILING_FORMS, since=since)
    if filings:
        return True, {"method": "filings_index", "since": since,
                      "new_filings": len(filings),
                      "latest_filed_at": filings[0]["filed_at"],
                      "forms": sorted({f["form"] for f in filings})}
    if (stores.bulk.filings_for(ticker, limit=1)
            or stores.bulk.get_state("bootstrap_done") == "1"):
        return False, {"method": "filings_index", "since": since, "new_filings": 0}
    # Pre-bulk fallback (offline-honest rule): a new financial observation
    # captured after the last full refresh indicates new reported fundamentals.
    ent = stores.identity.resolve_ticker(ticker)
    if not ent:
        return False, {"method": "stored_observations", "since": since,
                       "new_observations": 0, "note": "unknown entity"}
    row = stores.ws.query_one(
        "SELECT COUNT(*) AS n, MAX(period_end) AS latest_period FROM financial_observations "
        "WHERE entity_id = ? AND captured_at > ? AND superseded_by IS NULL",
        (ent["id"], since),
    )
    n = row["n"] if row else 0
    return bool(n), {"method": "stored_observations", "since": since,
                     "new_observations": n,
                     "latest_period": row["latest_period"] if row else None}


def _recalculate_plan(stores, plan: dict, refresh_id: str, held: bool) -> None:
    items = plan_items(stores, plan["id"])
    newly_pressured = 0
    confirmed_break = False
    statuses: list[str] = []
    for item in items:
        if item["tracking_mode"] != "quantitative":
            continue
        prior_status = item["status"]
        observed, detail = _resolve_observed(stores, plan["entity_id"], item["metric"],
                                             item["cadence"], item["lookback"])
        outcome = th.evaluate_item(
            item["threshold"], item["comparator"], observed,
            prior_consecutive_breaches=item["consecutive_breaches"],
            confirmation_periods=item["confirmation_periods"],
        )
        _record_check(stores, item, refresh_id, "refresh", observed, detail, outcome)
        if item["data_gap_count"] >= 2:
            # Repeated gaps degrade monitoring quality: low-priority attention.
            stores.dashboard.upsert_item(
                "attention", "needs_attention", "data_gap", item["id"],
                str(item["data_gap_count"]), ticker=plan["ticker"],
                title=f"Repeated thesis-health data gaps — {plan['ticker']}",
                body=(f"Watch item '{item['title']}' has {item['data_gap_count']} consecutive "
                      f"data gaps; its prior status is preserved while evidence is missing."),
                severity="low",
                evidence_refs=[{"kind": "thesis_health_plan", "id": plan["id"]}],
            )
        if item["status"] in ("watch", "broken") and prior_status not in ("watch", "broken"):
            newly_pressured += 1
        if item["status"] == "broken" and item["item_type"] in ("kill_criterion", "return_driver"):
            confirmed_break = True
        statuses.append(item["status"])

    # Material Thesis Break: confirmed kill/return-driver break, or broad
    # same-refresh deterioration. Mirrors to Dashboard; routine state stays here.
    label = th.summary_label(statuses)
    if confirmed_break or newly_pressured >= 2:
        broken = [i for i in items
                  if i["tracking_mode"] == "quantitative" and i["status"] == "broken"]
        detail = "; ".join(
            f"{i['item_type'].replace('_', ' ')} '{i['title']}' confirmed after "
            f"{i['consecutive_breaches']} period(s)" for i in broken
        ) or f"{newly_pressured} watch items deteriorated in the same refresh"
        stores.dashboard.upsert_item(
            "attention", "needs_attention", "thesis_break", plan["id"], refresh_id,
            ticker=plan["ticker"],
            title=f"Material thesis break — {plan['ticker']} ({'held' if held else 'not held'})",
            body=f"Memo-backed thesis health is {label}. {detail}.",
            severity="high",
            rank_source=f"Thesis health: {label} — {detail}",
            evidence_refs=[{"kind": "thesis_health_plan", "id": plan["id"]},
                           {"kind": "memo", "id": plan["memo_artifact_id"]},
                           {"kind": "thesis_health_refresh", "id": refresh_id}],
        )
    elif label != "Broken":
        stores.dashboard.resolve_source("thesis_break", plan["id"])


def _last_refresh_at(stores, ticker: str, full_only: bool = False) -> str | None:
    sql = "SELECT ran_at FROM thesis_health_refreshes WHERE ticker = ?"
    if full_only:
        sql += " AND metadata_only = 0"
    row = stores.ws.query_one(sql + " ORDER BY ran_at DESC LIMIT 1", (ticker.upper(),))
    return row["ran_at"] if row else None


def _last_full_refresh_at(stores, ticker: str) -> str | None:
    return _last_refresh_at(stores, ticker, full_only=True)


def due_tickers(stores) -> list[str]:
    """Active-plan tickers due a refresh: a relevant filing since the last
    full refresh (or still unprocessed) makes a ticker due immediately
    (ADR-0059 filings index); never-refreshed is always due; otherwise the
    staleness fallback is 7d held / 30d non-held."""
    held = {h["ticker"] for h in stores.portfolio.holdings()}
    now = datetime.now(timezone.utc)
    due: list[str] = []
    for plan in active_plans(stores):
        ticker = plan["ticker"]
        last = _last_refresh_at(stores, ticker)
        limit = HELD_REFRESH_DAYS if ticker in held else NON_HELD_REFRESH_DAYS
        if (last is None
                or _filing_due(stores, ticker,
                               _last_full_refresh_at(stores, ticker) or plan["created_at"])
                or (now - _parse_ts(last)).days >= limit):
            due.append(ticker)
    due.sort(key=lambda t: (t not in held, t))
    return due


def _filing_due(stores, ticker: str, since: str) -> bool:
    """A relevant filing newer than the last full refresh, or one the daily
    tick has not yet processed into facts, keeps a ticker due."""
    if stores.bulk.filings_for(ticker, forms=RELEVANT_FILING_FORMS, since=since, limit=1):
        return True
    return any(not f["processed"]
               for f in stores.bulk.filings_for(ticker, forms=RELEVANT_FILING_FORMS, limit=20))


# --- company-page view ---------------------------------------------------------------

def thesis_health_view(stores, ticker: str) -> dict:
    """Company Page Thesis Health Section payload (api-contract)."""
    ticker = ticker.upper()
    plan = active_plan(stores, ticker)
    if plan is None:
        memo = stores.artifacts.latest_for_ticker(ticker, "investment_memo")
        return {
            "summary_label": None, "active_source": None, "items": [], "history": [],
            "filings_last_checked": None, "recalculated_at": None,
            "empty_reason": ("No thesis health checks yet." if memo else
                             "Thesis health begins after a Completed Memo establishes "
                             "trackable assumptions."),
        }
    items = plan_items(stores, plan["id"])
    driving = [i for i in items if i["tracking_mode"] == "quantitative"]
    rows = [
        {
            "id": i["id"], "title": i["title"], "item_type": i["item_type"],
            "status": i["status"], "metric": i["metric"], "comparator": i["comparator"],
            "threshold": i["threshold"], "current_value": i["current_value"],
            "lookback": i["lookback"], "cadence": i["cadence"],
            "last_checked_at": i["last_checked_at"],
            "data_gap": i["data_gap_count"] > 0, "why_matters": i["why_matters"],
            "tracking_mode": i["tracking_mode"],
        }
        for i in items if i["tracking_mode"] != "unsupported"  # unsupported items hidden
    ]
    refreshes = stores.ws.query(
        "SELECT * FROM thesis_health_refreshes WHERE ticker = ? ORDER BY ran_at DESC LIMIT 20",
        (ticker,),
    )
    history = [{"refresh_id": r["id"], "ran_at": r["ran_at"],
                "metadata_only": bool(r["metadata_only"]), "trigger": r["trigger"]}
               for r in refreshes]
    memo = stores.artifacts.get(plan["memo_artifact_id"])
    out = {
        "summary_label": (th.summary_label([i["status"] for i in driving])
                          if driving else "Not Checked"),
        "active_source": {"memo_artifact_id": plan["memo_artifact_id"],
                          "memo_date": memo["created_at"] if memo else plan["created_at"]},
        "items": th.sort_items_for_display(rows),
        "history": history,
        "filings_last_checked": history[0]["ran_at"] if history else plan["created_at"],
        "recalculated_at": next((h["ran_at"] for h in history if not h["metadata_only"]),
                                plan["created_at"]),
    }
    ungrounded = [i for i in driving
                  if i["status"] in ("data_gap", "unknown") or not i["last_checked_at"]]
    if not driving:
        out["empty_reason"] = (
            "This memo's monitoring plan has only qualitative watch items; quantitative "
            "thesis-health checks appear once it tracks a supported metric with retained "
            "history.")
    elif len(ungrounded) == len(driving):
        gap_metrics = sorted({i["metric"] for i in ungrounded if i["metric"]})
        which = ", ".join(gap_metrics) if gap_metrics else "the tracked metrics"
        out["empty_reason"] = (
            f"Tracking {len(driving)} watch item(s), but baseline evidence is missing for "
            f"{which}. Thesis health populates once the next filing or data refresh provides "
            f"this history.")
    return out
