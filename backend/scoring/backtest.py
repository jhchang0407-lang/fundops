"""Closed-loop validation: backtest scoring code against historical outcomes.

Re-scores past screener universes with new scoring code and compares
the new top picks against actual outcome data (return, alpha).

Requires outcome_snapshots data to exist (from the outcome checker agent).
"""

import json
import logging
import sqlite3
from typing import Any

from backend.scoring.sandbox import (
    compile_scoring_function,
    execute_scoring,
    execute_scoring_subprocess,
    validate_ast,
    ScoringCodeError,
)

log = logging.getLogger("fundops.scoring.backtest")


def backtest_scoring_code(
    db_path: str,
    scoring_code: str,
    lookback_days: int = 365,
    top_k: int = 10,
    use_subprocess: bool = False,
) -> dict:
    """Backtest scoring code against historical screener runs with outcomes.

    Args:
        db_path: Path to the SQLite database
        scoring_code: Python scoring code to test (must define score())
        lookback_days: How far back to look for screener runs
        top_k: How many top picks to evaluate per run
        use_subprocess: Use subprocess sandbox (safer but slower)

    Returns:
        {
            "hit_rate": float,        # % of top picks that beat benchmark
            "avg_alpha": float,       # average alpha vs benchmark
            "sample_size": int,       # total stocks evaluated
            "runs_tested": int,       # number of screener runs tested
            "details": list[dict],    # per-stock results
            "warning": str | None,
        }
    """
    # Validate code first
    errors = validate_ast(scoring_code)
    if errors:
        raise ScoringCodeError(f"Code validation failed: {'; '.join(errors)}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Find screener runs with outcome data
        runs = conn.execute("""
            SELECT DISTINCT sr.id as run_id, sr.run_at, sr.all_results
            FROM screener_runs sr
            JOIN outcome_snapshots os ON os.screener_run_id = sr.id
            WHERE sr.all_results IS NOT NULL
              AND sr.run_at >= datetime('now', ?)
              AND os.return_pct IS NOT NULL
            ORDER BY sr.run_at DESC
            LIMIT 20
        """, (f"-{lookback_days} days",)).fetchall()

        if not runs:
            return {
                "hit_rate": 0,
                "avg_alpha": 0,
                "sample_size": 0,
                "runs_tested": 0,
                "details": [],
                "warning": "No screener runs with outcome data found",
            }

        # Compile scoring function
        if use_subprocess:
            score_fn = None  # Will use subprocess per batch
        else:
            score_fn = compile_scoring_function(scoring_code)

        all_details = []
        hits = 0
        total = 0
        alpha_sum = 0.0

        for run in runs:
            run_id = run["run_id"]

            # Load the universe that was scored
            try:
                universe = json.loads(run["all_results"])
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(universe, list) or not universe:
                continue

            # Re-score with new code
            if use_subprocess:
                scored = execute_scoring_subprocess(scoring_code, universe)
            else:
                scored = execute_scoring(score_fn, universe)

            if scored["status"] == "error":
                continue

            # Get top-K by new scoring
            top_picks = scored["results"][:top_k]
            top_tickers = {r.get("ticker", "") for r in top_picks}

            # Look up outcomes for these tickers
            outcomes = conn.execute("""
                SELECT ticker, return_pct, benchmark_return_pct, alpha_pct
                FROM outcome_snapshots
                WHERE screener_run_id = ?
                  AND ticker IN ({})
                  AND return_pct IS NOT NULL
            """.format(",".join("?" * len(top_tickers))),
                (run_id, *top_tickers),
            ).fetchall()

            for outcome in outcomes:
                ticker = outcome["ticker"]
                ret = outcome["return_pct"] or 0
                bench = outcome["benchmark_return_pct"] or 0
                alpha = outcome["alpha_pct"] or (ret - bench)

                beat_benchmark = ret > bench
                if beat_benchmark:
                    hits += 1
                total += 1
                alpha_sum += alpha

                all_details.append({
                    "ticker": ticker,
                    "run_id": run_id,
                    "return_pct": round(ret, 2),
                    "benchmark_pct": round(bench, 2),
                    "alpha_pct": round(alpha, 2),
                    "beat_benchmark": beat_benchmark,
                })

        hit_rate = (hits / total * 100) if total > 0 else 0
        avg_alpha = (alpha_sum / total) if total > 0 else 0

        warning = None
        if total < 10:
            warning = f"Small sample size ({total} stocks). Results may not be reliable."
        elif hit_rate < 40:
            warning = f"Hit rate {hit_rate:.0f}% is below 40% — this scoring logic underperforms random selection."

        return {
            "hit_rate": round(hit_rate, 1),
            "avg_alpha": round(avg_alpha, 2),
            "sample_size": total,
            "runs_tested": len(runs),
            "details": all_details,
            "warning": warning,
        }

    finally:
        conn.close()
