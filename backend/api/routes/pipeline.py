"""Pipeline routes — one-click full pipeline execution.

Full pipeline (8 steps):
  1. Screener (discovery)
  2. Thesis (top 20 candidates)
  3. IC Review (quality gate)
  4. Memo (PASS only)
  5. Library (archive)
  6. Portfolio (health check on held positions)
  7. Allocator (sizing + sell discipline)
  8. Learning loops (feedback patterns, drift analysis, outcome checker)
"""

import logging
from pathlib import Path

from fastapi import APIRouter

from backend.api.deps import (
    get_db, get_job_queue, get_config, get_fmp, get_yfinance, get_sec,
    get_llm, get_web_search, get_library, get_v2db, get_outcome_checker,
)
from backend.agents.screener import ScreenerAgent
from backend.agents.thesis import ThesisAgent
from backend.agents.ic_review import ICReviewAgent
from backend.agents.memo import MemoAgent
from backend.agents.library import LibraryAgent
from backend.agents.portfolio import PortfolioAgent
from backend.agents.allocator import AllocatorAgent
from backend.core.db_v2 import ScreenerV2DB
from backend.scoring.sandbox import compile_scoring_function, execute_scoring, ScoringCodeError

log = logging.getLogger("fundops.pipeline")

# In-memory cache for compiled scoring functions (same pattern as strategy.py)
_pipeline_scoring_cache: dict[str, object] = {}

router = APIRouter()


def _get_active_constitution(config) -> dict | None:
    """Load the active constitution from DB. Returns None if none saved."""
    try:
        db_path = config.resolved.get("db_path", str(Path.home() / ".fundops" / "fundops.db"))
        v2db = ScreenerV2DB(db_path=db_path)
        constitution = v2db.get_active_constitution()
        v2db.close()
        return constitution
    except Exception:
        return None


def _build_screener_config(base_config: dict, constitution: dict | None) -> dict:
    """Merge constitution settings over the base workflow.yaml screener config."""
    cfg = dict(base_config)
    if not constitution:
        return cfg

    # Override universe from constitution
    universe_type = constitution.get("universe_type", "preset")
    if universe_type == "custom" and constitution.get("universe_custom"):
        cfg["universe_type"] = "custom"
        cfg["universe_custom"] = constitution["universe_custom"]
    elif constitution.get("universe_name"):
        cfg["universe"] = constitution["universe_name"]

    # Override scoring weights from agent_profiles.screener
    agent_profiles = constitution.get("agent_profiles") or {}
    screener_profile = agent_profiles.get("screener") or {}
    if screener_profile.get("weights"):
        cfg["scoring_weights"] = screener_profile["weights"]
    if screener_profile.get("filters"):
        cfg["constitution_filters"] = screener_profile["filters"]

    return cfg


def _build_ic_config(base_config: dict, constitution: dict | None) -> dict:
    """Merge constitution IC hurdles over base config."""
    cfg = dict(base_config)
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


@router.post("/pipeline/run")
async def run_pipeline():
    """One-click pipeline: Screener → Thesis → IC Review → Memo → Library → Portfolio → Allocator → Learning.
    All agents use the active constitution for universe, weights, and hurdles.
    Steps 6-8 (portfolio, allocator, learning) are non-blocking — failures don't stop the pipeline.
    """
    config = get_config()
    jobs = get_job_queue()

    async def pipeline_fn(ctx):
        progress = ctx.get("_update_progress", lambda msg: None)

        # Load active constitution — this is the source of truth for universe + hurdles
        constitution = _get_active_constitution(config)

        # Step 1: Run screener with constitution-aware config
        base_scout_cfg = config.resolved.get("agents", {}).get("screener", {}).get("config", {})
        screener_config = _build_screener_config(base_scout_cfg, constitution)
        universe_name = screener_config.get("universe", "us_largecap_200")
        universe_label = constitution.get("universe_name", universe_name) if constitution else universe_name
        progress(f"Step 1/5: Running screener ({universe_label})...")

        # Check if AI-generated scoring code is available
        ai_score_fn = None
        version_id = constitution.get("active_version_id") if constitution else None
        if version_id:
            if version_id in _pipeline_scoring_cache:
                ai_score_fn = _pipeline_scoring_cache[version_id]
            else:
                try:
                    v2db_score = get_v2db()
                    version = v2db_score.get_version(version_id)
                    v2db_score.close()
                    if version and version.get("scoring_code"):
                        ai_score_fn = compile_scoring_function(version["scoring_code"])
                        _pipeline_scoring_cache[version_id] = ai_score_fn
                        log.info(f"Pipeline: loaded AI scoring code version {version_id}")
                except (ScoringCodeError, Exception) as e:
                    log.warning(f"Pipeline: AI scoring code failed to load ({e}), using dual-lens fallback")

        screener = ScreenerAgent(
            config=screener_config,
            fmp=get_fmp(), yfinance=get_yfinance(), sec=get_sec(), db=get_db(),
        )
        screener_result = await screener.run({"constitution": constitution})

        # Check if screener actually produced data — fail loudly if not
        if screener_result.status == "failed" or not screener_result.data:
            error_msg = "; ".join(screener_result.errors) if screener_result.errors else "Screener returned no data"
            # Check for common causes
            scored = screener_result.data.get("all_scored", []) if screener_result.data else []
            if not scored:
                error_msg += ". This usually means the data source (yfinance) is rate-limited or unavailable. Try again in a few minutes."
            progress(f"FAILED: {error_msg}")
            log.error(f"Pipeline failed at Step 1 (Screener): {error_msg}")
            raise RuntimeError(f"Screener failed: {error_msg}")

        # If AI scoring code is available, re-score all stocks with it
        if ai_score_fn:
            all_stocks = screener_result.data.get("all_scored", [])
            if not all_stocks:
                all_stocks = screener_result.data.get("handoff_candidates", [])
            if all_stocks:
                progress(f"Step 1/5: AI scoring {len(all_stocks)} stocks...")
                scoring_result = execute_scoring(ai_score_fn, all_stocks)
                # Sort by AI score and take top 20 as handoff
                ai_scored = sorted(scoring_result["results"], key=lambda s: s.get("score", 0), reverse=True)
                handoff = ai_scored[:20]
                log.info(f"Pipeline: AI scoring produced {len(ai_scored)} scored, top 20 as handoff")
                progress(f"Step 1/5: AI screener done, {len(handoff)} candidates (from {len(ai_scored)} scored)")

                # Save AI-scored results to screener_runs so frontend picks them up
                try:
                    v2db_save = get_v2db()
                    saved_id = v2db_save.record_screener_run(
                        strategy_version_id=version_id,
                        universe_size=screener_result.data.get("universe_size", len(all_stocks)),
                        scored_count=scoring_result["scored_count"],
                        failed_count=scoring_result["failed_count"],
                        top_results=handoff,
                        all_results=ai_scored,
                    )
                    v2db_save.close()
                    log.info(f"Pipeline: saved AI results to screener_runs (id={saved_id})")
                except Exception as e:
                    log.warning(f"Pipeline: failed to save AI results to screener_runs: {e}")
            else:
                handoff = []
        else:
            handoff = screener_result.data.get("handoff_candidates", [])
            # Save basic screener results to screener_runs too, so the Screener page
            # always finds results via /screener/v2/results (not just /screener/results)
            all_scored = screener_result.data.get("all_scored", handoff)
            if all_scored:
                try:
                    v2db_basic = get_v2db()
                    saved_id = v2db_basic.record_screener_run(
                        strategy_version_id=version_id,
                        universe_size=screener_result.data.get("universe_size", len(all_scored)),
                        scored_count=len(all_scored),
                        failed_count=0,
                        top_results=handoff,
                        all_results=all_scored,
                    )
                    v2db_basic.close()
                    log.info(f"Pipeline: saved basic screener results to screener_runs (id={saved_id})")
                except Exception as e:
                    log.warning(f"Pipeline: failed to save basic results to screener_runs: {e}")

        if not handoff:
            progress("Done: no candidates found")
            return screener_result

        progress(f"Step 1/5: Screener done, {len(handoff)} candidates")

        # Step 2: Run thesis for top 20 handoff candidates
        thesis_agent = ThesisAgent(
            config=config.resolved.get("agents", {}).get("val", {}).get("config", {}),
            fmp=get_fmp(), sec=get_sec(), yfinance=get_yfinance(),
            llm=get_llm(), web_search=get_web_search(), db=get_db(),
            library=get_library(),
        )

        thesis_results = []
        top_n = handoff[:20]
        for i, candidate in enumerate(top_n):
            ticker = candidate.get("symbol") or candidate.get("ticker", "")
            if ticker:
                progress(f"Step 2/5: Thesis {i+1}/{len(top_n)} ({ticker})")
                try:
                    result = await thesis_agent.run({"ticker": ticker, "constitution": constitution})
                    thesis_results.append(result.data)
                except Exception as e:
                    log.warning(f"Thesis failed for {ticker}: {e}")
                    thesis_results.append({"ticker": ticker, "error": str(e)})

        progress(f"Step 2/5: {len(thesis_results)} theses done")

        # Step 3: Rank theses by expected return, send top 10 to IC review
        base_judge_cfg = config.resolved.get("agents", {}).get("ic_review", {}).get("config", {})
        ic_config = _build_ic_config(base_judge_cfg, constitution)
        ic_agent = ICReviewAgent(
            config=ic_config,
            llm=get_llm(), db=get_db(),
            library=get_library(),
        )

        valid_theses = [t for t in thesis_results if t.get("ticker") and not t.get("error")]
        # Rank by expected return descending — only send the best opportunities to IC
        valid_theses.sort(
            key=lambda t: float(t.get("expected_return") or 0),
            reverse=True,
        )
        ic_candidates = valid_theses[:10]
        top_returns = [f"{t.get('ticker')}={t.get('expected_return', 0)}%" for t in ic_candidates[:5]]
        log.info(
            f"Pipeline: {len(valid_theses)} valid theses -> top {len(ic_candidates)} sent to IC review "
            f"(returns: {top_returns})"
        )
        progress(f"Step 3/5: Top {len(ic_candidates)} theses (by return) → IC review")

        ic_results = []
        for i, thesis in enumerate(ic_candidates):
            progress(f"Step 3/5: IC Review {i+1}/{len(ic_candidates)} ({thesis['ticker']})")
            try:
                result = await ic_agent.run({**thesis, "constitution": constitution})
                ic_results.append(result.data)
            except Exception as e:
                log.warning(f"IC Review failed for {thesis['ticker']}: {e}")
                ic_results.append({"ticker": thesis["ticker"], "error": str(e)})

        passed = [r for r in ic_results if r.get("verdict") == "PASS"]
        progress(f"Step 3/5: {len(passed)} passed IC review")

        # Step 4: Generate investment memos for IC-passed tickers
        memo_agent = MemoAgent(
            config=config.resolved.get("agents", {}).get("memo", {}).get("config", {}),
            fmp=get_fmp(), sec=get_sec(), yfinance=get_yfinance(),
            llm=get_llm(), web_search=get_web_search(), db=get_db(),
        )

        memo_results = []
        for i, ic_result in enumerate(passed):
            ticker = ic_result.get("ticker", "")
            if ticker:
                progress(f"Step 4/5: Memo {i+1}/{len(passed)} ({ticker})")
                try:
                    thesis_for_ticker = next(
                        (t for t in thesis_results if t.get("ticker") == ticker), {}
                    )
                    memo_result = await memo_agent.run({
                        "ticker": ticker,
                        "mode": "both",
                        "thesis": thesis_for_ticker,
                        "ic_verdict": ic_result,
                        "constitution": constitution,
                    })
                    memo_results.append(memo_result.data)
                except Exception as e:
                    log.warning(f"Memo generation failed for {ticker}: {e}")
                    memo_results.append({"ticker": ticker, "error": str(e)})

        memos_ok = len([m for m in memo_results if not m.get("error")])
        progress(f"Step 4/5: {memos_ok} memos generated")

        # Step 5: Ingest all results into library
        progress("Step 5/5: Archiving to library...")
        library_ingested = False
        try:
            db_path = config.resolved.get("db_path", str(Path.home() / ".fundops" / "fundops.db"))
            v2db = ScreenerV2DB(db_path=db_path)
            library_agent = LibraryAgent(db=get_db(), v2db=v2db)
            await library_agent.run({"constitution": constitution})
            v2db.close()
            library_ingested = True
        except Exception as e:
            log.warning(f"Library ingest failed: {e}")

        progress(f"Step 5/8: Library {'ok' if library_ingested else 'failed'}")

        # Step 6: Portfolio monitor (P&L, thesis health for held positions)
        portfolio_data = None
        try:
            progress("Step 6/8: Portfolio health check...")
            portfolio_agent = PortfolioAgent(
                config=config.resolved.get("agents", {}).get("portfolio", {}).get("config", {}),
                fmp=get_fmp(), yfinance=get_yfinance(), db=get_db(),
            )
            portfolio_result = await portfolio_agent.run({"constitution": constitution})
            portfolio_data = portfolio_result.data
            alerts_count = len(portfolio_data.get("alerts", []))
            progress(f"Step 6/8: Portfolio done, {alerts_count} alerts")
        except Exception as e:
            log.warning(f"Portfolio health check failed (non-blocking): {e}")
            progress("Step 6/8: Portfolio check skipped")

        # Step 7: Allocator recommendations (sizing, sell discipline)
        allocator_data = None
        if portfolio_data:
            try:
                progress("Step 7/8: Allocator recommendations...")
                allocator_agent = AllocatorAgent(
                    config=config.resolved.get("agents", {}).get("allocator", {}).get("config", {}),
                    db=get_db(),
                )
                allocator_result = await allocator_agent.run({
                    "holdings": portfolio_data.get("holdings", []),
                    "alerts": portfolio_data.get("alerts", []),
                    "constitution": constitution,
                })
                allocator_data = allocator_result.data
                actions_count = len(allocator_data.get("actions", []))
                progress(f"Step 7/8: Allocator done, {actions_count} actions")
            except Exception as e:
                log.warning(f"Allocator failed (non-blocking): {e}")
                progress("Step 7/8: Allocator skipped")
        else:
            progress("Step 7/8: Allocator skipped (no portfolio data)")

        # Step 8: Learning loops (pattern detection, drift analysis, outcome check)
        learning_summary = {}
        try:
            progress("Step 8/8: Running learning loops...")
            from backend.learning.feedback_loop import detect_patterns
            from backend.learning.behavioral import analyze_drift

            v2db_learn = get_v2db()
            try:
                # Loop 1: Feedback pattern detection
                patterns = await detect_patterns(v2db_learn)
                learning_summary["patterns_detected"] = len(patterns) if patterns else 0

                # Loop 2: Behavioral drift analysis
                if constitution:
                    drift = await analyze_drift(v2db_learn, constitution)
                    has_drift = bool(drift and (drift.get("signal_drift") or drift.get("anti_signal_violations")))
                    learning_summary["drift_detected"] = has_drift

                # Loop 3: Outcome checker for held positions
                try:
                    outcome_agent = get_outcome_checker()
                    outcome_result = await outcome_agent.run({"constitution": constitution})
                    learning_summary["outcomes_checked"] = len(outcome_result.data.get("checked", [])) if outcome_result.data else 0
                except Exception as oe:
                    log.warning(f"Outcome checker failed: {oe}")
                    learning_summary["outcomes_checked"] = 0
            finally:
                v2db_learn.close()

            progress(f"Step 8/8: Learning done — {learning_summary}")
        except Exception as e:
            log.warning(f"Learning loops failed (non-blocking): {e}")
            progress("Step 8/8: Learning loops skipped")

        progress(f"Done: {len(passed)} passed, {memos_ok} memos, pipeline complete")

        return type("Result", (), {
            "data": {
                "screened": screener_result.data.get("universe_size", 0),
                "handoff": len(handoff),
                "theses": len(thesis_results),
                "ic_reviewed": len(ic_results),
                "passed": len(passed),
                "passed_tickers": [r["ticker"] for r in passed],
                "memos_generated": memos_ok,
                "library_ingested": library_ingested,
                "portfolio_alerts": len(portfolio_data.get("alerts", [])) if portfolio_data else 0,
                "allocator_actions": len(allocator_data.get("actions", [])) if allocator_data else 0,
                "learning": learning_summary,
                "results": ic_results,
                "constitution_used": constitution.get("id") if constitution else None,
                "universe_used": universe_label,
            }
        })()

    job_id = await jobs.submit("pipeline", pipeline_fn, {})
    return {"job_id": job_id, "status": "running"}


@router.get("/pipeline/status")
async def get_pipeline_status():
    """Get current pipeline state."""
    jobs = get_job_queue()
    pipeline_jobs = jobs.list_jobs(agent="pipeline")
    return {"jobs": pipeline_jobs[:5]}


@router.get("/pipeline/history")
async def get_pipeline_history():
    """Pipeline run history."""
    db = get_db()
    runs = db.get_latest_runs("pipeline", limit=10)
    return {"history": runs}


# ---------------------------------------------------------------------------
# Pipeline approval gates (Phase 5)
# ---------------------------------------------------------------------------

@router.get("/pipeline/pending")
async def list_pending_approvals():
    """List pending approval requests (paused pipeline steps)."""
    db = get_db()
    try:
        rows = db.conn.execute(
            "SELECT * FROM pending_approvals WHERE status = 'pending' ORDER BY created_at DESC"
        ).fetchall()
        cols = [d[0] for d in db.conn.execute("SELECT * FROM pending_approvals LIMIT 0").description]
        return {"pending": [dict(zip(cols, row)) for row in rows]}
    except Exception as e:
        return {"pending": [], "error": str(e)}


@router.post("/pipeline/pending/{approval_id}/approve")
async def approve_pending(approval_id: int):
    """Approve a pending pipeline step, allowing the next agent to run."""
    import json
    import sqlite3
    from datetime import datetime, timezone

    db = get_db()

    try:
        row = db.conn.execute(
            "SELECT * FROM pending_approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        if not row:
            return {"error": "Approval not found"}

        cols = [d[0] for d in db.conn.execute("SELECT * FROM pending_approvals LIMIT 0").description]
        approval = dict(zip(cols, row))

        if approval["status"] != "pending":
            return {"error": f"Approval already {approval['status']}"}

        db.conn.execute(
            "UPDATE pending_approvals SET status = 'approved', decided_by = 'user', decided_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), approval_id),
        )
        db.conn.commit()

        ticker = approval["ticker"]
        next_agent = approval["next_agent"]
        decision_data = json.loads(approval["decision_data"]) if approval["decision_data"] else {}

        log.info(f"Approval granted for {ticker}: proceeding to {next_agent}")

        config = get_config()
        jobs = get_job_queue()
        llm = get_llm()
        constitution = _get_active_constitution(config)

        if next_agent == "memo":
            agent = MemoAgent(
                config=config.get_agent_config("memo"),
                db=db, llm=llm,
            )
            context = {
                "ticker": ticker,
                "thesis": decision_data,
                "constitution": constitution,
            }

            async def run_approved():
                return await agent.run(context)

            job_id = await jobs.submit(f"memo-{ticker}", run_approved)
            return {"status": "approved", "job_id": job_id, "next_agent": next_agent}

        return {"status": "approved", "message": f"Approved {ticker} for {next_agent}"}

    except Exception as e:
        return {"error": str(e)}


@router.post("/pipeline/pending/{approval_id}/reject")
async def reject_pending(approval_id: int, reason: str = ""):
    """Reject a pending pipeline step."""
    from datetime import datetime, timezone

    db = get_db()
    try:
        db.conn.execute(
            "UPDATE pending_approvals SET status = 'rejected', decided_by = 'user', decided_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), approval_id),
        )
        db.conn.commit()
        return {"status": "rejected", "approval_id": approval_id}
    except Exception as e:
        return {"error": str(e)}
