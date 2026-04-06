"""Review routes — aggregated data for side-by-side review.

Combines fact sheet, thesis, IC verdict, evidence artifacts, data quality,
and risk check into one response for the TickerDetail review view.
"""

import json
import logging

from fastapi import APIRouter

from backend.api.deps import get_db

log = logging.getLogger("fundops.api.review")

router = APIRouter()


@router.get("/review/{ticker}")
async def get_review_data(ticker: str):
    """Aggregate all review data for a ticker."""
    db = get_db()

    result = {
        "ticker": ticker,
        "fact_sheet": {},
        "thesis": {},
        "ic_review": {},
        "evidence_artifacts": [],
        "data_quality": {},
    }

    # Latest thesis
    try:
        thesis_run = db.get_latest_run(ticker, "thesis")
        if thesis_run and thesis_run.get("full_output"):
            output = thesis_run["full_output"]
            if isinstance(output, str):
                output = json.loads(output)
            result["thesis"] = output
            result["fact_sheet"] = {
                "price": output.get("price"),
                "fair_value": output.get("fair_value"),
                "discount_pct": output.get("discount_pct"),
                "expected_return": output.get("expected_return"),
                "quality": output.get("quality", {}),
                "return_sources": output.get("return_sources", {}),
                "valuation": output.get("valuation", {}),
                "data_freshness": output.get("data_freshness", {}),
                "data_warnings": output.get("data_warnings", []),
            }
    except Exception as e:
        log.debug(f"Failed to load thesis for {ticker}: {e}")

    # Latest IC review
    try:
        ic_run = db.get_latest_run(ticker, "ic_review")
        if ic_run and ic_run.get("full_output"):
            output = ic_run["full_output"]
            if isinstance(output, str):
                output = json.loads(output)
            result["ic_review"] = output
    except Exception as e:
        log.debug(f"Failed to load IC review for {ticker}: {e}")

    # Evidence artifacts — query from the same DB connection
    try:
        rows = db.conn.execute(
            "SELECT * FROM evidence_artifacts WHERE ticker = ? ORDER BY captured_at DESC LIMIT 20",
            (ticker,),
        ).fetchall()
        if rows:
            cols = [d[0] for d in db.conn.execute("SELECT * FROM evidence_artifacts LIMIT 0").description]
            result["evidence_artifacts"] = [dict(zip(cols, row)) for row in rows]
    except Exception as e:
        log.debug(f"Failed to load evidence for {ticker}: {e}")

    # Data quality — pass the full thesis output so audit can find nested metrics
    if result["thesis"] or result["fact_sheet"]:
        try:
            from backend.core.data_quality import audit_data_quality
            # Merge fact_sheet + thesis so audit can find metrics in quality/valuation dicts
            audit_input = {**result.get("thesis", {}), **result.get("fact_sheet", {})}
            result["data_quality"] = audit_data_quality(audit_input, ticker=ticker)
        except Exception as e:
            log.debug(f"Data quality check failed: {e}")

    return result


@router.get("/evidence/{ticker}")
async def get_evidence(ticker: str):
    """Get evidence artifacts for a ticker."""
    db = get_db()
    try:
        rows = db.conn.execute(
            "SELECT * FROM evidence_artifacts WHERE ticker = ? ORDER BY captured_at DESC",
            (ticker,),
        ).fetchall()
        if rows:
            cols = [d[0] for d in db.conn.execute("SELECT * FROM evidence_artifacts LIMIT 0").description]
            return {"ticker": ticker, "artifacts": [dict(zip(cols, row)) for row in rows]}
        return {"ticker": ticker, "artifacts": []}
    except Exception as e:
        return {"ticker": ticker, "artifacts": [], "error": str(e)}
