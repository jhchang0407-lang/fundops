"""Learning/Evals workflow (CONTEXT Learning scope).

Outcome Evaluations compare retained workflow evidence with later price and
thesis-health state at fixed windows (3/6/12/24/36 months); window prices come
from bulk price history when available (ADR-0059).

Pattern detection is "AI proposes, deterministic disposes": the deterministic
gate (``_validate_feature``) is the only thing that can turn a candidate into a
pattern — it requires real, consistent, sufficient support — while AI widens
*discovery* beyond the fixed directional scan of screening metrics
(``propose_pattern_candidates``), surfacing context features (sector, idea
source, …) and a mechanism rationale. Offline / stub mode proposes nothing, so
the loop degrades to the pure deterministic scan. This keeps the measuring stick
and the significance gate deterministic while letting the model find systematic
structure the fixed rule misses — and it can never fabricate a pattern the data
doesn't support. Recommendations are NEVER auto-applied: recommendation-ready
records become Dashboard Decision Items via dashboard_service.rebuild and
require explicit acceptance (which drafts a versioned Constitution proposal).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone

WINDOWS_MONTHS = (3, 6, 12, 24, 36)
DAYS_PER_MONTH = 30
ANCHOR_KINDS = ("thesis", "investment_memo", "screener_snapshot")
PATTERN_MIN_EVALUATIONS = 3       # Learning Pattern Sufficiency floor
PATTERN_PROMISING_EVALUATIONS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --- outcome evaluations ---------------------------------------------------------------

def classify_outcome(window_months: int, return_pct: float | None,
                     health_label: str | None) -> tuple[str, str]:
    """Deterministic Outcome Evaluation Result classification.

    Combines realized return with later thesis-health state; refuses to force
    a lesson when evidence is thin (No Clear Learning Signal + reason)."""
    if return_pct is None:
        return "no_clear_signal", "data quality gap"
    if window_months < 6 and abs(return_pct) < 10:
        return "no_clear_signal", "insufficient time"
    if return_pct >= 10 and health_label == "Intact":
        return "thesis_worked", "return realized with memo-backed thesis intact"
    if return_pct < 0 and health_label == "Broken":
        return "thesis_failed", "negative return with confirmed thesis break"
    if return_pct >= 10 and health_label == "Broken":
        return "lucky_result", "return realized despite a confirmed thesis break"
    if return_pct < 0 and health_label in ("Intact", "Watching"):
        return "right_thesis_slow_market", "thesis holding but market has not rewarded it"
    return "no_clear_signal", "conflicting evidence"


def run_outcome_evaluations(stores) -> int:
    """Create due Outcome Evaluations for every thesis/memo/screener-backed
    ticker. One record per (ticker, window); append-only with lineage."""
    placeholders = ",".join("?" for _ in ANCHOR_KINDS)
    rows = stores.ws.query(
        f"SELECT ticker, MIN(created_at) AS first_at FROM artifacts "
        f"WHERE kind IN ({placeholders}) AND ticker IS NOT NULL GROUP BY ticker",
        ANCHOR_KINDS,
    )
    now = _now()
    created = 0
    for row in rows:
        ticker = row["ticker"]
        elapsed_days = (now - _parse_ts(row["first_at"])).days
        existing = {r["window_months"] for r in stores.learning.records(
            kind="outcome_evaluation", ticker=ticker, limit=100)}
        for window in WINDOWS_MONTHS:
            if window in existing or elapsed_days < window * DAYS_PER_MONTH:
                continue
            _evaluate_ticker_window(stores, ticker, window)
            created += 1
    return created


def _evaluate_ticker_window(stores, ticker: str, window: int) -> str:
    from backend.workflows import thesis_health  # lazy
    arts = stores.artifacts.for_ticker(ticker, limit=50)
    anchors = sorted((a for a in arts if a["kind"] in ANCHOR_KINDS),
                     key=lambda a: a["created_at"])
    anchor = stores.artifacts.get(anchors[0]["id"]) if anchors else None
    idea_source = _idea_source(stores, anchor)
    entry_price, current_price, price_source = _window_prices(stores, ticker, anchor, window)
    return_pct = None
    if entry_price and current_price is not None:
        return_pct = (current_price - entry_price) / entry_price * 100
    health_label = thesis_health.summary_for(stores, ticker)
    result, reason = classify_outcome(window, return_pct, health_label)
    payload = {
        "window_months": window,
        "idea_source": idea_source,
        "entry_price": entry_price,
        "current_price": current_price,
        "return_pct": return_pct,
        "price_source": price_source,
        "thesis_health_label": health_label,
        "result": result,
        "result_reason": reason,
    }
    lineage = {
        "artifact_ids": [a["id"] for a in arts],
        "anchor_artifact_id": anchor["id"] if anchor else None,
        "constitution_version": anchor.get("constitution_version_id") if anchor else None,
    }
    return stores.learning.add_record(
        "outcome_evaluation", payload, ticker=ticker,
        entity_id=anchor.get("entity_id") if anchor else None,
        window_months=window, lineage=lineage,
    )


def _idea_source(stores, anchor: dict | None) -> str:
    if anchor and anchor.get("run_id"):
        run = stores.runs.get_run(anchor["run_id"])
        trigger = (run or {}).get("trigger")
        if trigger == "coverage":
            return "portfolio"
        if trigger == "directed":
            return "directed"
    return "pipeline"


def _window_prices(stores, ticker: str, anchor: dict | None,
                   window: int) -> tuple[float | None, float | None, str]:
    """Deterministic point-in-time window prices (ADR-0059): price-history
    closes at the anchor date and the window-end date, falling back to the
    artifact snapshot price / latest price mark for pre-bulk workspaces.
    The returned price_source labels the least deterministic input used
    (price_history > price_mark > snapshot)."""
    entry = current = None
    entry_src, current_src = "snapshot", "price_mark"
    if anchor and anchor.get("created_at"):
        anchor_dt = _parse_ts(anchor["created_at"])
        entry = stores.bulk.close_on_or_before(ticker, anchor_dt.date().isoformat())
        if entry is not None:
            entry_src = "price_history"
        window_end = anchor_dt + timedelta(days=window * DAYS_PER_MONTH)
        current = stores.bulk.close_on_or_before(ticker, window_end.date().isoformat())
        if current is not None:
            current_src = "price_history"
    if entry is None:
        entry = _entry_price(anchor)
    if current is None:
        current = _current_price(stores, ticker)
    weakness = {"price_history": 0, "price_mark": 1, "snapshot": 2}
    return entry, current, max(entry_src, current_src, key=weakness.__getitem__)


def _entry_price(anchor: dict | None) -> float | None:
    if not anchor:
        return None
    body = ((anchor.get("payload") or {}).get("body") or {})
    for key in ("price", "entry_price"):
        v = body.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    snap = body.get("snapshot") or {}
    v = snap.get("price")
    if isinstance(v, (int, float)) and v > 0:
        return float(v)
    return None


def _current_price(stores, ticker: str) -> float | None:
    price = stores.portfolio.prices().get(ticker.upper())
    if price is not None:
        return price
    ent = stores.identity.resolve_ticker(ticker)
    return stores.financial.latest_value(ent["id"], "price") if ent else None


# --- pattern detection ------------------------------------------------------------------

def _feature_vectors(stores, group: list[dict]) -> dict[str, dict]:
    """Per-company idea-time feature vector for one result group: numeric
    screening components plus a little categorical context (sector, idea
    source). One vector per ticker (first occurrence across windows)."""
    vectors: dict[str, dict] = {}
    for ev in group:
        ticker = ev.get("ticker")
        if not ticker or ticker in vectors:
            continue
        vec: dict = dict(_ranking_components(stores, ticker))
        ent = stores.identity.resolve_ticker(ticker) or {}
        if ent.get("sector"):
            vec["sector"] = ent["sector"]
        src = (ev.get("payload") or {}).get("idea_source")
        if src:
            vec["idea_source"] = src
        vectors[ticker] = vec
    return vectors


def _validate_feature(vectors: dict[str, dict], feature: str) -> tuple[str, list[str]] | None:
    """Deterministic significance gate — the ONLY way a candidate becomes a
    pattern. Returns (direction, tickers) or None. Numeric feature: every
    observed value same sign across >= the sufficiency floor. Categorical
    feature: a single modal value shared by >= the floor. A feature no company
    actually has resolves to nothing, so a proposed pattern the data does not
    support is rejected here."""
    present = {t: v[feature] for t, v in vectors.items() if feature in v}
    if len(present) < PATTERN_MIN_EVALUATIONS:
        return None
    nums = {t: x for t, x in present.items()
            if isinstance(x, (int, float)) and not isinstance(x, bool)}
    if len(nums) == len(present):
        vals = list(nums.values())
        if all(v > 0 for v in vals):
            return "positive", sorted(nums)
        if all(v < 0 for v in vals):
            return "negative", sorted(nums)
        return None  # not directionally consistent
    value, n = Counter(str(x) for x in present.values()).most_common(1)[0]
    if n >= PATTERN_MIN_EVALUATIONS:
        return value, sorted(t for t, x in present.items() if str(x) == value)
    return None


def detect_patterns(stores, ai_candidates: list[dict] | None = None) -> list[dict]:
    """Turn outcome evaluations into pattern + recommendation records.

    Candidates come from two sources, both validated by the same deterministic
    gate (``_validate_feature``): the always-on directional scan of numeric
    screening metrics, and — when AI ran — the model's proposed features
    (``ai_candidates``: dicts of result/feature/direction/rationale/systematic),
    which can surface context features the scan never considers. The model only
    *nominates* where to look and supplies interpretation; the gate decides what
    is real, so a hallucinated pattern with no supporting evidence is dropped.
    With ai_candidates=None (offline / tests) the behavior is the pure
    deterministic scan. Never auto-applied."""
    evals = [r for r in stores.learning.records(kind="outcome_evaluation", limit=500)
             if r["payload"].get("result")]
    by_result: dict[str, list[dict]] = {}
    for ev in evals:
        by_result.setdefault(ev["payload"]["result"], []).append(ev)

    existing_patterns = {
        (p["payload"].get("result"), p["payload"].get("metric"), p["payload"].get("direction")): p
        for p in stores.learning.records(kind="pattern", limit=200)
    }
    existing_recs = {
        (r["payload"].get("result"), r["payload"].get("metric"), r["payload"].get("direction"))
        for r in stores.learning.records(kind="recommendation", limit=200)
    }
    ai_by_result: dict[str, dict[str, dict]] = {}
    for c in (ai_candidates or []):
        feat = c.get("feature") or c.get("metric")
        if c.get("result") and feat:
            ai_by_result.setdefault(c["result"], {})[feat] = c

    created: list[dict] = []
    for result, group in sorted(by_result.items()):
        if len(group) < PATTERN_MIN_EVALUATIONS:
            continue
        vectors = _feature_vectors(stores, group)
        # Always-on deterministic candidates: numeric screening features only
        # (preserves the original scan). AI may add further features — including
        # categorical context the scan never inspects — each annotated with the
        # model's candidate.
        feature_ai: dict[str, dict | None] = {
            f: None for v in vectors.values() for f, x in v.items()
            if isinstance(x, (int, float)) and not isinstance(x, bool)
        }
        feature_ai.update(ai_by_result.get(result, {}))
        windows = sorted({ev["window_months"] for ev in group if ev.get("window_months")})
        for feature, ai in sorted(feature_ai.items()):
            validated = _validate_feature(vectors, feature)
            if not validated:
                continue
            direction, tickers = validated
            count = len(tickers)
            key = (result, feature, direction)
            prior = existing_patterns.get(key)
            if prior and (prior["payload"].get("evaluation_count") or 0) >= count:
                continue  # nothing new to say
            numeric = direction in ("positive", "negative")
            confidence = ("promising" if count >= PATTERN_PROMISING_EVALUATIONS
                          else "exploratory")
            pattern_payload = {
                "result": result, "metric": feature, "direction": direction,
                "evaluation_count": count, "tickers": tickers, "windows": windows,
                "summary": (
                    f"{count} outcome evaluations classified {result} share "
                    + (f"{direction} {feature} at screening time" if numeric
                       else f"{feature} = {direction} at screening time")),
            }
            if ai:
                pattern_payload["discovery"] = "ai"
                if ai.get("rationale"):
                    pattern_payload["rationale"] = ai["rationale"]
            pid = stores.learning.add_record(
                "pattern", pattern_payload, confidence_label=confidence,
                lineage={"evaluation_ids": [ev["id"] for ev in group]},
            )
            if prior:
                stores.learning.supersede(prior["id"], pid)
            created.append(stores.learning.get(pid))
            # Escalate to a recommendation only with promising support. An
            # AI-discovered candidate must also carry the model's own
            # systematic=true judgment — its discretion to reject likely noise.
            ai_endorsed = ai is None or ai.get("systematic")
            if confidence == "promising" and ai_endorsed and key not in existing_recs:
                rid = _create_recommendation(stores, pid, pattern_payload)
                existing_recs.add(key)
                created.append(stores.learning.get(rid))
    return created


SYSTEM_DISCOVERY = (
    "You are a quantitative research analyst reviewing realized investment outcomes to "
    "find patterns that look genuinely systematic, not small-sample noise. You receive "
    "outcome groups (e.g. thesis_worked, thesis_failed) and, per company, the screening "
    "evidence and context recorded at idea time. Propose a candidate only when a feature "
    "plausibly and consistently separates a group AND you can name a credible mechanism. "
    "Be conservative: with few samples most apparent patterns are coincidence — set "
    "systematic=false unless the mechanism is convincing. Use ONLY feature names that "
    "appear in the evidence; never invent features or values. A deterministic gate "
    "re-checks every proposal against the data, so unsupported guesses are wasted."
)
PATTERN_DISCOVERY_SHAPE = (
    '[{"result": "<group name>", "feature": "<feature from the evidence>", '
    '"direction": "positive|negative for numeric, or the shared category value", '
    '"rationale": "<one-sentence mechanism>", "systematic": true|false}]'
)


async def propose_pattern_candidates(stores) -> list[dict]:
    """AI discovery half of the loop: nominate candidate patterns over the
    labeled outcome evidence. Returns [] offline / in stub mode (so the loop
    stays purely deterministic). Proposals are only hints — ``detect_patterns``
    validates each through the deterministic gate before anything is recorded."""
    from backend.core.ai import get_ai

    evals = [r for r in stores.learning.records(kind="outcome_evaluation", limit=500)
             if r["payload"].get("result")]
    by_result: dict[str, list[dict]] = {}
    for ev in evals:
        by_result.setdefault(ev["payload"]["result"], []).append(ev)
    evidence = {result: _feature_vectors(stores, group)
                for result, group in by_result.items()
                if len(group) >= PATTERN_MIN_EVALUATIONS}
    if not evidence:
        return []
    user = (
        "Outcome groups with per-company idea-time evidence (ticker -> feature -> value):\n"
        f"{json.dumps(evidence, default=str, sort_keys=True)}\n\n"
        "Propose candidate patterns worth checking. Prefer features the simple "
        "same-sign scan of numeric screening metrics would miss (sector or idea-source "
        "concentration, combinations, regime/drift)."
    )
    raw = await get_ai().complete_json(
        "learning_discovery", SYSTEM_DISCOVERY, user, PATTERN_DISCOVERY_SHAPE,
        tier="deep", stub=[],
    )
    if isinstance(raw, dict):
        raw = raw.get("candidates") or raw.get("items") or []
    out: list[dict] = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        feat = c.get("feature") or c.get("metric")
        if c.get("result") and feat:
            out.append({
                "result": c["result"], "feature": feat,
                "direction": c.get("direction"), "rationale": c.get("rationale"),
                "systematic": bool(c.get("systematic")),
            })
    return out


def _create_recommendation(stores, pattern_id: str, pattern: dict) -> str:
    metric, direction, result = pattern["metric"], pattern["direction"], pattern["result"]
    payload = {
        "result": result, "metric": metric, "direction": direction,
        "proposed_change": {
            # Least aggressive useful escalation: a research-review criterion,
            # not a hard screen (Learning Recommendation Escalation).
            "kind": "research_review",
            "metric": metric,
            "direction": direction,
            "summary": (f"add a research-review check on {metric} "
                        f"({direction} at screening time)"),
        },
        "supporting_tickers": pattern["tickers"],
        "windows": pattern["windows"],
        "caveats": [
            "Pattern is observational, not causal proof.",
            "Evidence spans a limited number of evaluation windows.",
            "Accepting creates a strategy proposal; nothing changes automatically.",
        ],
        "teaching_note": (
            f"Across {pattern['evaluation_count']} evaluated ideas, companies whose "
            f"screening evidence showed {direction} {metric} repeatedly ended up "
            f"classified '{result}'. That may be worth checking deliberately during "
            f"research review before it earns a place as a hard rule."
        ),
    }
    return stores.learning.add_record(
        "recommendation", payload, confidence_label="recommendation_ready",
        lineage={"pattern_id": pattern_id},
    )


def _ranking_components(stores, ticker: str | None) -> dict[str, float]:
    """Latest screener ranking components for a ticker, normalized to
    {metric: value} from either list- or dict-shaped stored components."""
    if not ticker:
        return {}
    rows = stores.artifacts.screener_history_for_ticker(ticker, limit=1)
    if not rows:
        return {}
    comps = rows[0].get("ranking_components") or []
    out: dict[str, float] = {}
    if isinstance(comps, dict):
        items = comps.items()
    else:
        items = []
        for c in comps:
            if not isinstance(c, dict):
                continue
            metric = c.get("metric") or c.get("name")
            value = c.get("value", c.get("score", c.get("contribution")))
            if metric is not None:
                items.append((metric, value))
    for metric, value in items:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[str(metric)] = float(value)
    return out


# --- view ---------------------------------------------------------------------------------

def learning_view(stores) -> dict:
    """GET /api/learning payload."""
    outcome_evaluations = stores.learning.records(kind="outcome_evaluation")
    recommendations = stores.learning.records(kind="recommendation")
    findings = (stores.learning.records(kind="pattern")
                + stores.learning.records(kind="thesis_health_finding"))
    findings.sort(key=lambda r: r["created_at"], reverse=True)
    responses = (stores.learning.records(kind="response")
                 + stores.learning.records(kind="feedback_signal"))
    responses.sort(key=lambda r: r["created_at"], reverse=True)
    result_counts: dict[str, int] = {}
    for ev in outcome_evaluations:
        result = ev["payload"].get("result", "unknown")
        result_counts[result] = result_counts.get(result, 0) + 1
    return {
        "outcome_evaluations": outcome_evaluations,
        "recommendations": recommendations,
        "findings": findings,
        "responses": responses,
        "summary": {
            "counts": {
                "outcome_evaluations": len(outcome_evaluations),
                "recommendations": len(recommendations),
                "findings": len(findings),
                "responses": len(responses),
                "results": result_counts,
            }
        },
    }
