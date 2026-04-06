"""Agent execution routes."""

import logging
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

log = logging.getLogger("fundops.routes.agents")

TICKER_PATTERN = re.compile(r'^[A-Z]{1,6}$')

def validate_ticker(ticker: str) -> str:
    """Validate and normalize ticker symbol."""
    t = ticker.strip().upper()
    if not TICKER_PATTERN.match(t):
        raise HTTPException(400, f"Invalid ticker: {ticker}. Must be 1-6 uppercase letters.")
    return t

from backend.api.deps import (
    get_db, get_job_queue, get_llm, get_web_search,
    get_fmp, get_yfinance, get_sec, get_config,
    get_library, get_v2db, get_outcome_checker,
)
from backend.agents.screener import ScreenerAgent
from backend.agents.thesis import ThesisAgent
from backend.agents.ic_review import ICReviewAgent
from backend.agents.library import LibraryAgent
from backend.agents.portfolio import PortfolioAgent
from backend.agents.allocator import AllocatorAgent

router = APIRouter()


def _load_constitution(config) -> dict | None:
    """Load active constitution from DB for strategy-aware agent runs."""
    try:
        from backend.core.db_v2 import ScreenerV2DB
        db_path = config.resolved.get("db_path", str(Path.home() / ".fundops" / "fundops.db"))
        v2db = ScreenerV2DB(db_path=db_path)
        constitution = v2db.get_active_constitution()
        v2db.close()
        return constitution
    except Exception:
        return None


def _lookup_screener_data(ticker: str, config) -> dict | None:
    """Look up screener-enriched data for a ticker from the latest screener run.

    Returns the candidate dict with SEC-computed metrics (PE, ROIC, growth, margins,
    ownerEarningsPerShare, etc.) so thesis can use them as seed data instead of
    re-fetching everything from FMP.
    """
    try:
        from backend.core.db_v2 import ScreenerV2DB
        db_path = config.resolved.get("db_path", str(Path.home() / ".fundops" / "fundops.db"))
        v2db = ScreenerV2DB(db_path=db_path)
        latest = v2db.get_latest_screener_results()
        v2db.close()
        if not latest:
            return None
        all_results = latest.get("all_results") or latest.get("top_results") or []
        ticker_upper = ticker.upper()
        for candidate in all_results:
            if not isinstance(candidate, dict):
                continue
            if (candidate.get("symbol") or candidate.get("ticker", "")).upper() == ticker_upper:
                return candidate
    except Exception:
        pass
    return None


# --- Display-format → execution-format filter conversion ---
# Constitution stores filters in display format (for the Configure modal).
# The screener agent expects execution-format keys with numeric values.

_DISPLAY_TO_EXEC_KEY = {
    "gross_margin_pct":           "min_gross_margin",
    "revenue_growth_ttm_yoy":     "min_revenue_growth_1y",
    "revenue_growth_yoy":         "min_revenue_growth_1y",
    "revenue_cagr_3yr":           "min_revenue_growth_3y",
    "operating_margin_latest_pct":"min_operating_margin",
    "net_margin":                 "min_net_margin",
    "roic":                       "min_roic",
    "roe":                        "min_roe",
    "fcf_yield":                  "min_fcf_yield_pct",
    "rs_percentile_3m":           "min_rs_percentile_3m",
    "rs_percentile_6m":           "min_rs_percentile_6m",
    "debt_equity":                "max_debt_equity",
    "pe_ratio":                   "max_pe",
    "ev_ebitda":                  "max_ev_ebitda",
    "price_to_book":              "max_pb",
    "revenue_not_declining":      "revenue_not_declining",
    "positive_fcf_required":      "positive_fcf_required",
    # Allow keys that are already in execution format to pass through
}

def _display_filters_to_exec(display_filters: dict) -> dict:
    """Convert constitution display-format filters to screener execution format.

    Display: {"gross_margin_pct": ">=50%", "revenue_not_declining": "true"}
    Execution: {"min_gross_margin": 50.0, "revenue_not_declining": True}
    """
    exec_filters = {}
    for k, v in display_filters.items():
        exec_key = _DISPLAY_TO_EXEC_KEY.get(k, k)  # fall back to same key if already exec format
        if isinstance(v, bool):
            exec_filters[exec_key] = v
        elif isinstance(v, (int, float)):
            exec_filters[exec_key] = v
        elif isinstance(v, str):
            lower = v.strip().lower()
            if lower in ("true", "yes", "✓"):
                exec_filters[exec_key] = True
            elif lower in ("false", "no"):
                exec_filters[exec_key] = False
            else:
                # Parse ">=50%", ">20%", "<=3", "50", etc.
                clean = lower.replace(">=", "").replace("<=", "").replace(">", "").replace("<", "").replace("%", "").replace("bps", "").strip()
                try:
                    exec_filters[exec_key] = float(clean)
                except ValueError:
                    pass  # Skip unparseable values
    return exec_filters


def _apply_universe(agent_config: dict, constitution: dict | None) -> dict:
    """Override screener config universe from active constitution."""
    cfg = dict(agent_config)
    if not constitution:
        return cfg
    if constitution.get("universe_type") == "custom" and constitution.get("universe_custom"):
        custom = constitution["universe_custom"]
        # Normalize to list
        if isinstance(custom, str):
            custom_list = [t.strip() for t in custom.split(",") if t.strip()]
        elif isinstance(custom, list):
            custom_list = [str(t).strip() for t in custom if t]
        else:
            custom_list = []
        # Filter out placeholder markers (e.g. "FETCH_AND_SET_CONSTITUENTS:IGV")
        real_tickers = [t for t in custom_list if ":" not in t and t.isalpha() and len(t) <= 6]
        if real_tickers:
            cfg["custom_tickers"] = real_tickers
        else:
            # Placeholder custom — fall back to preset, clear stale custom_tickers
            cfg.pop("custom_tickers", None)
            if constitution.get("universe_name"):
                cfg["universe"] = constitution["universe_name"]
    elif constitution.get("universe_name"):
        cfg["universe"] = constitution["universe_name"]
        cfg.pop("custom_tickers", None)  # Clear any stale custom_tickers from base config
    agent_profiles = constitution.get("agent_profiles") or {}
    screener_profile = agent_profiles.get("screener") or {}
    if screener_profile.get("weights"):
        cfg["scoring_weights"] = screener_profile["weights"]
    if screener_profile.get("filters"):
        # Convert display format → execution format so the screener can apply them
        cfg["constitution_filters"] = _display_filters_to_exec(screener_profile["filters"])
    return cfg


def _apply_ic_hurdles(agent_config: dict, constitution: dict | None) -> dict:
    """Override IC config hurdles from active constitution."""
    cfg = dict(agent_config)
    if not constitution:
        return cfg
    hurdles = constitution.get("ic_hurdles") or {}
    if hurdles.get("base_return_pct") is not None:
        cfg["hurdle_base_pct"] = hurdles["base_return_pct"]
    if hurdles.get("bear_return_pct") is not None:
        cfg["hurdle_bear_pct"] = hurdles["bear_return_pct"]
    if hurdles.get("haircut_pct") is not None:
        cfg["bear_haircut_pct"] = hurdles["haircut_pct"]
    return cfg


class TickerRequest(BaseModel):
    ticker: str


class MemoRequest(BaseModel):
    ticker: str
    mode: str = "research"  # research, investment, both


# --- Screener ---

@router.post("/screener/run")
async def run_screener():
    """Trigger screener run (async, returns job ID).
    Uses active constitution for universe and scoring weights.
    """
    config = get_config()
    constitution = _load_constitution(config)
    base_config = config.resolved.get("agents", {}).get("screener", {}).get("config", {})
    agent_config = _apply_universe(base_config, constitution)

    agent = ScreenerAgent(
        config=agent_config,
        fmp=get_fmp(),
        yfinance=get_yfinance(),
        sec=get_sec(),
        db=get_db(),
    )

    jobs = get_job_queue()
    job_id = await jobs.submit(
        "screener", agent.run, {"constitution": constitution},
        on_complete=_screener_feedback_callback(config),
    )
    universe_used = agent_config.get("universe", "us_largecap_200")
    return {"job_id": job_id, "status": "running", "universe": universe_used}


def _screener_feedback_callback(config):
    """Return a callback that runs Loop 1 pattern detection after screener completes.

    Non-blocking: if detection fails, the screener result is unaffected.
    Only detects and logs patterns here. propose_refinement() requires an LLM
    client and should be called separately (e.g., from a UI-triggered endpoint
    or a scheduled task) when LLM is available.
    """
    async def _on_screener_complete(job):
        try:
            from backend.learning.feedback_loop import detect_patterns, propose_refinement
            from backend.core.db_v2 import ScreenerV2DB

            db_path = config.resolved.get("db_path", str(Path.home() / ".fundops" / "fundops.db"))
            v2db = ScreenerV2DB(db_path=db_path)
            try:
                patterns = await detect_patterns(v2db)
                if patterns:
                    log.info(f"Detected {len(patterns)} feedback patterns after screener run")
                    for p in patterns:
                        log.info(f"  Pattern: {p['type']} — {p['tag']} ({p['count']} occurrences)")

                    # Auto-generate proposals for detected patterns
                    try:
                        llm = get_llm()
                        if llm and llm.api_key:
                            constitution = v2db.get_active_constitution() or {}
                            # Get current scoring code for context
                            current_code = ""
                            try:
                                latest_version = v2db.get_active_scoring_code()
                                current_code = latest_version.get("code", "") if latest_version else ""
                            except Exception:
                                pass
                            for pattern in patterns[:3]:  # Cap at 3 proposals per run
                                try:
                                    proposal = await propose_refinement(
                                        llm=llm,
                                        pattern=pattern,
                                        current_code=current_code,
                                        constitution=constitution,
                                    )
                                    if proposal:
                                        log.info(f"  Auto-proposal generated: {proposal.get('summary', 'N/A')}")
                                except Exception as pe:
                                    log.warning(f"  Proposal generation failed for pattern '{pattern.get('tag', '?')}': {pe}")
                    except Exception as llm_err:
                        log.debug(f"LLM not available for auto-proposals: {llm_err}")
                else:
                    log.debug("No feedback patterns detected after screener run")
            finally:
                v2db.close()
        except Exception as e:
            log.warning(f"Feedback pattern detection failed (non-blocking): {e}")

    return _on_screener_complete


@router.get("/screener/results")
async def get_screener_results():
    """Get latest screener results, formatted for the Screener page.

    Maps the basic screener output (all_scored / handoff_candidates) into the
    standard results shape so the frontend Screener page can display it.
    """
    import json as _json
    db = get_db()
    runs = db.get_latest_runs("screener", limit=1)
    if not runs:
        return {"results": [], "message": "No screener runs yet"}

    run = runs[0]
    try:
        fo = _json.loads(run["full_output"]) if isinstance(run.get("full_output"), str) else (run.get("full_output") or {})
    except Exception:
        fo = {}

    # all_scored has everything; handoff_candidates is the top subset
    raw = fo.get("all_scored") or fo.get("handoff_candidates") or []
    if not raw:
        return {"results": [], "run_id": run.get("run_at"), "message": "Run completed but no stocks scored"}

    results = []
    for r in raw:
        ticker = r.get("symbol") or r.get("ticker", "")
        if not ticker:
            continue
        return_sources = r.get("return_sources") or {}
        # Score: use the higher of dislocation / compounder, scaled to 0-100
        disl = r.get("dislocation_score", 0) or 0
        comp = r.get("compounder_score", 0) or 0
        raw_score = max(disl, comp)
        score = round(min(raw_score * 10, 100), 1)  # 0-10 → 0-100
        results.append({
            "ticker": ticker,
            "symbol": ticker,
            "companyName": r.get("companyName") or r.get("company_name", ""),
            "sector": r.get("sector", ""),
            "price": r.get("price"),
            "score": score,
            "quality": round((r.get("quality_score") or 0) * 10, 1),
            "cheapness": round((r.get("cheapness_score") or 0) * 10, 1),
            "growth": round((r.get("health_score") or 0) * 10, 1),
            "expected_return": r.get("expected_return"),
            "top_lens": r.get("top_lens"),
            "lens": r.get("top_lens"),
            # Financials (both naming conventions for compatibility)
            "grossProfitMargin": r.get("grossProfitMargin"),
            "returnOnInvestedCapital": r.get("returnOnInvestedCapital"),
            "revenueGrowth": r.get("revenueGrowth"),
            "fcfYield": r.get("fcfYield"),
            "debtEquity": r.get("debtEquity"),
            # Return decomposition
            "return_discount": return_sources.get("discount"),
            "return_growth": return_sources.get("growth"),
            "return_margin": return_sources.get("margin"),
            "return_dividend": return_sources.get("dividends", 0),
            # Relative strength percentiles
            "rs_3m": r.get("rs_3m"),
            "rs_6m": r.get("rs_6m"),
            "rs_3m_percentile": r.get("rs_3m_percentile"),
            "rs_6m_percentile": r.get("rs_6m_percentile"),
            # Additional financials with snake_case aliases
            "gross_margin": r.get("gross_margin") or r.get("grossProfitMargin"),
            "roic": r.get("roic") or r.get("returnOnInvestedCapital"),
            "revenue_growth": r.get("revenue_growth") or r.get("revenueGrowth"),
            "fcf_yield": r.get("fcf_yield") or r.get("fcfYield"),
            "debt_to_equity": r.get("debt_to_equity") or r.get("debtEquity"),
            "operatingMargin": r.get("operatingMargin") or r.get("operating_margin"),
            "reason": r.get("reason") or r.get("variant_view"),
        })

    return {
        "results": results,
        "run_id": run.get("run_at"),
        "universe_size": fo.get("universe_size"),
        "scored_count": fo.get("passed_hurdle") or len(results),
        "strategy_name": None,
        "status": "complete",
        "run_at": run.get("run_at"),
    }


# --- Thesis ---

@router.post("/thesis/{ticker}")
async def run_thesis(ticker: str):
    """Trigger thesis generation for a ticker. Passes constitution for strategy-aware analysis."""
    ticker = validate_ticker(ticker)
    config = get_config()
    constitution = _load_constitution(config)
    agent_config = config.resolved.get("agents", {}).get("val", {}).get("config", {})

    agent = ThesisAgent(
        config=agent_config,
        fmp=get_fmp(),
        sec=get_sec(),
        yfinance=get_yfinance(),
        llm=get_llm(),
        web_search=get_web_search(),
        db=get_db(),
        library=get_library(),
    )

    # Seed screener data so thesis has baseline financial metrics even if FMP is incomplete
    screener_seed = _lookup_screener_data(ticker, config)

    jobs = get_job_queue()
    job_id = await jobs.submit("thesis", agent.run, {"ticker": ticker, "constitution": constitution, "screener_data": screener_seed}, ticker=ticker)
    return {"job_id": job_id, "status": "running", "ticker": ticker}


@router.post("/thesis/batch")
async def run_thesis_batch(request: Request):
    """Run thesis generation for multiple tickers SEQUENTIALLY as a single job.

    Body: {"tickers": ["APP", "MSFT", ...]}
    Processes one at a time to avoid API rate limits.
    """
    body = await request.json()
    tickers = [validate_ticker(t) for t in (body.get("tickers") or [])]
    if not tickers:
        return {"error": "No tickers provided"}

    config = get_config()
    constitution = _load_constitution(config)
    agent_config = config.resolved.get("agents", {}).get("val", {}).get("config", {})

    async def batch_fn(ctx):
        progress = ctx.get("_update_progress", lambda msg: None)
        agent = ThesisAgent(
            config=agent_config,
            fmp=get_fmp(), sec=get_sec(), yfinance=get_yfinance(),
            llm=get_llm(), web_search=get_web_search(), db=get_db(),
            library=get_library(),
        )
        results = []
        for i, ticker in enumerate(tickers):
            progress(f"Thesis {i+1}/{len(tickers)}: {ticker}")
            try:
                screener_seed = _lookup_screener_data(ticker, config)
                result = await agent.run({"ticker": ticker, "constitution": constitution, "screener_data": screener_seed})
                results.append({"ticker": ticker, "status": "complete"})
            except Exception as e:
                results.append({"ticker": ticker, "status": "failed", "error": str(e)})
        progress(f"Done: {sum(1 for r in results if r['status'] == 'complete')}/{len(tickers)} complete")
        return type("Result", (), {"data": {"results": results, "completed": sum(1 for r in results if r['status'] == 'complete')}})()

    jobs = get_job_queue()
    job_id = await jobs.submit("thesis", batch_fn, {})
    return {"job_id": job_id, "status": "running", "tickers": tickers, "count": len(tickers)}


@router.post("/ic-review/batch")
async def run_ic_batch(request: Request):
    """Run IC review for multiple tickers SEQUENTIALLY as a single job.

    Body: {"tickers": ["APP", "MSFT", ...]}
    """
    body = await request.json()
    tickers = [validate_ticker(t) for t in (body.get("tickers") or [])]
    if not tickers:
        return {"error": "No tickers provided"}

    config = get_config()
    constitution = _load_constitution(config)
    base_cfg = config.resolved.get("agents", {}).get("ic_review", {}).get("config", {})

    async def batch_fn(ctx):
        progress = ctx.get("_update_progress", lambda msg: None)
        import json as _json
        db = get_db()
        ic_agent = ICReviewAgent(config=base_cfg, llm=get_llm(), db=db, library=get_library())
        results = []
        for i, ticker in enumerate(tickers):
            progress(f"IC Review {i+1}/{len(tickers)}: {ticker}")
            try:
                # Load thesis data for this ticker
                thesis_runs = db.get_latest_runs("thesis", ticker=ticker, limit=1)
                thesis_data = {}
                if thesis_runs:
                    raw = thesis_runs[0].get("full_output") or "{}"
                    thesis_data = _json.loads(raw) if isinstance(raw, str) else raw
                result = await ic_agent.run({**thesis_data, "ticker": ticker, "constitution": constitution})
                results.append({"ticker": ticker, "status": "complete", "verdict": result.data.get("verdict")})
            except Exception as e:
                results.append({"ticker": ticker, "status": "failed", "error": str(e)})
        passed = sum(1 for r in results if r.get("verdict") == "PASS")
        progress(f"Done: {passed} passed, {len(results) - passed} failed/no_pass")
        return type("Result", (), {"data": {"results": results, "passed": passed}})()

    jobs = get_job_queue()
    job_id = await jobs.submit("ic_review", batch_fn, {})
    return {"job_id": job_id, "status": "running", "tickers": tickers, "count": len(tickers)}


@router.get("/thesis")
async def list_theses():
    """List all tickers with thesis runs + screener handoff candidates pending thesis.

    Screener handoff candidates that don't yet have a thesis run appear as
    'screened' entries so the user can trigger thesis generation from the
    Research page.
    """
    import json as _json
    db = get_db()
    runs = db.get_latest_runs("thesis", limit=200)
    results = []
    seen = set()
    skip_tickers = {"PIPELINE", "BATCH"}
    # Group runs by ticker, prefer the one with full_output
    best_runs = {}
    for run in runs:
        ticker = run.get("ticker", "")
        if not ticker or ticker in skip_tickers:
            continue
        # If we already have a run with full_output for this ticker, skip
        if ticker in best_runs:
            existing = best_runs[ticker]
            if existing.get("full_output") and not run.get("full_output"):
                continue
        best_runs[ticker] = run

    for ticker, run in best_runs.items():
        if ticker in seen:
            continue
        seen.add(ticker)
        try:
            raw = _json.loads(run["full_output"]) if isinstance(run.get("full_output"), str) else (run.get("full_output") or {})
        except Exception:
            raw = {}
        # Skip ghost rows with no data (from failed writes)
        if not raw and not run.get("fair_value"):
            continue
        # Check if IC review exists for this ticker
        ic_runs = db.get_latest_runs("ic_review", ticker=ticker, limit=1)
        ic_verdict = None
        if ic_runs:
            ic_raw_str = ic_runs[0].get("full_output") or "{}"
            try:
                ic_raw = _json.loads(ic_raw_str) if isinstance(ic_raw_str, str) else ic_raw_str
                v = (ic_raw.get("verdict") or ic_runs[0].get("verdict") or "").upper()
                ic_verdict = "pass" if v == "PASS" else "no_pass" if v == "NO_PASS" else "pending"
            except Exception:
                ic_verdict = "pending"
        valuation = raw.get("valuation") or {}
        quality = raw.get("quality") or {}
        web = raw.get("web_research") or {}
        constitution_fit = raw.get("constitution_fit") or {}
        # Build constitution_criteria from signals_met + signals_missed
        signals_met = constitution_fit.get("signals_met") or []
        signals_missed = constitution_fit.get("signals_missed") or []
        constitution_criteria = (
            [{"label": s.get("label", s) if isinstance(s, dict) else s, "met": True, "actual": s.get("actual", "") if isinstance(s, dict) else ""} for s in signals_met] +
            [{"label": s.get("label", s) if isinstance(s, dict) else s, "met": False, "actual": s.get("actual", "") if isinstance(s, dict) else ""} for s in signals_missed]
        ) or None
        anti_signals_raw = constitution_fit.get("anti_signals_triggered") or []
        anti_signals = [{"label": a.get("label", a) if isinstance(a, dict) else a, "value": a.get("value", "") if isinstance(a, dict) else ""} for a in anti_signals_raw] or None
        results.append({
            "ticker": ticker,
            "company_name": raw.get("company_name") or run.get("ticker"),
            "fair_value": raw.get("fair_value") or run.get("fair_value"),
            "expected_return": raw.get("expected_return"),
            "discount": raw.get("discount_pct"),
            "ic_verdict": ic_verdict,
            "conviction": raw.get("conviction"),
            "conviction_max": 5,
            "why_it_exists": web.get("why_cheap"),
            # thesis_narrative: prefer explicit field, fall back to variant_view only if it
            # looks like a real thesis (not raw LLM chatter starting with "Thanks" etc.)
            "thesis_summary": raw.get("thesis_summary"),
            "thesis_narrative": raw.get("thesis_narrative") or (
                raw.get("variant_view")
                if raw.get("variant_view") and not str(raw.get("variant_view", "")).startswith(("Thanks", "I'll", "I will", "Sure", "Got it"))
                else None
            ),
            "web_research_note": web.get("summary") if isinstance(web, dict) else None,
            "valuation_method": valuation.get("method") if isinstance(valuation, dict) else None,
            "valuation_note": valuation.get("note") if isinstance(valuation, dict) else None,
            "current_pe": valuation.get("current_pe") if isinstance(valuation, dict) else None,
            "fair_pe": valuation.get("fair_pe") if isinstance(valuation, dict) else None,
            "eps": valuation.get("eps") if isinstance(valuation, dict) else None,
            "growth": valuation.get("growth_rate") if isinstance(valuation, dict) else None,
            "earnings_growth": valuation.get("earnings_growth") if isinstance(valuation, dict) else None,
            "quality": quality if quality else None,
            "return_sources": raw.get("return_sources"),
            "constitution_criteria": constitution_criteria,
            "anti_signals": anti_signals,
            "similar_research": raw.get("similar_research"),
            "return_validation": raw.get("return_validation"),
            "date": run.get("run_at"),
            "stage": "thesis_complete",
        })

    # Fallback: check judgment_events for thesis data not in agent_runs
    # (handles cases where agent_runs write failed but judgment event was recorded)
    try:
        from backend.core.db_v2 import ScreenerV2DB as _V2DB
        _v2 = _V2DB(db_path=db.db_path)
        thesis_events = _v2.conn.execute(
            "SELECT ticker, data, rationale, created_at FROM judgment_events "
            "WHERE event_type = 'thesis_generated' ORDER BY created_at DESC"
        ).fetchall()
        ic_events_map = {}
        for row in _v2.conn.execute(
            "SELECT ticker, data FROM judgment_events "
            "WHERE event_type IN ('ic_passed', 'ic_failed') ORDER BY created_at DESC"
        ).fetchall():
            if row[0] not in ic_events_map:
                ic_events_map[row[0]] = _json.loads(row[1]) if isinstance(row[1], str) else (row[1] or {})

        for ev in thesis_events:
            ticker = ev[0]
            if not ticker or ticker in seen or ticker in skip_tickers:
                continue
            seen.add(ticker)
            jev_data = _json.loads(ev[1]) if isinstance(ev[1], str) else (ev[1] or {})
            ic_jev = ic_events_map.get(ticker, {})
            ic_verdict = None
            if ic_jev:
                v = (ic_jev.get("verdict") or "").upper()
                ic_verdict = "pass" if v == "PASS" else "no_pass" if v == "NO_PASS" else "pending"

            # Try to get full thesis data from agent_runs (may have full_output even without fair_value)
            raw = {}
            try:
                ar_rows = db.get_latest_runs("thesis", ticker=ticker, limit=1)
                if ar_rows and ar_rows[0].get("full_output"):
                    raw = _json.loads(ar_rows[0]["full_output"]) if isinstance(ar_rows[0]["full_output"], str) else ar_rows[0]["full_output"]
            except Exception:
                pass

            valuation = raw.get("valuation") or {}
            quality = raw.get("quality") or {}
            web = raw.get("web_research") or {}

            results.append({
                "ticker": ticker,
                "company_name": raw.get("company_name") or "",
                "fair_value": raw.get("fair_value") or jev_data.get("fair_value"),
                "expected_return": raw.get("expected_return") or jev_data.get("expected_return"),
                "discount": raw.get("discount_pct") or jev_data.get("discount_pct"),
                "ic_verdict": ic_verdict,
                "conviction": raw.get("conviction") or jev_data.get("conviction"),
                "conviction_max": 5,
                "why_it_exists": web.get("why_cheap"),
                "thesis_summary": raw.get("thesis_summary"),
                "thesis_narrative": raw.get("thesis_narrative") or raw.get("variant_view"),
                "web_research_note": web.get("summary") if isinstance(web, dict) else None,
                "valuation_method": valuation.get("method") if isinstance(valuation, dict) else None,
                "valuation_note": valuation.get("note") if isinstance(valuation, dict) else None,
                "current_pe": valuation.get("current_pe") if isinstance(valuation, dict) else None,
                "fair_pe": valuation.get("fair_pe") if isinstance(valuation, dict) else None,
                "eps": valuation.get("eps") if isinstance(valuation, dict) else None,
                "growth": valuation.get("growth_rate") if isinstance(valuation, dict) else None,
                "earnings_growth": valuation.get("earnings_growth") if isinstance(valuation, dict) else None,
                "quality": quality if quality else None,
                "date": ev[3],
                "stage": "thesis_complete",
            })
        _v2.close()
    except Exception as e:
        log.debug(f"Judgment events fallback failed: {e}")

    # Append screener handoff candidates that don't yet have a thesis
    # Screener v2 stores results in screener_runs table (db_v2), not agent_runs
    latest_screener = None
    try:
        from backend.core.db_v2 import ScreenerV2DB
        v2db = ScreenerV2DB(db_path=db.db_path)
        latest_screener = v2db.get_latest_screener_results()
        v2db.close()
    except Exception:
        pass
    # Fallback: try default path (data/fundops.db) if primary had no results
    if not latest_screener:
        try:
            from backend.core.db_v2 import ScreenerV2DB
            v2db = ScreenerV2DB()
            latest_screener = v2db.get_latest_screener_results()
            v2db.close()
        except Exception:
            pass

    if latest_screener:
        handoff = latest_screener.get("top_results") or latest_screener.get("all_results") or []
        # Take top 20 by score
        if isinstance(handoff, list) and len(handoff) > 20:
            handoff = sorted(handoff, key=lambda x: x.get("score", 0), reverse=True)[:20]

        # Batch-load stored financial data for all screened tickers
        screened_tickers = [
            (c.get("symbol") or c.get("ticker", "")).upper()
            for c in handoff if isinstance(c, dict)
        ]
        financials_map = {}
        try:
            from backend.core.db_v2 import ScreenerV2DB
            from backend.core.financial_data import FinancialData
            v2db2 = ScreenerV2DB(db_path=db.db_path)
            financials_map = v2db2.get_ticker_financials_batch(screened_tickers)
            v2db2.close()
        except Exception:
            pass

        for candidate in handoff:
            if not isinstance(candidate, dict):
                continue
            ticker = (candidate.get("symbol") or candidate.get("ticker", "")).upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)

            # Build quality metrics from stored financial data
            quality = None
            stored = financials_map.get(ticker)
            if stored and stored.get("financial_data"):
                try:
                    fd = FinancialData.from_dict(stored["financial_data"])
                    flat = fd.to_flat_metrics()
                    quality = {
                        "gross_margin": round(flat.get("gross_margin", 0) * 100, 1),
                        "roic": round(flat.get("roic", 0) * 100, 1),
                        "roe": round(flat.get("roe", 0) * 100, 1),
                        "debt_equity": round(flat.get("debt_equity", 0), 2),
                        "fcf_yield": round(flat.get("fcf_yield", 0), 1),
                    }
                except Exception:
                    pass

            results.append({
                "ticker": ticker,
                "company_name": candidate.get("companyName") or candidate.get("company_name") or candidate.get("name", ""),
                "fair_value": None,
                "expected_return": candidate.get("expected_return"),
                "discount": None,
                "ic_verdict": None,
                "conviction": None,
                "conviction_max": 5,
                "why_it_exists": None,
                "thesis_narrative": None,
                "web_research_note": None,
                "valuation_method": "screener" if quality else None,
                "valuation_note": None,
                "quality": quality,
                "date": latest_screener.get("run_at"),
                "stage": "screened",
            })

    # Filter: only show tickers from the latest screener handoff (current pipeline)
    # This prevents accumulated results from old pipeline runs showing up
    if latest_screener:
        handoff_tickers_set = {
            (c.get("symbol") or c.get("ticker", "")).upper()
            for c in (latest_screener.get("top_results") or latest_screener.get("all_results") or [])
            if isinstance(c, dict)
        }
        if handoff_tickers_set:
            results = [r for r in results if r.get("ticker", "").upper() in handoff_tickers_set]

    return {"results": results}


@router.get("/thesis/{ticker}")
async def get_thesis(ticker: str):
    """Get latest thesis for a ticker."""
    db = get_db()
    runs = db.get_latest_runs("thesis", ticker=validate_ticker(ticker), limit=1)
    if not runs:
        return {"thesis": None, "message": f"No thesis for {ticker}"}
    return runs[0]


# --- IC Review ---

@router.post("/ic-review/{ticker}")
async def run_ic_review(ticker: str):
    """Trigger IC review for a ticker. Uses constitution hurdles if set."""
    ticker = validate_ticker(ticker)
    config = get_config()
    constitution = _load_constitution(config)
    base_config = config.resolved.get("agents", {}).get("ic_review", {}).get("config", {})
    agent_config = _apply_ic_hurdles(base_config, constitution)

    agent = ICReviewAgent(
        config=agent_config,
        llm=get_llm(),
        db=get_db(),
        library=get_library(),
    )

    # Get thesis context — parse full_output so IC agent gets structured thesis data
    import json as _json
    db = get_db()
    thesis_runs = db.get_latest_runs("thesis", ticker=ticker, limit=1)
    if thesis_runs:
        raw_run = thesis_runs[0]
        try:
            thesis_data = _json.loads(raw_run["full_output"]) if isinstance(raw_run.get("full_output"), str) else (raw_run.get("full_output") or {})
        except Exception:
            thesis_data = {}
        context = {"ticker": ticker, "thesis": thesis_data, "constitution": constitution, **thesis_data}
    else:
        context = {"ticker": ticker, "constitution": constitution}

    jobs = get_job_queue()
    job_id = await jobs.submit(
        "ic_review", agent.run, context, ticker=ticker,
        on_complete=_ic_drift_callback(config),
    )
    return {"job_id": job_id, "status": "running", "ticker": ticker}


def _ic_drift_callback(config):
    """Return a callback that runs Loop 2 behavioral drift analysis after IC review.

    Non-blocking: if drift analysis fails, the IC result is unaffected.
    Only triggers when >=3 IC decisions exist in the judgment events table,
    ensuring enough data for meaningful behavioral comparison.
    """
    async def _on_ic_complete(job):
        try:
            from backend.learning.behavioral import analyze_drift
            from backend.core.db_v2 import ScreenerV2DB

            db_path = config.resolved.get("db_path", str(Path.home() / ".fundops" / "fundops.db"))
            v2db = ScreenerV2DB(db_path=db_path)
            try:
                # Count recent IC decisions
                ic_passes = v2db.get_events_by_type("ic_passed", limit=50)
                ic_fails = v2db.get_events_by_type("ic_failed", limit=50)
                ic_decisions = ic_passes + ic_fails

                if len(ic_decisions) < 3:
                    log.debug(
                        f"Only {len(ic_decisions)} IC decisions — skipping drift analysis (need >=3)"
                    )
                    return

                constitution = v2db.get_active_constitution()
                if not constitution:
                    log.debug("No active constitution — skipping drift analysis")
                    return

                drift = await analyze_drift(v2db, constitution)
                has_drift = bool(
                    drift.get("signal_drift")
                    or drift.get("anti_signal_violations")
                    or drift.get("style_drift")
                )
                if has_drift:
                    log.info(f"Behavioral drift detected after IC batch: {drift.get('summary', '')}")
                    v2db.record_judgment_event(
                        event_type="drift_detected",
                        agent="behavioral",
                        data=drift,
                        rationale=drift.get("summary", "Drift detected"),
                    )
                else:
                    log.debug("No behavioral drift detected after IC review")
            finally:
                v2db.close()
        except Exception as e:
            log.warning(f"Drift analysis trigger failed (non-blocking): {e}")

    return _on_ic_complete


@router.get("/ic-review")
async def list_ic_reviews():
    """List all IC reviews + thesis-complete tickers pending IC, formatted for Research page.

    Includes both completed IC reviews AND thesis-complete tickers that haven't
    been IC'd yet (shown as verdict='pending'). This makes the IC tab show the
    full pipeline state.
    """
    import json as _json
    db = get_db()
    runs = db.get_latest_runs("ic_review", limit=100)
    results = []
    seen = set()
    skip_tickers = {"PIPELINE", "BATCH"}

    # 1. Completed IC reviews
    for run in runs:
        ticker = run.get("ticker", "")
        if not ticker or ticker in seen or ticker in skip_tickers:
            continue
        seen.add(ticker)
        try:
            raw = _json.loads(run["full_output"]) if isinstance(run.get("full_output"), str) else (run.get("full_output") or {})
        except Exception:
            raw = {}
        scores = run.get("scores") or {}
        if isinstance(scores, str):
            try:
                scores = _json.loads(scores)
            except Exception:
                scores = {}
        v = (raw.get("verdict") or run.get("verdict") or "").upper()
        verdict = "pass" if v == "PASS" else "no_pass" if v == "NO_PASS" else "pending"
        # Build full scorecard from constitution_scorecard (met + missed)
        cs = raw.get("constitution_scorecard") or {}
        signals_met = cs.get("signals_met") or []
        signals_missed = cs.get("signals_missed") or []
        anti_signals_raw = cs.get("anti_signals_triggered") or []
        # Fallback: if scorecard empty, re-derive from thesis quality + active constitution dimensions
        if not signals_met and not signals_missed:
            try:
                from backend.agents.ic_review import ICReviewAgent as _ICAgent
                _constitution = _load_constitution(get_config())
                if _constitution:
                    _thesis = raw.get("thesis") or raw
                    _recomputed = _ICAgent()._build_constitution_scorecard(_thesis, _constitution)
                    signals_met = _recomputed.get("signals_met") or []
                    signals_missed = _recomputed.get("signals_missed") or []
                    anti_signals_raw = _recomputed.get("anti_signals_triggered") or []
            except Exception:
                pass
        # Fallback: old scorecard_signals field (has met flag inline)
        legacy_sc = raw.get("scorecard_signals") or []
        if legacy_sc:
            scorecard = [{"label": s.get("label") or s.get("signal", ""), "met": s.get("met", False), "actual": s.get("actual", "")} for s in legacy_sc]
        else:
            def _sc_label(s):
                if isinstance(s, dict):
                    return s.get("label") or s.get("signal") or str(s)
                return s
            scorecard = (
                [{"label": _sc_label(s), "met": True,  "actual": s.get("actual", "") if isinstance(s, dict) else ""} for s in signals_met] +
                [{"label": _sc_label(s), "met": False, "actual": s.get("actual", "") if isinstance(s, dict) else ""} for s in signals_missed]
            )
        anti_signals = [{"label": a.get("label", a) if isinstance(a, dict) else a, "value": a.get("value", "") if isinstance(a, dict) else ""} for a in anti_signals_raw]
        criteria_met = len(signals_met) if (signals_met or signals_missed) else None
        criteria_total = (len(signals_met) + len(signals_missed)) if (signals_met or signals_missed) else None
        results.append({
            "ticker": ticker,
            "verdict": verdict,
            "base_return": raw.get("base_return") or scores.get("base_return"),
            "bear_return": raw.get("bear_return") or scores.get("bear_return"),
            "conviction": raw.get("conviction") or scores.get("conviction"),
            "conviction_max": 5,
            "key_risk": raw.get("key_risk"),
            "haircut_pct": raw.get("haircut_pct", 70),
            "bear_hurdle": raw.get("hurdle_bear", 15),
            "discount_floor": str(raw.get("discount_floor", "30%")),
            "discount_actual": f"{raw.get('discount_pct', 0):.1f}%" if raw.get("discount_pct") is not None else None,
            "discount_met": raw.get("discount_floor_met"),
            "scorecard": scorecard,
            "criteria_met": criteria_met,
            "criteria_total": criteria_total,
            "anti_signals": anti_signals,
            "anti_signal_count": len(anti_signals),
            "ai_review": raw.get("ai_review"),
            "key_assumptions": raw.get("key_assumptions", []),
            "similar_research": raw.get("similar_research"),
            "date": run.get("run_at"),
        })

    # Auto-flow: show top 10 thesis-complete tickers as pending IC.
    # Sources: agent_runs + judgment_events (for runs without full_output).
    thesis_complete_tickers = []

    # From agent_runs
    thesis_runs = db.get_latest_runs("thesis", limit=200)
    thesis_seen = set()
    for run in thesis_runs:
        ticker = run.get("ticker", "")
        if not ticker or ticker in seen or ticker in skip_tickers or ticker in thesis_seen:
            continue
        thesis_seen.add(ticker)
        try:
            raw = _json.loads(run["full_output"]) if isinstance(run.get("full_output"), str) else (run.get("full_output") or {})
        except Exception:
            raw = {}
        exp_ret = raw.get("expected_return") or run.get("fair_value")
        if not exp_ret and not raw:
            continue
        thesis_complete_tickers.append({
            "ticker": ticker,
            "company_name": raw.get("company_name", ""),
            "verdict": "pending",
            "base_return": raw.get("expected_return"),
            "bear_return": None,
            "conviction": raw.get("conviction"),
            "conviction_max": 5,
            "key_risk": None,
            "date": run.get("run_at"),
        })

    # Also from judgment_events (for thesis runs that only have event data)
    try:
        from backend.core.db_v2 import ScreenerV2DB
        v2db_ic = ScreenerV2DB(db_path=db.db_path)
        thesis_events = v2db_ic.conn.execute(
            "SELECT ticker, data, created_at FROM judgment_events "
            "WHERE event_type = 'thesis_generated' ORDER BY created_at DESC"
        ).fetchall()
        for ev in thesis_events:
            ticker = ev[0]
            if not ticker or ticker in seen or ticker in skip_tickers or ticker in thesis_seen:
                continue
            thesis_seen.add(ticker)
            jev_data = _json.loads(ev[1]) if isinstance(ev[1], str) else (ev[1] or {})
            if not jev_data.get("expected_return"):
                continue
            thesis_complete_tickers.append({
                "ticker": ticker,
                "company_name": "",
                "verdict": "pending",
                "base_return": jev_data.get("expected_return"),
                "bear_return": None,
                "conviction": jev_data.get("conviction"),
                "conviction_max": 5,
                "key_risk": None,
                "date": ev[2],
            })
        v2db_ic.close()
    except Exception:
        pass

    if thesis_complete_tickers:
        # Auto-flow: fill IC Review up to 10 total (existing IC runs count toward the 10)
        existing_ic_count = len(results)  # How many already have IC runs
        slots_remaining = max(0, 10 - existing_ic_count)
        if slots_remaining > 0:
            thesis_for_ic = sorted(
                thesis_complete_tickers,
                key=lambda x: x.get("base_return") or 0,
                reverse=True,
            )[:slots_remaining]
            for item in thesis_for_ic:
                seen.add(item["ticker"])
            results.extend(thesis_for_ic)

    # Filter: only show tickers from the latest screener handoff (current pipeline)
    try:
        from backend.core.db_v2 import ScreenerV2DB
        _v2_ic = ScreenerV2DB(db_path=db.db_path)
        _latest = _v2_ic.get_latest_screener_results()
        _v2_ic.close()
        if _latest:
            _handoff = _latest.get("top_results") or _latest.get("all_results") or []
            _handoff_set = {
                (c.get("symbol") or c.get("ticker", "")).upper()
                for c in _handoff if isinstance(c, dict)
            }
            if _handoff_set:
                results = [r for r in results if r.get("ticker", "").upper() in _handoff_set]
    except Exception:
        pass

    return {"results": results}


@router.get("/ic-review/{ticker}")
async def get_ic_review(ticker: str):
    """Get latest IC review for a ticker."""
    db = get_db()
    runs = db.get_latest_runs("ic_review", ticker=validate_ticker(ticker), limit=1)
    if not runs:
        return {"review": None, "message": f"No IC review for {ticker}"}
    return runs[0]


class OverrideRequest(BaseModel):
    note: Optional[str] = None


class DismissRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/ic-review/{ticker}/override")
async def override_ic_review(ticker: str, body: OverrideRequest = None):
    """Manually override a NO_PASS verdict to PASS (analyst conviction overrides IC)."""
    import json as _json
    db = get_db()
    t = validate_ticker(ticker)
    # Record an overridden IC pass in the DB so it shows as PASS in Research > Approved
    db.record_run(
        agent="ic_review", ticker=t,
        verdict="PASS",
        scores={"conviction": 3, "base_return": 0, "bear_return": 0, "overridden": True},
        summary=f"PASS (manual override{': ' + body.note if body and body.note else ''})",
        full_output={"ticker": t, "verdict": "PASS", "overridden": True,
                     "override_note": body.note if body else None},
    )
    return {"overridden": True, "ticker": t}


@router.post("/research/dismiss/{ticker}")
async def dismiss_ticker(ticker: str, body: DismissRequest = None):
    """Dismiss a ticker from the research pipeline."""
    db = get_db()
    t = validate_ticker(ticker)
    db.record_run(
        agent="research", ticker=t,
        verdict="DISMISSED",
        scores={"dismissed": True},
        summary=f"Dismissed{': ' + body.reason if body and body.reason else ''}",
        full_output={"ticker": t, "verdict": "DISMISSED",
                     "dismiss_reason": body.reason if body else None},
    )
    return {"dismissed": True, "ticker": t}


@router.post("/research/promote/{ticker}")
async def promote_ticker(ticker: str):
    """Manually promote a ticker to the next pipeline stage.

    - If ticker has screener result but no thesis → trigger thesis
    - If ticker has thesis but no IC review → trigger IC review
    - If ticker has IC PASS but not yet in approved → already approved (no-op)
    - If ticker has IC NO_PASS → override to PASS (promote to approved)
    """
    import json as _json
    t = validate_ticker(ticker)
    db = get_db()

    # Check what stage this ticker is at
    ic_runs = db.get_latest_runs("ic_review", ticker=t, limit=1)
    thesis_runs = db.get_latest_runs("thesis", ticker=t, limit=1)

    if ic_runs:
        # Has IC review — check verdict
        try:
            raw = _json.loads(ic_runs[0]["full_output"]) if isinstance(ic_runs[0].get("full_output"), str) else (ic_runs[0].get("full_output") or {})
        except Exception:
            raw = {}
        v = (raw.get("verdict") or ic_runs[0].get("verdict") or "").upper()
        if v == "PASS":
            return {"promoted": True, "ticker": t, "action": "already_approved", "message": f"{t} already has IC PASS"}
        else:
            # Override NO_PASS to PASS
            db.record_run(
                agent="ic_review", ticker=t,
                verdict="PASS",
                scores={"conviction": 3, "base_return": 0, "bear_return": 0, "overridden": True},
                summary=f"PASS (promoted via pipeline)",
                full_output={"ticker": t, "verdict": "PASS", "overridden": True, "override_note": "Promoted via pipeline"},
            )
            return {"promoted": True, "ticker": t, "action": "override_to_pass", "message": f"{t} promoted to approved"}

    if thesis_runs:
        # Has thesis but no IC → queue for IC review (don't run yet)
        # Record a pending IC review so it appears in the IC Review tab
        db.record_run(
            agent="ic_review", ticker=t,
            verdict="pending",
            summary=f"Queued for IC review",
            full_output={"ticker": t, "verdict": "pending", "queued": True},
        )
        return {"promoted": True, "ticker": t, "action": "queued_for_ic", "message": f"{t} moved to IC Review"}

    # No thesis → trigger thesis
    result = await run_thesis(t)
    return {"promoted": True, "ticker": t, "action": "trigger_thesis", "job_id": result.get("job_id")}


@router.post("/ic-review/batch")
async def run_ic_review_batch():
    """Batch IC review for all tickers with thesis."""
    db = get_db()
    # Get all tickers with thesis but no IC review
    # For now, return a placeholder
    return {"message": "Batch IC review not yet implemented", "status": "pending"}


# --- Research (Approved + Memos) ---

@router.get("/research/approved")
async def list_approved():
    """List IC-passed tickers ready for memo generation."""
    import json as _json
    db = get_db()
    ic_runs = db.get_latest_runs("ic_review", limit=100)
    results = []
    seen = set()
    skip_tickers = {"PIPELINE", "BATCH"}
    for run in ic_runs:
        ticker = run.get("ticker", "")
        if not ticker or ticker in seen or ticker in skip_tickers:
            continue
        seen.add(ticker)
        v = (run.get("verdict") or "").upper()
        if v != "PASS":
            continue
        try:
            raw = _json.loads(run["full_output"]) if isinstance(run.get("full_output"), str) else (run.get("full_output") or {})
        except Exception:
            raw = {}
        scores = run.get("scores") or {}
        if isinstance(scores, str):
            try:
                scores = _json.loads(scores)
            except Exception:
                scores = {}
        # Check if memos exist (distinguish research vs investment type)
        memo_runs = db.get_latest_runs("memo", ticker=ticker, limit=20)
        research_ready = any(r.get("run_type") == "research" for r in memo_runs)
        investment_ready = any(r.get("run_type") == "investment" for r in memo_runs)
        # Fallback: any memo run counts (job_complete with content also means ready)
        any_memo = bool(memo_runs) and any(
            r.get("run_type") in ("research", "investment", "job_complete") for r in memo_runs
        )
        # Try to get fair_value from IC output or thesis run
        fv = raw.get("fair_value")
        if not fv:
            thesis_runs = db.get_latest_runs("thesis", ticker=ticker, limit=1)
            if thesis_runs:
                try:
                    t_raw = _json.loads(thesis_runs[0]["full_output"]) if isinstance(thesis_runs[0].get("full_output"), str) else (thesis_runs[0].get("full_output") or {})
                except Exception:
                    t_raw = {}
                fv = t_raw.get("fair_value") or thesis_runs[0].get("fair_value")
        results.append({
            "ticker": ticker,
            "company_name": raw.get("company_name"),
            "approved_date": run.get("run_at"),
            "fair_value": fv,
            "expected_return": raw.get("base_return") or scores.get("base_return"),
            "conviction": raw.get("conviction") or scores.get("conviction"),
            "conviction_max": 5,
            "research_report_ready": research_ready or any_memo,
            "investment_memo_ready": investment_ready,
            "research_report_cost": 1.0,
            "investment_memo_cost": 0.5,
        })

    # Note: Only tickers with IC verdict = PASS appear in Approved.
    # NO_PASS tickers stay in IC Review for the user to override or dismiss.

    # Filter: only show tickers from the latest screener handoff (current pipeline)
    try:
        from backend.core.db_v2 import ScreenerV2DB
        _v2_app = ScreenerV2DB(db_path=db.db_path)
        _latest = _v2_app.get_latest_screener_results()
        _v2_app.close()
        if _latest:
            _handoff = _latest.get("top_results") or _latest.get("all_results") or []
            _handoff_set = {
                (c.get("symbol") or c.get("ticker", "")).upper()
                for c in _handoff if isinstance(c, dict)
            }
            if _handoff_set:
                results = [r for r in results if r.get("ticker", "").upper() in _handoff_set]
    except Exception:
        pass

    return {"results": results}


async def _memo_with_library_ingest(memo_agent, context: dict):
    """Run memo agent, then auto-ingest result into library.

    Wraps the memo agent run so the job queue executes both steps
    as a single background task. Library ingest failure is non-fatal.
    """
    import logging
    _log = logging.getLogger("fundops.memo")

    result = await memo_agent.run(context)

    # Auto-ingest to library on successful memo completion
    if result.status == "complete" and result.data:
        try:
            config = get_config()
            db_path = config.resolved.get("db_path", str(Path.home() / ".fundops" / "fundops.db"))
            from backend.core.db_v2 import ScreenerV2DB
            v2db = ScreenerV2DB(db_path=db_path)
            library = LibraryAgent(db=get_db(), v2db=v2db)
            await library.run({
                "ticker": result.data.get("ticker", context.get("ticker", "")),
                "artifact_type": "memo",
                "data": result.data,
                "constitution": context.get("constitution"),
            })
            v2db.close()
            _log.info(f"Library auto-ingest complete for memo {context.get('ticker')}")
        except Exception as e:
            _log.warning(f"Library auto-ingest failed for memo {context.get('ticker')}: {e}")

    return result


@router.post("/research/report/{ticker}")
async def generate_research_report(ticker: str):
    """Trigger full research memo pipeline for a ticker. Passes constitution for strategy lens."""
    from backend.agents.memo import MemoAgent
    ticker = validate_ticker(ticker)
    config = get_config()
    constitution = _load_constitution(config)
    agent_config = config.resolved.get("agents", {}).get("memo", {}).get("config", {})
    agent = MemoAgent(
        config=agent_config,
        fmp=get_fmp(),
        sec=get_sec(),
        yfinance=get_yfinance(),
        llm=get_llm(),
        db=get_db(),
    )
    jobs = get_job_queue()
    memo_fn = lambda ctx: _memo_with_library_ingest(agent, ctx)
    job_id = await jobs.submit("research_report", memo_fn, {"ticker": ticker, "mode": "research", "constitution": constitution}, ticker=ticker)
    return {"job_id": job_id, "status": "running", "ticker": ticker}


@router.post("/research/memo/{ticker}")
async def generate_investment_memo(ticker: str):
    """Trigger investment memo generation for a ticker. Passes constitution for strategy lens."""
    from backend.agents.memo import MemoAgent
    ticker = validate_ticker(ticker)
    config = get_config()
    constitution = _load_constitution(config)
    agent_config = config.resolved.get("agents", {}).get("memo", {}).get("config", {})
    agent = MemoAgent(
        config=agent_config,
        fmp=get_fmp(),
        sec=get_sec(),
        yfinance=get_yfinance(),
        llm=get_llm(),
        db=get_db(),
    )
    jobs = get_job_queue()
    memo_fn = lambda ctx: _memo_with_library_ingest(agent, ctx)
    job_id = await jobs.submit("investment_memo", memo_fn, {"ticker": ticker, "mode": "investment", "constitution": constitution}, ticker=ticker)
    return {"job_id": job_id, "status": "running", "ticker": ticker}


# --- Library ---

@router.post("/library/sync")
async def run_library_sync():
    """Trigger library sync — ingest artifacts + run outcome checker (learning loop)."""
    from backend.agents.library import LibraryAgent
    config = get_config()
    constitution = _load_constitution(config)
    db = get_db()
    from backend.core.db_v2 import ScreenerV2DB
    db_path = config.resolved.get("db_path", str(Path.home() / ".fundops" / "fundops.db"))
    v2db = ScreenerV2DB(db_path=db_path)
    agent = LibraryAgent(
        config=config.resolved.get("agents", {}).get("library", {}).get("config", {}),
        db=db, v2db=v2db,
    )

    async def _sync_with_learning(ctx):
        """Ingest artifacts, then run outcome checker + portfolio health refresh."""
        import logging
        _log = logging.getLogger("fundops.library")

        # Step 1: Ingest recent research artifacts
        result = await agent.run(ctx)

        # Step 2: Run outcome checker (learning loop — checks prediction accuracy)
        try:
            outcome_agent = get_outcome_checker()
            outcome_result = await outcome_agent.run(ctx)
            outcomes_checked = len(outcome_result.data.get("checked", [])) if outcome_result.data else 0
            if result.data:
                result.data["outcomes_checked"] = outcomes_checked
            _log.info(f"Library sync: outcome checker evaluated {outcomes_checked} positions")
        except Exception as e:
            _log.warning(f"Outcome checker failed during library sync: {e}")
            if result.data:
                result.data["outcomes_checked"] = 0

        # Step 3: Refresh thesis health for held positions
        try:
            portfolio_agent = PortfolioAgent(
                config=config.resolved.get("agents", {}).get("portfolio", {}).get("config", {}),
                fmp=get_fmp(),
                yfinance=get_yfinance(),
                db=get_db(),
                sec=get_sec(),
                v2db=get_v2db(),
                web_search=get_web_search(),
                llm=get_llm(),
            )
            portfolio_result = await portfolio_agent.run(ctx)
            health_count = len([
                h for h in (portfolio_result.data or {}).get("holdings", [])
                if h.get("thesis_health")
            ])
            if result.data:
                result.data["health_checks_run"] = health_count
            _log.info(f"Library sync: portfolio health refreshed for {health_count} positions")
        except Exception as e:
            _log.warning(f"Portfolio health refresh failed during library sync: {e}")

        return result

    jobs = get_job_queue()
    job_id = await jobs.submit("library", _sync_with_learning, {"constitution": constitution})
    return {"job_id": job_id, "status": "running"}


_MEMO_CONTENT_TYPES = {"research", "investment", "both"}

@router.get("/library/memos")
async def get_memos(search: str = "", type: str = "", sector: str = ""):
    """Get all memos with optional search/filter."""
    db = get_db()
    runs = db.get_latest_runs("memo", limit=100)
    # Only return actual content runs, not job tracking entries
    content_runs = [r for r in runs if r.get("run_type") in _MEMO_CONTENT_TYPES]
    return {"memos": content_runs, "total": len(content_runs)}


@router.get("/library/memos/{ticker}")
async def get_memo_for_ticker(ticker: str, type: str = ""):
    """Get memo for a specific ticker."""
    db = get_db()
    runs = db.get_latest_runs("memo", ticker=validate_ticker(ticker), limit=20)
    # Only return actual content runs, not job tracking entries
    content_runs = [r for r in runs if r.get("run_type") in _MEMO_CONTENT_TYPES]
    return {"memos": content_runs}


# --- Portfolio ---

@router.post("/portfolio/run")
async def run_portfolio():
    """Trigger portfolio monitoring. Uses constitution for alert thresholds."""
    config = get_config()
    constitution = _load_constitution(config)
    agent_config = config.resolved.get("agents", {}).get("portfolio", {}).get("config", {})

    # Merge constitution alert thresholds into agent config
    if constitution:
        agent_profiles = constitution.get("agent_profiles") or {}
        portfolio_profile = agent_profiles.get("portfolio") or {}
        alert_on = agent_config.get("alert_on", [])
        if portfolio_profile.get("concentration_limit_pct"):
            alert_on = [a for a in alert_on if "concentration_above_pct" not in (a if isinstance(a, dict) else {})]
            alert_on.append({"concentration_above_pct": portfolio_profile["concentration_limit_pct"]})
        if portfolio_profile.get("drawdown_threshold_pct"):
            alert_on = [a for a in alert_on if "drawdown_below_pct" not in (a if isinstance(a, dict) else {})]
            alert_on.append({"drawdown_below_pct": portfolio_profile["drawdown_threshold_pct"]})
        agent_config = dict(agent_config, alert_on=alert_on)

    agent = PortfolioAgent(
        config=agent_config,
        fmp=get_fmp(),
        yfinance=get_yfinance(),
        db=get_db(),
        sec=get_sec(),
        v2db=get_v2db(),
        web_search=get_web_search(),
        llm=get_llm(),
    )

    jobs = get_job_queue()
    job_id = await jobs.submit("portfolio", agent.run, {"constitution": constitution})
    return {"job_id": job_id, "status": "running"}


@router.get("/portfolio/status")
async def get_portfolio_status():
    """Get latest portfolio data."""
    import json as _json
    db = get_db()
    snapshot = db.get_latest_portfolio_snapshot()
    if not snapshot:
        return {"holdings": [], "alerts": []}
    # Parse JSON fields that SQLite stores as strings
    for field in ("holdings", "alerts"):
        val = snapshot.get(field)
        if isinstance(val, str):
            try:
                snapshot[field] = _json.loads(val)
            except Exception:
                snapshot[field] = []
        elif val is None:
            snapshot[field] = []
    # Enrich holdings with sector/industry from tickers table
    for h in (snapshot.get("holdings") or []):
        if not h.get("sector"):
            row = db.conn.execute(
                "SELECT sector, industry FROM tickers WHERE ticker = ?",
                (h.get("ticker", ""),)
            ).fetchone()
            if row:
                h["sector"] = row[0] or ""
                h["industry"] = row[1] or ""
    # Compute total_pnl and total_pnl_pct from holdings if missing
    holdings = snapshot.get("holdings") or []
    if holdings and snapshot.get("total_pnl_pct") is None:
        total_cost = sum(
            (h.get("shares", 0) or 0) * (h.get("cost_basis", 0) or 0)
            for h in holdings
        )
        total_value = snapshot.get("total_value") or sum(
            h.get("market_value", 0) or 0 for h in holdings
        )
        total_pnl = total_value - total_cost
        snapshot["total_pnl"] = round(total_pnl, 2)
        snapshot["total_pnl_pct"] = round(total_pnl / total_cost * 100, 1) if total_cost > 0 else 0
    return snapshot


# --- Allocator ---

@router.post("/allocator/run")
async def run_allocator():
    """Trigger allocator. Uses constitution for position sizing rules."""
    config = get_config()
    constitution = _load_constitution(config)
    base_agent_config = config.resolved.get("agents", {}).get("allocator", {}).get("config", {})
    agent_config = dict(base_agent_config)

    # Merge constitution position sizing into agent config
    if constitution:
        pos_sizing = constitution.get("position_sizing") or {}
        agent_profiles = constitution.get("agent_profiles") or {}
        alloc_profile = agent_profiles.get("allocator") or {}

        if pos_sizing.get("max_position_pct") is not None:
            agent_config["concentration_limit_pct"] = pos_sizing["max_position_pct"]
        if alloc_profile.get("max_position_pct") is not None:
            agent_config["concentration_limit_pct"] = alloc_profile["max_position_pct"]
        if alloc_profile.get("min_expected_return_pct") is not None:
            agent_config["min_expected_return_pct"] = alloc_profile["min_expected_return_pct"]
        # Pass position type ranges from constitution
        if alloc_profile.get("position_types"):
            agent_config["position_types"] = alloc_profile["position_types"]

    # Get latest portfolio data as context
    import json as _json
    db = get_db()
    snapshot = db.get_latest_portfolio_snapshot() or {}
    # Deserialize JSON string fields (DB stores them as JSON text)
    for key in ("holdings", "alerts"):
        val = snapshot.get(key)
        if isinstance(val, str):
            try:
                snapshot[key] = _json.loads(val)
            except Exception:
                snapshot[key] = []

    # Enrich each holding with research data (memos, thesis, IC, financials)
    holdings = snapshot.get("holdings") or []
    held_tickers = [h.get("ticker") for h in holdings if h.get("ticker")]

    research_context = {}
    for ticker in held_tickers:
        rc = {}
        # Latest thesis
        thesis_run = db.get_latest_run(ticker, "thesis")
        if thesis_run:
            fo = thesis_run.get("full_output")
            if isinstance(fo, str):
                try: fo = _json.loads(fo)
                except Exception: fo = {}
            rc["thesis"] = {
                "summary": thesis_run.get("summary", ""),
                "fair_value": thesis_run.get("fair_value"),
                "expected_return": fo.get("expected_return") if isinstance(fo, dict) else None,
                "return_sources": fo.get("return_sources") if isinstance(fo, dict) else None,
                "key_assumptions": fo.get("key_assumptions") if isinstance(fo, dict) else None,
            }
        # Latest IC review
        ic_run = db.get_latest_run(ticker, "ic_review")
        if ic_run:
            fo = ic_run.get("full_output")
            if isinstance(fo, str):
                try: fo = _json.loads(fo)
                except Exception: fo = {}
            rc["ic_review"] = {
                "verdict": ic_run.get("verdict"),
                "summary": ic_run.get("summary", ""),
                "base_return": fo.get("base_expected_return") if isinstance(fo, dict) else None,
                "bear_return": fo.get("bear_expected_return") if isinstance(fo, dict) else None,
                "conviction": fo.get("conviction") if isinstance(fo, dict) else None,
            }
        # Latest memo (research report or investment memo)
        for memo_agent in ("research_report", "investment_memo", "memo"):
            memo_runs = db.get_latest_runs(memo_agent, ticker=ticker, limit=1)
            memo_runs = [r for r in memo_runs if r.get("run_type") not in ("job_start", "job_failed", "job_complete")]
            if memo_runs:
                mr = memo_runs[0]
                fo = mr.get("full_output")
                if isinstance(fo, str):
                    try: fo = _json.loads(fo)
                    except Exception: fo = {}
                memo_type = mr.get("run_type") or memo_agent
                rc.setdefault("memos", {})[memo_type] = {
                    "summary": mr.get("summary", ""),
                    "run_at": mr.get("run_at"),
                    # Include key sections if available (truncated to keep context manageable)
                    "content_preview": (fo.get("narrative") or fo.get("content") or "")[:2000] if isinstance(fo, dict) else "",
                }
        # Financial data from ticker_financials
        try:
            from backend.core.db_v2 import ScreenerV2DB
            from backend.core.financial_data import FinancialData
            v2db = ScreenerV2DB()
            stored = v2db.get_ticker_financials(ticker)
            if stored:
                fd = FinancialData.from_dict(stored["financial_data"])
                rc["financials"] = fd.to_flat_metrics()
        except Exception as e:
            log.debug(f"Failed to load financials for {ticker}: {e}")

        if rc:
            research_context[ticker] = rc

    # Load IC-approved opportunities not in portfolio (new buy candidates)
    approved_opps = []
    try:
        from backend.core.db_v2 import ScreenerV2DB
        v2db = ScreenerV2DB()
        # Get approved tickers from judgment_events
        approved_rows = db.conn.execute(
            "SELECT DISTINCT ticker FROM judgment_events WHERE verdict = 'PASS'"
        ).fetchall()
        for row in approved_rows:
            aticker = row[0]
            if aticker in held_tickers:
                continue  # Already held
            opp = {"ticker": aticker}
            # Get thesis data
            thesis_run = db.get_latest_run(aticker, "thesis")
            if thesis_run:
                fo = thesis_run.get("full_output")
                if isinstance(fo, str):
                    try: fo = _json.loads(fo)
                    except Exception: fo = {}
                opp["fair_value"] = thesis_run.get("fair_value")
                opp["expected_return"] = fo.get("expected_return") if isinstance(fo, dict) else None
                opp["return_sources"] = fo.get("return_sources") if isinstance(fo, dict) else None
                opp["thesis_summary"] = thesis_run.get("summary", "")
            # Get IC review data
            ic_run = db.get_latest_run(aticker, "ic_review")
            if ic_run:
                fo = ic_run.get("full_output")
                if isinstance(fo, str):
                    try: fo = _json.loads(fo)
                    except Exception: fo = {}
                opp["conviction"] = fo.get("conviction") if isinstance(fo, dict) else None
                opp["base_return"] = fo.get("base_expected_return") if isinstance(fo, dict) else None
                opp["bear_return"] = fo.get("bear_expected_return") if isinstance(fo, dict) else None
            # Get financials
            stored = v2db.get_ticker_financials(aticker)
            if stored:
                fd = FinancialData.from_dict(stored["financial_data"])
                opp["financials"] = fd.to_flat_metrics()
            # Get memo data
            for memo_agent in ("research_report", "investment_memo", "memo"):
                memo_runs = db.get_latest_runs(memo_agent, ticker=aticker, limit=1)
                memo_runs = [r for r in memo_runs if r.get("run_type") not in ("job_start", "job_failed", "job_complete")]
                if memo_runs:
                    mr = memo_runs[0]
                    opp["has_memo"] = True
                    opp["memo_summary"] = mr.get("summary", "")
                    break
            approved_opps.append(opp)
    except Exception as e:
        log.warning(f"Failed to load approved opportunities: {e}")

    context = {
        **snapshot,
        "constitution": constitution,
        "research_context": research_context,
        "approved_opportunities": approved_opps,
    }

    agent = AllocatorAgent(config=agent_config, db=db, llm=get_llm())

    jobs = get_job_queue()
    job_id = await jobs.submit("allocator", agent.run, context)
    return {"job_id": job_id, "status": "running"}


@router.get("/allocator/recommendations")
async def get_allocator_recommendations():
    """Get latest allocator actions, enriched with constitution policy."""
    import json as _json
    db = get_db()
    runs = db.get_latest_runs("allocator", limit=1)
    if not runs:
        return {"actions": None, "message": "No allocator runs yet"}
    result = runs[0]

    # Parse full_output JSON string and merge into top-level result
    fo = result.get("full_output")
    if isinstance(fo, str):
        try:
            fo = _json.loads(fo)
        except Exception:
            fo = {}
    if isinstance(fo, dict):
        result.update(fo)

    # Build kpis and alerts for frontend AllocatorData shape
    actions_req = result.get("actions_required") or []
    monitoring = result.get("monitoring") or []
    no_action = result.get("no_action") or []
    risk_health = result.get("risk_health") or {}
    summary = result.get("summary") or {}

    # Find highest-concentration position
    all_positions = actions_req + monitoring + no_action
    top_conc = max(all_positions, key=lambda x: x.get("current_weight", 0), default={})

    # Compute avg expected return from position analysis
    def _sf(v):
        try: return float(v)
        except (TypeError, ValueError): return 0.0
    returns = [_sf(p.get("expected_return", 0)) for p in all_positions if _sf(p.get("expected_return", 0)) > 0]
    weights = [_sf(p.get("current_weight", 0)) for p in all_positions if _sf(p.get("expected_return", 0)) > 0]
    total_w = sum(weights) if weights else 1
    avg_ret = sum(r * w for r, w in zip(returns, weights)) / total_w if total_w > 0 else 0

    new_positions = result.get("new_positions") or []

    # summary may be a string (from old runs) or dict (from new runs)
    if isinstance(summary, str):
        try:
            summary = _json.loads(summary)
        except Exception:
            summary = {}

    result["kpis"] = {
        "actions_pending": len(actions_req),
        "urgent_count": sum(1 for a in actions_req if a.get("urgency") == "high"),
        "monitor_count": len(monitoring),
        "concentration": top_conc.get("current_weight", 0),
        "concentration_ticker": top_conc.get("ticker", ""),
        "concentration_limit": 25,  # default, overridden below from constitution
        "cash_available": summary.get("trim_proceeds_est", 0) if isinstance(summary, dict) else 0,
        "cash_pct": 0,
        "avg_expected_return": round(avg_ret, 1),
        "new_opportunities": len(new_positions),
    }
    result["alerts"] = [
        {"severity": "danger" if "concentration" in a.lower() else "warning", "title": a, "description": ""}
        for a in risk_health.get("alerts", [])
    ]
    result["last_run"] = result.get("run_at", "")

    # Attach constitution-derived policy for the PolicyModal
    config = get_config()
    constitution = _load_constitution(config)
    if constitution:
        pos_sizing = constitution.get("position_sizing") or {}
        sell_discipline = constitution.get("sell_discipline") or {}
        agent_profiles = constitution.get("agent_profiles") or {}
        alloc_profile = agent_profiles.get("allocator") or {}
        portfolio_profile = agent_profiles.get("portfolio") or {}

        result["policy"] = {
            "max_position_pct": alloc_profile.get("max_position_pct") or pos_sizing.get("max_position_pct"),
            "concentration_limit_pct": alloc_profile.get("concentration_limit_pct") or pos_sizing.get("concentration_limit_pct"),
            "min_position_pct": pos_sizing.get("min_position_pct"),
            "position_types": alloc_profile.get("position_types"),
            "sell_discipline": sell_discipline if sell_discipline else None,
            "drawdown_threshold_pct": portfolio_profile.get("drawdown_threshold_pct"),
        }
        # Update kpis with constitution limits
        conc_limit = alloc_profile.get("concentration_limit_pct") or pos_sizing.get("concentration_limit_pct") or alloc_profile.get("max_position_pct") or pos_sizing.get("max_position_pct")
        if conc_limit:
            result["kpis"]["concentration_limit"] = conc_limit

    return result


class DiscussRequest(BaseModel):
    message: str
    history: list[dict] = []
    context: dict = {}


@router.post("/allocator/{ticker}/discuss")
async def discuss_position(ticker: str, body: DiscussRequest):
    """AI discussion about a specific position's allocation.

    Takes the position context (action, metrics, thesis) and the user's
    question, returns an AI response reasoning about the position.
    """
    ticker = validate_ticker(ticker)
    llm = get_llm()

    # Check if LLM is configured
    if not llm.api_key:
        return {
            "message": "AI discussion requires an AI model to be configured. Set up your AI model in Settings.",
            "role": "assistant",
        }

    # Load constitution for sell discipline / position sizing context
    config = get_config()
    constitution = _load_constitution(config)

    # Build system prompt with position context
    ctx = body.context or {}
    position_lines = [
        f"Ticker: {ticker}",
    ]
    if ctx.get("action"):
        position_lines.append(f"Recommended action: {ctx['action']}")
    if ctx.get("weight") is not None:
        position_lines.append(f"Current weight: {ctx['weight']}%")
    if ctx.get("weight_target") is not None:
        position_lines.append(f"Target weight: {ctx['weight_target']}%")
    if ctx.get("pnl_pct") is not None:
        position_lines.append(f"P&L: {ctx['pnl_pct']:+.1f}%")
    if ctx.get("reason"):
        position_lines.append(f"Reason: {ctx['reason']}")
    if ctx.get("type"):
        position_lines.append(f"Position type: {ctx['type']}")
    if ctx.get("health_score") is not None:
        position_lines.append(f"Thesis health: {ctx['health_score']}/100")

    # Add constitution context if available
    constitution_lines = []
    if constitution:
        pos_sizing = constitution.get("position_sizing") or {}
        if pos_sizing:
            constitution_lines.append("Position sizing policy:")
            if pos_sizing.get("max_position_pct") is not None:
                constitution_lines.append(f"  Max single position: {pos_sizing['max_position_pct']}%")
            if pos_sizing.get("min_position_pct") is not None:
                constitution_lines.append(f"  Min position size: {pos_sizing['min_position_pct']}%")
        sell_discipline = constitution.get("sell_discipline") or {}
        if sell_discipline:
            constitution_lines.append("Sell discipline:")
            for k, v in sell_discipline.items():
                constitution_lines.append(f"  {k}: {v}")
        agent_profiles = constitution.get("agent_profiles") or {}
        alloc_profile = agent_profiles.get("allocator") or {}
        if alloc_profile.get("position_types"):
            constitution_lines.append("Position type ranges:")
            for pt in alloc_profile["position_types"]:
                if isinstance(pt, dict):
                    constitution_lines.append(f"  {pt.get('type', '')}: {pt.get('min', '')}–{pt.get('max', '')}%")

    system_msg = (
        "You are a portfolio manager's AI co-PM for a concentrated value fund. "
        "The user is asking about a position action recommendation. "
        "Be direct, use numbers, reason about risk/reward. "
        "Keep responses concise — 2-4 sentences unless the question warrants more detail.\n\n"
        f"POSITION CONTEXT:\n" + "\n".join(position_lines)
    )
    if constitution_lines:
        system_msg += "\n\n" + "\n".join(constitution_lines)

    # Build messages for chat
    messages = [{"role": "system", "content": system_msg}]
    for h in body.history:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": body.message})

    try:
        result = await llm.generate_chat(
            messages=messages,
            agent="allocator_discuss",
            reasoning_effort="low",
        )
        return {
            "message": result.text or "I wasn't able to generate a response. Please try again.",
            "role": "assistant",
        }
    except Exception as e:
        log.error(f"Allocator discuss failed for {ticker}: {e}")
        return {
            "message": f"Failed to get AI response: {str(e)}",
            "role": "assistant",
        }


# --- Allocator Actions ---

@router.post("/allocator/{ticker}/action")
async def record_allocator_action(ticker: str, body: dict = {}):
    """Record that the user acted on an allocator recommendation.

    Stores the action in the DB so it's excluded from future allocator runs.
    """
    ticker = validate_ticker(ticker)
    db = get_db()
    action = body.get("action", "acknowledged")
    reason = body.get("reason", "")

    try:
        db.record_action(
            action=f"allocator_{action}",
            ticker=ticker,
            reason=reason or f"User acted on allocator recommendation: {action}",
            context=body,
        )
        return {"status": "recorded", "ticker": ticker, "action": action}
    except Exception as e:
        log.error(f"Failed to record allocator action for {ticker}: {e}")
        return {"error": str(e)}


# --- Outcome Checker ---

@router.post("/outcomes/check")
async def run_outcome_checker():
    """Run outcome checker on all held positions that are due for review.

    Checks thesis integrity, goal alignment, and researches what drove returns.
    Runs as a background job.
    """
    agent = get_outcome_checker()
    jobs = get_job_queue()
    config = get_config()
    constitution = _load_constitution(config)
    job_id = await jobs.submit("outcome_checker", agent.run, {"constitution": constitution})
    return {"job_id": job_id, "status": "running"}


@router.get("/outcomes/latest")
async def get_latest_outcomes(ticker: str = None, limit: int = 20):
    """Get latest outcome snapshots."""
    try:
        v2db = get_v2db()
        snapshots = v2db.get_outcome_snapshots(ticker=ticker, limit=limit)
        v2db.close()
        return {"outcomes": snapshots, "total": len(snapshots)}
    except Exception as e:
        return {"outcomes": [], "total": 0, "error": str(e)}


# --- Jobs ---

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Poll job status."""
    jobs = get_job_queue()
    status = jobs.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return status


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running or pending job."""
    jobs = get_job_queue()
    cancelled = jobs.cancel(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found or not cancellable")
    return {"cancelled": True, "job_id": job_id}


@router.get("/jobs")
async def list_jobs(status: str = None, agent: str = None):
    """List all jobs."""
    jobs = get_job_queue()
    return {"jobs": jobs.list_jobs(status=status, agent=agent)}


# --- Ticker Detail ---

@router.get("/ticker/{ticker}")
async def get_ticker_detail(ticker: str):
    """Full ticker detail with all agent runs."""
    import json as _json
    t = validate_ticker(ticker)
    db = get_db()
    pipeline = db.get_pipeline_status(t)

    # Helper: get first non-None value from a dict for multiple possible keys
    def _pick(d: dict, *keys):
        for k in keys:
            v = d.get(k)
            if v is not None:
                return v
        return None

    # Enrich with latest thesis
    thesis_runs = db.get_latest_runs("thesis", ticker=t, limit=1)
    thesis = None
    if thesis_runs:
        raw = thesis_runs[0]
        try:
            full = _json.loads(raw["full_output"]) if isinstance(raw.get("full_output"), str) else (raw.get("full_output") or {})
        except Exception:
            full = {}
        thesis = {
            "fair_value": _pick(full, "fair_value") or raw.get("fair_value"),
            "expected_return": full.get("expected_return"),
            "return_sources": full.get("return_sources"),
            "discount_pct": full.get("discount_pct"),
            "conviction": full.get("conviction"),
            "variant_view": full.get("variant_view"),
            "company_name": full.get("company_name"),
            "valuation": full.get("valuation"),
            "quality": full.get("quality"),
            "web_research": {
                "why_cheap": (full.get("web_research") or {}).get("why_cheap", "")[:500] if full.get("web_research") else None,
                "bull_case": (full.get("web_research") or {}).get("bull_case", "")[:500] if full.get("web_research") else None,
            } if full.get("web_research") else None,
            "similar_research": full.get("similar_research"),
            "constitution_fit": full.get("constitution_fit"),
            "run_at": raw.get("run_at"),
        }

    # Enrich with latest IC review
    # If the latest run is an override (bare verdict), also fetch the most recent
    # substantive IC review for the full analysis (AI review, stress-tested returns, etc.)
    ic_runs = db.get_latest_runs("ic_review", ticker=t, limit=5)
    ic_review = None
    if ic_runs:
        raw = ic_runs[0]
        try:
            full = _json.loads(raw["full_output"]) if isinstance(raw.get("full_output"), str) else (raw.get("full_output") or {})
        except Exception:
            full = {}

        is_override = full.get("overridden", False)

        # If override, find the latest substantive (non-override) run with rich data
        substantive = full
        substantive_run_at = raw.get("run_at")
        if is_override and len(ic_runs) > 1:
            for older_run in ic_runs[1:]:
                try:
                    older_full = _json.loads(older_run["full_output"]) if isinstance(older_run.get("full_output"), str) else (older_run.get("full_output") or {})
                except Exception:
                    older_full = {}
                # A substantive run has ai_review or base_return
                if older_full.get("ai_review") or older_full.get("base_return") is not None:
                    substantive = older_full
                    substantive_run_at = older_run.get("run_at")
                    break

        v = (full.get("verdict") or raw.get("verdict") or "").upper()
        ic_review = {
            "verdict": "pass" if v == "PASS" else "no_pass" if v == "NO_PASS" else "pending",
            # Pull from substantive run for analysis content
            "base_return": _pick(substantive, "base_return", "base_case_return"),
            "bear_return": _pick(substantive, "bear_return", "bear_case_return"),
            "conviction": _pick(substantive, "conviction", "ai_conviction"),
            "key_risk": _pick(substantive, "key_risk", "top_risk", "primary_risk"),
            "key_assumptions": substantive.get("key_assumptions"),
            "ai_review": _pick(substantive, "ai_review", "ai_review_summary"),
            "ai_verdict": substantive.get("ai_verdict"),
            "return_sources_base": substantive.get("return_sources_base"),
            "return_sources_bear": substantive.get("return_sources_bear"),
            "discount_pct": substantive.get("discount_pct"),
            "discount_floor": substantive.get("discount_floor"),
            "discount_floor_met": substantive.get("discount_floor_met"),
            "hurdle_base": substantive.get("hurdle_base"),
            "hurdle_bear": substantive.get("hurdle_bear"),
            "constitution_scorecard": substantive.get("constitution_scorecard"),
            "scorecard": substantive.get("scorecard"),
            "dimension_scores": substantive.get("dimension_scores"),
            "value_trap_signals": substantive.get("value_trap_signals"),
            "ai_rationale": substantive.get("ai_rationale"),
            "style_fit": substantive.get("style_fit"),
            "overridden": is_override,
            "override_note": full.get("override_note"),
            "original_verdict": substantive.get("verdict") if is_override else None,
            "analysis_run_at": substantive_run_at if is_override else None,
            "run_at": raw.get("run_at"),
        }

    # Screener metrics from db_v2 (rich stock data from latest screener run)
    metrics = {}
    try:
        from backend.core.db_v2 import ScreenerV2DB
        latest_run = None
        # Try deps DB first, then default
        for db_path_attempt in [db.db_path, None]:
            try:
                v2db = ScreenerV2DB(db_path=db_path_attempt) if db_path_attempt else ScreenerV2DB()
                latest_run = v2db.get_latest_screener_results()
                v2db.close()
                if latest_run:
                    break
            except Exception:
                pass
        if latest_run:
            all_results = latest_run.get("all_results") or []
            ticker_data = next(
                (s for s in all_results if s.get("symbol", "").upper() == t.upper()),
                None,
            )
            if ticker_data:
                # Use _pick() for all metrics to avoid 0.0 being treated as falsy
                metrics = {
                    "market_cap": _pick(ticker_data, "marketCap", "mktCap"),
                    "pe": _pick(ticker_data, "pe", "priceEarningsRatio"),
                    "revenue_growth": _pick(ticker_data, "revenueGrowth", "revenue_growth"),
                    "earnings_growth": _pick(ticker_data, "earningsGrowth", "earnings_growth"),
                    "gross_margin": _pick(ticker_data, "grossProfitMargin", "gross_margin"),
                    "operating_margin": _pick(ticker_data, "operatingMargin", "operating_margin"),
                    "net_margin": _pick(ticker_data, "netProfitMargin", "net_margin"),
                    "roe": _pick(ticker_data, "returnOnEquity", "roe"),
                    "roic": _pick(ticker_data, "returnOnInvestedCapital", "roic"),
                    "fcf_yield": _pick(ticker_data, "fcfYield", "fcf_yield"),
                    "fcf_conversion": _pick(ticker_data, "fcfConversion", "fcf_conversion"),
                    "income_quality": _pick(ticker_data, "incomeQuality", "income_quality"),
                    "debt_equity": _pick(ticker_data, "debtEquity", "debtToEquity", "debt_equity"),
                    "implied_growth": _pick(ticker_data, "impliedGrowth", "implied_growth"),
                    "expected_return": ticker_data.get("expected_return"),
                    "return_sources": ticker_data.get("return_sources"),
                    "rs_3m": ticker_data.get("rs_3m"),
                    "rs_6m": ticker_data.get("rs_6m"),
                    "rs_3m_percentile": ticker_data.get("rs_3m_percentile"),
                    "rs_6m_percentile": ticker_data.get("rs_6m_percentile"),
                    "price": ticker_data.get("price"),
                    "score": ticker_data.get("score"),
                    "quality_score": _pick(ticker_data, "quality", "quality_score"),
                    "cheapness_score": _pick(ticker_data, "cheapness", "cheapness_score"),
                    "growth_score": _pick(ticker_data, "growth", "growth_score"),
                    "health_score": ticker_data.get("health_score"),
                    "top_lens": ticker_data.get("top_lens"),
                    "vs_sector": ticker_data.get("vs_sector"),
                    "reason": ticker_data.get("reason"),
                    "company_name": _pick(ticker_data, "companyName", "company_name"),
                    "sector": ticker_data.get("sector"),
                    "industry": ticker_data.get("industry"),
                }
    except Exception as e:
        log.warning(f"Failed to fetch screener metrics for {t}: {e}")

    # Fallback: if no screener metrics, try ticker_financials DB (SEC data)
    if not metrics or not metrics.get("gross_margin"):
        try:
            from backend.core.db_v2 import ScreenerV2DB
            from backend.core.financial_data import FinancialData
            v2db_fb = ScreenerV2DB(db_path=db.db_path)
            stored = v2db_fb.get_ticker_financials(t)
            v2db_fb.close()
            if stored and stored.get("financial_data"):
                fd = FinancialData.from_dict(stored["financial_data"])
                flat = fd.to_flat_metrics()
                metrics = {
                    "market_cap": flat.get("market_cap"),
                    "pe": flat.get("pe"),
                    "revenue_growth": flat.get("revenue_growth"),
                    "gross_margin": flat.get("gross_margin"),
                    "operating_margin": flat.get("operating_margin"),
                    "net_margin": flat.get("net_margin"),
                    "roe": flat.get("roe"),
                    "roic": flat.get("roic"),
                    "fcf_yield": flat.get("fcf_yield"),
                    "fcf_conversion": flat.get("fcf_conversion"),
                    "debt_equity": flat.get("debt_equity"),
                    "price": flat.get("price"),
                    "revenue": flat.get("revenue"),
                    "company_name": stored.get("financial_data", {}).get("profile", {}).get("name"),
                    "sector": stored.get("financial_data", {}).get("profile", {}).get("sector"),
                    "industry": stored.get("financial_data", {}).get("profile", {}).get("industry"),
                }
        except Exception as e:
            log.debug(f"Fallback ticker_financials for {t}: {e}")

    # Portfolio position for this ticker
    snapshot = db.get_latest_portfolio_snapshot() or {}
    holdings = snapshot.get("holdings") or []
    if isinstance(holdings, str):
        try:
            holdings = _json.loads(holdings)
        except Exception:
            holdings = []
    position = next((h for h in holdings if isinstance(h, dict) and h.get("ticker") == t), None)

    # Build screener section data from metrics for the Research tab
    screener_section = None
    if metrics:
        score_items = []
        for label, key, fmt in [
            ("Score", "score", lambda v: f"{v:.0f}"),
            ("Quality", "quality_score", lambda v: f"{v:.1f}"),
            ("Cheapness", "cheapness_score", lambda v: f"{v:.1f}"),
            ("Growth", "growth_score", lambda v: f"{v:.1f}"),
            ("Health", "health_score", lambda v: f"{v:.0f}"),
        ]:
            v = metrics.get(key)
            if v is not None:
                score_items.append({"label": label, "value": fmt(v), "color": "var(--text-primary)"})

        screener_section = {
            "narrative": metrics.get("reason") or f"Screened via {metrics.get('top_lens', 'dual')} lens",
            "scores": score_items,
            "top_lens": metrics.get("top_lens"),
            "vs_sector": metrics.get("vs_sector"),
            "return_sources": metrics.get("return_sources"),
        }

    # Build health data: prefer real thesis health from judgment_events, fall back to IC assumptions
    health = {}
    ic_data = ic_review or {}
    thesis_data = thesis or {}

    # Try to load real thesis health from judgment_events
    real_health = None
    health_history = []
    try:
        v2db_health = get_v2db()
        real_health = v2db_health.get_latest_thesis_health(t)
        health_history = v2db_health.get_thesis_health_history(t, limit=10)
        v2db_health.close()
    except Exception as e:
        log.debug(f"Failed to load thesis health for {t}: {e}")

    if real_health and real_health.get("data"):
        # Real health data exists — use it
        health_data = real_health["data"]
        checks = health_data.get("checks", [])
        score = health_data.get("score")
        checked_at = health_data.get("checked_at") or real_health.get("created_at")

        assumptions = []
        _status_scores = {"intact": 100, "at_risk": 50, "breach": 0, "monitoring": 70, "unknown": 50}
        for check in checks:
            assumption_text = check.get("assumption", "")
            status = check.get("status", "unknown")
            a_score = _status_scores.get(status, 50)
            detail_parts = []
            if check.get("metric") and check.get("current_value") is not None:
                detail_parts.append(f"Current {check['metric']}: {check['current_value']}")
            if check.get("threshold") is not None:
                detail_parts.append(f"Threshold: {check['threshold']}")
            if check.get("signal_count") and check["signal_count"] > 0:
                detail_parts.append(f"{check['signal_count']} web signals in 90 days")
            detail = " | ".join(detail_parts) if detail_parts else f"Status: {status}"

            assumptions.append({
                "name": assumption_text,
                "label": assumption_text,
                "status": status,
                "score": a_score,
                "trend": 0,
                "detail": detail,
                "signal_count": check.get("signal_count"),
            })

        # Build quality fundamentals from thesis data
        fundamentals = []
        quality = thesis_data.get("quality") or {}
        for label, key, is_pct in [("Gross Margin", "gross_margin", True), ("ROIC", "roic", True),
                                    ("ROE", "roe", True), ("D/E", "debt_equity", False),
                                    ("FCF Yield", "fcf_yield", True)]:
            val = quality.get(key)
            if val is not None:
                display = f"{val:.1f}%" if is_pct else f"{val:.2f}"
                fundamentals.append({
                    "metric": label,
                    "thesis_target": display,
                    "quarters": [],
                    "trend_icon": "\u2192",
                    "trend_color": "var(--text-muted)",
                })

        thesis_breakers = []
        if ic_data.get("key_risk"):
            risk_text = ic_data["key_risk"]
            thesis_breakers.append({
                "condition": "Key Risk Materializes",
                "name": "Key Risk Materializes",
                "description": risk_text,
                "impact": risk_text,
                "severity": "critical",
                "action": "Review position sizing and stop-loss levels.",
            })

        health = {
            "assumptions": assumptions,
            "fundamentals": fundamentals,
            "thesis_breakers": thesis_breakers,
            "score": score,
            "checked_at": checked_at,
            "history": health_history,
        }

    elif ic_data.get("key_assumptions") or thesis_data.get("quality"):
        # No real health data yet — fall back to IC assumptions with "awaiting check" status
        assumptions = []
        for a in (ic_data.get("key_assumptions") or []):
            text = a if isinstance(a, str) else a.get("assumption", str(a))
            assumptions.append({
                "name": text,
                "label": text,
                "status": "awaiting_check",
                "score": None,
                "trend": 0,
                "detail": "Awaiting first portfolio health check to verify against current data.",
            })

        # Build quality fundamentals
        fundamentals = []
        quality = thesis_data.get("quality") or {}
        for label, key, is_pct in [("Gross Margin", "gross_margin", True), ("ROIC", "roic", True),
                                    ("ROE", "roe", True), ("D/E", "debt_equity", False),
                                    ("FCF Yield", "fcf_yield", True)]:
            val = quality.get(key)
            if val is not None:
                display = f"{val:.1f}%" if is_pct else f"{val:.2f}"
                fundamentals.append({
                    "metric": label,
                    "thesis_target": display,
                    "quarters": [],
                    "trend_icon": "\u2192",
                    "trend_color": "var(--text-muted)",
                })

        thesis_breakers = []
        if ic_data.get("key_risk"):
            risk_text = ic_data["key_risk"]
            thesis_breakers.append({
                "condition": "Key Risk Materializes",
                "name": "Key Risk Materializes",
                "description": risk_text,
                "impact": risk_text,
                "severity": "critical",
                "action": "Review position sizing and stop-loss levels.",
            })

        health = {
            "assumptions": assumptions,
            "fundamentals": fundamentals,
            "thesis_breakers": thesis_breakers,
            "score": None,
            "checked_at": None,
            "history": [],
        }

    # Enrich top-level detail fields from metrics when not available from DB
    company_name = (thesis or {}).get("company_name") or metrics.get("company_name")
    sector = metrics.get("sector")
    industry = metrics.get("industry")

    return {
        "ticker": t,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "pipeline": pipeline,
        "thesis": thesis,
        "ic_review": ic_review,
        "screener": screener_section,
        "health": health,
        "position": position,
        "metrics": metrics,
    }


@router.get("/ticker/{ticker}/health")
async def get_ticker_health(ticker: str):
    """Get comprehensive thesis health for a ticker.

    Returns latest health score, assumption statuses, web signals,
    outcome data, and health history.
    """
    import json as _json
    t = validate_ticker(ticker)

    # Load real thesis health from judgment_events
    v2db = get_v2db()
    latest = v2db.get_latest_thesis_health(t)
    history = v2db.get_thesis_health_history(t, limit=20)

    # Load recent web signals
    web_signals = []
    try:
        signal_events = [
            e for e in v2db.get_events_by_ticker(t, limit=50)
            if e.get("event_type") == "thesis_web_signal"
        ]
        for evt in signal_events[:10]:
            data = evt.get("data", {})
            web_signals.append({
                "assumption": data.get("assumption", ""),
                "signal_direction": data.get("signal_direction", "neutral"),
                "finding": data.get("finding", "")[:200],
                "confidence": data.get("confidence", 0),
                "created_at": evt.get("created_at"),
            })
    except Exception:
        pass

    # Load outcome data
    outcome_data = []
    try:
        outcome_events = [
            e for e in v2db.get_events_by_ticker(t, limit=50)
            if e.get("event_type") == "web_signal_accuracy"
        ]
        for evt in outcome_events[:10]:
            data = evt.get("data", {})
            outcome_data.append({
                "assumption": data.get("assumption", ""),
                "web_predicted": data.get("web_predicted", ""),
                "sec_confirmed": data.get("sec_confirmed", ""),
                "accurate": data.get("accurate", False),
                "created_at": evt.get("created_at"),
            })
    except Exception:
        pass

    v2db.close()

    health_data = {}
    if latest and latest.get("data"):
        data = latest["data"]
        health_data = {
            "score": data.get("score"),
            "checks": data.get("checks", []),
            "checked_at": data.get("checked_at") or latest.get("created_at"),
        }

    return {
        "ticker": t,
        "health": health_data,
        "history": history,
        "web_signals": web_signals,
        "outcome_accuracy": outcome_data,
        "has_data": latest is not None,
    }


@router.get("/ticker/{ticker}/timeline")
async def get_ticker_timeline(ticker: str):
    """Agent run timeline for a ticker."""
    db = get_db()
    # Get all runs for this ticker
    runs = db.get_runs_for_ticker(validate_ticker(ticker))
    return {"ticker": validate_ticker(ticker), "timeline": runs}
