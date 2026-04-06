"""Outcome Checker Agent — Periodic grading of screener results.

Runs daily via orchestrator trigger. Checks screener results at
90/180/365/730/1095 day intervals to measure:
- Thesis integrity: did the fundamentals hold?
- Goal alignment: did returns come through the intended path?
- Alpha: did top-ranked stocks outperform the benchmark?
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backend.agents import AgentPlugin, AgentResult
from backend.core.db_v2 import ScreenerV2DB
from backend.core.prose_spec import OUTCOME_CHECKER_SPEC
from backend.core.prose_validate import clean_prose

log = logging.getLogger("fundops.outcome_checker")

CHECK_INTERVALS = [90, 180, 365, 730, 1095]

# Thesis integrity: metric configs with scoring weights.
# A >20% relative deterioration loses all points for that metric.
# A 10-20% decline loses half.
_INTEGRITY_METRICS = {
    "gross_margin": {
        "original_key": "grossProfitMargin",
        "current_keys": ["grossProfitMargin", "gross_margin"],
        "weight": 25,
        "is_higher_better": True,
    },
    "roic": {
        "original_key": "roic",
        "current_keys": ["roic", "returnOnInvestedCapital"],
        "weight": 25,
        "is_higher_better": True,
    },
    "revenue_growth": {
        "original_key": "revenueGrowth",
        "current_keys": ["revenueGrowth", "revenue_growth"],
        "weight": 25,
        "is_higher_better": True,
    },
    "debt_equity": {
        "original_key": "debtEquity",
        "current_keys": ["debtEquity", "debt_equity", "debtToEquity"],
        "weight": 25,
        "is_higher_better": False,  # lower is better
    },
}


def _parse_datetime(dt_str) -> Optional[datetime]:
    """Parse an ISO datetime string to a datetime object, handling various formats."""
    if not dt_str:
        return None
    if isinstance(dt_str, datetime):
        return dt_str
    try:
        return datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(dt_str), fmt).replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            pass
    return None


def _extract_value(data: dict, keys: list[str]) -> Optional[float]:
    """Try multiple keys to extract a numeric value from a dict."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


def _classify_strategy(constitution: Optional[dict]) -> str:
    """Classify the constitution into a strategy type for alignment checking.

    Returns: "value", "compounder", or "general"
    """
    if not constitution:
        return "general"

    style = (constitution.get("style_identity") or "").lower()
    if style:
        if any(kw in style for kw in ("value", "discount", "margin of safety", "dislocation")):
            return "value"
        if any(kw in style for kw in ("compounder", "growth", "quality")):
            return "compounder"

    north_star = (constitution.get("north_star") or "").lower()
    if north_star:
        if any(kw in north_star for kw in ("undervalued", "discount", "cheap", "value")):
            return "value"
        if any(kw in north_star for kw in ("compound", "grow", "quality")):
            return "compounder"

    dims = constitution.get("dimensions")
    if dims and isinstance(dims, dict):
        dim_str = str(dims).lower()
        if "discount" in dim_str or "margin_of_safety" in dim_str:
            return "value"
        if "compounder" in dim_str or "growth_durability" in dim_str:
            return "compounder"

    return "general"


class OutcomeCheckerAgent(AgentPlugin):
    """Check screener results at periodic intervals."""

    name = "outcome_checker"
    description = "Grade screener results against market reality"

    def __init__(self, config: dict = None, db: ScreenerV2DB = None,
                 yfinance=None, sec=None, fmp=None, web_search=None):
        super().__init__(config)
        self.db = db
        self.yfinance = yfinance
        self.sec = sec
        self.fmp = fmp
        self.web_search = web_search

    async def run(self, context: dict) -> AgentResult:
        """Find due outcome checks and execute them."""
        if not self.db:
            return AgentResult(
                agent=self.name, status="failed",
                errors=["No database configured"]
            )

        due_checks = self.db.get_due_checks(CHECK_INTERVALS)

        if not due_checks:
            return AgentResult(
                agent=self.name, status="complete",
                data={"message": "No outcome checks due", "checked": 0}
            )

        checked = 0
        failed = 0
        results = []

        for check in due_checks:
            run_id = check["run_id"]
            days = check["check_days"]
            top_results = check.get("top_results", [])

            if not top_results:
                continue

            for stock in top_results[:10]:  # Check top 10 per run
                ticker = stock.get("ticker") or stock.get("symbol")
                if not ticker:
                    continue

                try:
                    snapshot = await self._check_ticker(
                        ticker=ticker,
                        run_id=run_id,
                        screened_at=check["run_at"],
                        days_elapsed=days,
                        original_data=stock,
                    )
                    results.append(snapshot)
                    checked += 1

                except Exception as e:
                    log.warning(f"Outcome check failed for {ticker}: {e}")
                    self.db.record_outcome_snapshot(
                        screener_run_id=run_id,
                        ticker=ticker,
                        screened_at=check["run_at"],
                        check_at=datetime.now(timezone.utc).isoformat(),
                        days_elapsed=days,
                        status="error",
                        error_message=str(e),
                    )
                    failed += 1

        return AgentResult(
            agent=self.name,
            status="complete",
            data={
                "checked": checked,
                "failed": failed,
                "results": results,
            },
        )

    async def _check_ticker(self, ticker: str, run_id: str, screened_at: str,
                             days_elapsed: int, original_data: dict) -> dict:
        """Check a single ticker's outcome."""
        now = datetime.now(timezone.utc).isoformat()

        # Get current price (via yfinance if available)
        current_price = None
        if self.yfinance:
            try:
                result = await self.yfinance.get_quotes([ticker])
                if result.ok and result.data:
                    quote = result.data[0] if isinstance(result.data, list) else result.data
                    current_price = quote.get("price") or quote.get("regularMarketPrice")
            except Exception as e:
                log.warning(f"Failed to fetch current price for {ticker}: {e}")

        original_price = original_data.get("price")

        # Calculate return
        return_pct = None
        if current_price and original_price and original_price > 0:
            return_pct = round(
                (current_price - original_price) / original_price * 100, 2
            )

        # --- Gap 1: Benchmark return (SPY) ---
        benchmark_return = await self._fetch_benchmark_return(screened_at, now)

        alpha = None
        if return_pct is not None and benchmark_return is not None:
            alpha = round(return_pct - benchmark_return, 2)

        # --- Gap 2: Thesis integrity check ---
        thesis_integrity = await self._check_thesis_integrity(
            ticker, original_data, days_elapsed
        )

        # --- Gap 3: Goal alignment ---
        goal_alignment = await self._check_goal_alignment(
            ticker=ticker,
            return_pct=return_pct,
            original_data=original_data,
            current_price=current_price,
            original_price=original_price,
            thesis_integrity=thesis_integrity,
        )

        # Narrative web research (optional — only if web_search configured)
        narrative_data = None
        if self.web_search and return_pct is not None:
            company_name = (
                original_data.get("companyName")
                or original_data.get("company_name")
                or original_data.get("name")
                or ticker
            )
            narrative_data = await self._research_outcome_narrative(
                ticker=ticker,
                company_name=company_name,
                screened_at=screened_at,
                check_at=now,
                return_pct=return_pct,
                original_data=original_data,
                financial_data=original_data,
            )

        self.db.record_outcome_snapshot(
            screener_run_id=run_id,
            ticker=ticker,
            screened_at=screened_at,
            check_at=now,
            days_elapsed=days_elapsed,
            price_at_screen=original_price,
            price_at_check=current_price,
            return_pct=return_pct,
            benchmark_return_pct=benchmark_return,
            alpha_pct=alpha,
            thesis_integrity=thesis_integrity,
            goal_alignment=goal_alignment,
        )

        result = {
            "ticker": ticker,
            "days": days_elapsed,
            "return_pct": return_pct,
            "benchmark_return_pct": benchmark_return,
            "alpha_pct": alpha,
            "thesis_integrity": thesis_integrity,
            "goal_alignment": goal_alignment,
        }
        if narrative_data:
            result["narrative"] = narrative_data

        return result

    # ------------------------------------------------------------------
    # Gap 1: Benchmark return (SPY)
    # ------------------------------------------------------------------

    async def _fetch_benchmark_return(self, screened_at: str, check_at: str) -> Optional[float]:
        """Fetch S&P 500 (SPY) return between screened_at and check_at.

        Uses yfinance.download() for historical SPY prices.
        Falls back to None with a warning if data is unavailable.
        """
        if not self.yfinance:
            log.debug("No yfinance connector — skipping benchmark return")
            return None

        try:
            screened_dt = _parse_datetime(screened_at)
            check_dt = _parse_datetime(check_at)

            if not screened_dt or not check_dt:
                log.warning(
                    f"Could not parse dates for benchmark: "
                    f"screened_at={screened_at}, check_at={check_at}"
                )
                return None

            # Buffer for weekends/holidays
            spy_start = screened_dt - timedelta(days=5)
            spy_end = check_dt + timedelta(days=1)

            spy_price_at_screen = await self._get_spy_close(screened_dt, spy_start, spy_end)
            spy_price_at_check = await self._get_spy_close(check_dt, spy_start, spy_end)

            if spy_price_at_screen and spy_price_at_check and spy_price_at_screen > 0:
                benchmark_return = (
                    (spy_price_at_check - spy_price_at_screen) / spy_price_at_screen * 100
                )
                return round(benchmark_return, 2)

            log.warning("Could not compute SPY benchmark — missing price data")
            return None

        except Exception as e:
            log.warning(f"Benchmark return fetch failed: {e}")
            return None

    async def _get_spy_close(self, target_dt: datetime,
                              range_start: datetime,
                              range_end: datetime) -> Optional[float]:
        """Get SPY closing price nearest to target_dt (on or before).

        Downloads the full range and finds the closest trading day.
        """
        try:
            import yfinance as yf

            start_str = range_start.strftime("%Y-%m-%d")
            end_str = range_end.strftime("%Y-%m-%d")

            hist = await asyncio.to_thread(
                lambda: yf.download("SPY", start=start_str, end=end_str, progress=False)
            )

            if hist is None or hist.empty:
                return None

            idx = hist.index
            target_naive = target_dt.replace(tzinfo=None)

            # Find closest date on or before target
            mask = idx <= target_naive
            if not mask.any():
                closest_idx = idx[0]
            else:
                closest_idx = idx[mask][-1]

            # Handle both single-level and multi-level column indexes
            close_col = "Close"
            if close_col not in hist.columns:
                for col in hist.columns:
                    if "close" in str(col).lower():
                        close_col = col
                        break

            price = hist.loc[closest_idx, close_col]
            # yfinance may return a Series for multi-level columns
            if hasattr(price, "item"):
                price = price.item()
            elif hasattr(price, "values"):
                price = float(price.values[0]) if len(price.values) > 0 else float(price)
            return float(price)

        except Exception as e:
            log.warning(f"SPY price fetch at {target_dt} failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Gap 2: Thesis integrity
    # ------------------------------------------------------------------

    async def _check_thesis_integrity(self, ticker: str, original_data: dict,
                                       days_elapsed: int) -> dict:
        """Check if the original screening thesis still holds.

        Compares current fundamentals to screening-time values.
        Score 0-100 where 100 = everything the screener liked is still true.

        Scoring:
        - Start at full weight for each metric
        - >20% relative deterioration: lose all weight
        - 10-20% deterioration: lose half weight
        - Stable or improved: keep full weight
        - Missing current data: half credit (benefit of the doubt)
        """
        checks = {}
        total_weight = 0
        earned_weight = 0

        # Fetch current data from SEC if available
        current_data = {}
        if self.sec:
            current_data = await self._fetch_current_fundamentals(ticker)

        for metric_name, cfg in _INTEGRITY_METRICS.items():
            original_val = original_data.get(cfg["original_key"])
            if original_val is None:
                continue

            weight = cfg["weight"]
            total_weight += weight

            try:
                orig_float = float(original_val)
            except (ValueError, TypeError):
                checks[metric_name] = {
                    "at_screen": original_val,
                    "current": None,
                    "status": "invalid_original",
                }
                continue

            # Display formatting: ratios (<2) shown as pct for GM/ROIC/growth
            is_pct = metric_name in ("gross_margin", "roic", "revenue_growth")
            display_orig = (
                round(orig_float * 100, 1) if is_pct and abs(orig_float) < 2
                else round(orig_float, 2)
            )

            current_val = _extract_value(current_data, cfg["current_keys"])

            if current_val is None:
                checks[metric_name] = {
                    "at_screen": display_orig,
                    "current": None,
                    "status": "no_current_data",
                }
                earned_weight += weight * 0.5  # partial credit
                continue

            display_current = (
                round(current_val * 100, 1) if is_pct and abs(current_val) < 2
                else round(current_val, 2)
            )

            # Calculate relative change
            higher_better = cfg["is_higher_better"]

            if abs(orig_float) < 1e-9:
                # Near-zero original — just compare direction
                if higher_better:
                    rel_change_pct = 0.0 if current_val >= orig_float else -1.0
                else:
                    rel_change_pct = 0.0 if current_val <= orig_float else -1.0
            else:
                if higher_better:
                    rel_change_pct = (current_val - orig_float) / abs(orig_float)
                else:
                    rel_change_pct = (orig_float - current_val) / abs(orig_float)

            # Score
            if rel_change_pct >= 0:
                status = "held"
                earned_weight += weight
            elif rel_change_pct >= -0.10:
                status = "minor_decline"
                earned_weight += weight
            elif rel_change_pct >= -0.20:
                status = "moderate_decline"
                earned_weight += weight * 0.5
            else:
                status = "deteriorated"
                # no weight earned

            checks[metric_name] = {
                "at_screen": display_orig,
                "current": display_current,
                "relative_change_pct": round(rel_change_pct * 100, 1),
                "status": status,
            }

        score = round(earned_weight / total_weight * 100) if total_weight > 0 else None

        return {
            "score": score,
            "checks": checks,
            "total_weight": total_weight,
        }

    async def _fetch_current_fundamentals(self, ticker: str) -> dict:
        """Fetch current fundamental data from SEC connector, with FMP fallback.

        Returns a flat dict with standard keys for metric extraction.
        """
        result = {}

        # Try SEC first (free, authoritative)
        if self.sec:
            try:
                ratios_result = await self.sec.get_ratios(ticker)
                if ratios_result.ok and ratios_result.data:
                    data = ratios_result.data
                    if isinstance(data, dict):
                        if "annual" in data:
                            years = data["annual"]
                            if isinstance(years, list) and years:
                                result.update(years[0])
                            elif isinstance(years, dict):
                                result.update(years)
                        else:
                            result.update(data)
            except Exception as e:
                log.debug(f"SEC ratios failed for {ticker}: {e}")

            # Fallback within SEC: try get_financials
            if not result:
                try:
                    fin_result = await self.sec.get_financials(ticker, years=1)
                    if fin_result.ok and fin_result.data:
                        data = fin_result.data
                        if isinstance(data, dict) and "annual" in data:
                            years = data["annual"]
                            if isinstance(years, list) and years:
                                result.update(years[0])
                except Exception as e:
                    log.debug(f"SEC financials failed for {ticker}: {e}")

        # FMP fallback (paid, but covers more metrics)
        if not result and self.fmp:
            try:
                fmp_result = await self.fmp.get_key_metrics(ticker)
                if fmp_result.ok and fmp_result.data:
                    data = fmp_result.data
                    if isinstance(data, list) and data:
                        result.update(data[0])
                    elif isinstance(data, dict):
                        result.update(data)
            except Exception as e:
                log.debug(f"FMP key metrics failed for {ticker}: {e}")

        return result

    # ------------------------------------------------------------------
    # Gap 3: Goal alignment
    # ------------------------------------------------------------------

    async def _check_goal_alignment(self, ticker: str, return_pct: Optional[float],
                                     original_data: dict, current_price: Optional[float],
                                     original_price: Optional[float],
                                     thesis_integrity: dict) -> dict:
        """Check if the return path matches the stated investment strategy.

        Loads the active constitution and checks strategy-specific alignment:
        - Value: did the discount close?
        - Compounder: did growth metrics maintain?
        - General: is return on track vs expected?

        Statuses:
        - "aligned": return path matches strategy expectations
        - "divergent": positive return from unexpected sources
        - "failed": negative return when positive expected
        """
        if return_pct is None:
            return {
                "assessed": False,
                "status": "no_return_data",
                "note": "Cannot assess alignment without return data",
            }

        # Load constitution for strategy context.
        # Use the constitution version active when the stock was screened,
        # not the current one, so strategy changes don't reinterpret old outcomes.
        constitution = None
        used_fallback_constitution = False
        if self.db:
            try:
                screened_version = (
                    original_data.get("constitution_version")
                    or original_data.get("strategy_version")
                )
                if screened_version is not None:
                    try:
                        screened_version = int(screened_version)
                        constitution = self.db.get_constitution_by_version(screened_version)
                    except (ValueError, TypeError):
                        pass
                if constitution is None:
                    constitution = self.db.get_active_constitution()
                    # If we had a screened_version but couldn't load it, we're using a fallback
                    if screened_version is not None:
                        used_fallback_constitution = True
            except Exception as e:
                log.debug(f"Could not load constitution: {e}")

        expected_return = original_data.get("expected_return") or original_data.get("expectedReturn")
        if expected_return is not None:
            try:
                expected_return = float(expected_return)
            except (ValueError, TypeError):
                expected_return = None

        strategy_type = _classify_strategy(constitution)

        # Case 1: Clear failure — significantly negative return
        if return_pct < -5 and (expected_return is None or expected_return > 0):
            result = {
                "assessed": True,
                "status": "failed",
                "strategy_type": strategy_type,
                "return_pct": round(return_pct, 2),
                "expected_return_pct": expected_return,
                "note": f"Negative return ({return_pct:.1f}%) when positive was expected",
            }
        # Case 2: Strategy-specific alignment
        elif strategy_type == "value":
            result = self._assess_value_alignment(
                return_pct, original_data, current_price, original_price,
                expected_return, thesis_integrity,
            )
        elif strategy_type == "compounder":
            result = self._assess_compounder_alignment(
                return_pct, original_data, expected_return, thesis_integrity,
            )
        else:
            result = self._assess_general_alignment(
                return_pct, expected_return, strategy_type,
            )

        # Annotate if we fell back to the current strategy instead of the one active at screening time
        if used_fallback_constitution and constitution:
            version = constitution.get("version", "?")
            fallback_note = f"Graded against current strategy (v{version}), not the strategy active at screening time"
            existing_note = result.get("note")
            result["note"] = f"{existing_note}; {fallback_note}" if existing_note else fallback_note

        return result

    def _assess_value_alignment(self, return_pct: float, original_data: dict,
                                 current_price: Optional[float],
                                 original_price: Optional[float],
                                 expected_return: Optional[float],
                                 thesis_integrity: dict) -> dict:
        """Value strategy: check if discount closed."""
        fair_value = original_data.get("fairValue") or original_data.get("fair_value")
        discount_closed = None
        note_parts = []

        if fair_value and current_price and original_price:
            try:
                fv = float(fair_value)
                original_discount = (fv - original_price) / fv * 100
                current_discount = (fv - current_price) / fv * 100

                if current_discount < original_discount:
                    discount_closed = True
                    note_parts.append(
                        f"Discount narrowed from {original_discount:.0f}% to {current_discount:.0f}%"
                    )
                else:
                    discount_closed = False
                    note_parts.append(
                        f"Discount widened from {original_discount:.0f}% to {current_discount:.0f}%"
                    )
            except (ValueError, TypeError):
                pass

        if return_pct > 0:
            if discount_closed:
                status = "aligned"
                note_parts.append("Return driven by discount closing (value thesis working)")
            elif discount_closed is False:
                status = "divergent"
                note_parts.append("Positive return but discount did not close")
            else:
                if expected_return and return_pct >= expected_return * 0.7:
                    status = "aligned"
                    note_parts.append(f"On track: {return_pct:.1f}% vs {expected_return:.1f}% expected")
                else:
                    status = "aligned"
                    note_parts.append("Positive return, fair value unavailable for path analysis")
        else:
            status = "failed"
            note_parts.append(f"Negative return ({return_pct:.1f}%)")

        return {
            "assessed": True,
            "status": status,
            "strategy_type": "value",
            "return_pct": round(return_pct, 2),
            "expected_return_pct": expected_return,
            "discount_closed": discount_closed,
            "note": "; ".join(note_parts) if note_parts else None,
        }

    def _assess_compounder_alignment(self, return_pct: float, original_data: dict,
                                      expected_return: Optional[float],
                                      thesis_integrity: dict) -> dict:
        """Compounder strategy: check if growth metrics maintained."""
        integrity_score = thesis_integrity.get("score")
        note_parts = []

        if return_pct > 0:
            if integrity_score is not None and integrity_score >= 70:
                status = "aligned"
                note_parts.append(f"Growth metrics maintained (integrity: {integrity_score}/100)")
            elif integrity_score is not None and integrity_score < 70:
                status = "divergent"
                note_parts.append(
                    f"Positive return but growth metrics deteriorated "
                    f"(integrity: {integrity_score}/100)"
                )
            else:
                if expected_return and return_pct >= expected_return * 0.7:
                    status = "aligned"
                    note_parts.append(f"On track: {return_pct:.1f}% vs {expected_return:.1f}% expected")
                else:
                    status = "aligned"
                    note_parts.append("Positive return, insufficient data for growth path analysis")
        else:
            status = "failed"
            note_parts.append(f"Negative return ({return_pct:.1f}%)")

        return {
            "assessed": True,
            "status": status,
            "strategy_type": "compounder",
            "return_pct": round(return_pct, 2),
            "expected_return_pct": expected_return,
            "thesis_integrity_score": integrity_score,
            "note": "; ".join(note_parts) if note_parts else None,
        }

    def _assess_general_alignment(self, return_pct: float,
                                   expected_return: Optional[float],
                                   strategy_type: str) -> dict:
        """General/unknown strategy: check return vs expected."""
        note_parts = []

        if return_pct > 0:
            if expected_return and return_pct >= expected_return * 0.7:
                status = "aligned"
                note_parts.append(f"On track: {return_pct:.1f}% vs {expected_return:.1f}% expected")
            elif expected_return and return_pct < expected_return * 0.7:
                status = "divergent"
                note_parts.append(
                    f"Underperforming: {return_pct:.1f}% vs {expected_return:.1f}% expected"
                )
            else:
                status = "aligned"
                note_parts.append(f"Positive return ({return_pct:.1f}%), no expected return for comparison")
        else:
            status = "failed"
            note_parts.append(f"Negative return ({return_pct:.1f}%)")

        return {
            "assessed": True,
            "status": status,
            "strategy_type": strategy_type,
            "return_pct": round(return_pct, 2),
            "expected_return_pct": expected_return,
            "note": "; ".join(note_parts) if note_parts else None,
        }

    # ------------------------------------------------------------------
    # Narrative web research (B4 — already wired, kept intact)
    # ------------------------------------------------------------------

    async def _research_outcome_narrative(
        self,
        ticker: str,
        company_name: str,
        screened_at: str,
        check_at: str,
        return_pct: float,
        original_data: dict,
        financial_data: dict,
    ) -> dict:
        """Research WHY a screened stock moved the way it did.

        This feeds Loop 3 learning with qualitative narrative.
        Returns dict with narrative, confidence, thesis_played_out,
        contradictions, and warnings. Returns None on failure.
        """
        try:
            from backend.core.web_grounding import build_fact_anchor, ground_web_research

            fact_anchor = build_fact_anchor(financial_data, ticker, company_name)

            expected_return = original_data.get("expected_return") or original_data.get("expectedReturn")
            expected_str = f" with {expected_return:.1f}% expected return" if expected_return else ""

            direction = "gained" if return_pct >= 0 else "lost"
            abs_return = abs(return_pct)

            query = (
                f"{fact_anchor}\n\n"
                f"We screened {company_name} ({ticker}) on {screened_at}{expected_str}. "
                f"Since then, the stock has {direction} {abs_return:.1f}% "
                f"(checked on {check_at}). "
                f"What drove this return? Focus on:\n"
                f"- Key business developments, earnings surprises, or guidance changes\n"
                f"- Sector or macro catalysts that affected the stock\n"
                f"- Whether the discount closed, margins expanded, or growth accelerated/decelerated\n"
                f"- Any thesis-breaking events (management changes, competitive disruption, etc.)\n"
            )

            search_result = await self.web_search.search(
                query=query,
                context={"ticker": ticker, "agent": "outcome_checker"},
            )

            if search_result.error or not search_result.text:
                log.warning(
                    f"Web search returned no results for {ticker} outcome narrative: "
                    f"{search_result.error}"
                )
                return None

            grounded = ground_web_research(
                raw_text=search_result.text,
                financial_data=financial_data,
                ticker=ticker,
                company_name=company_name,
                fact_anchor=fact_anchor,
            )

            thesis_played_out = self._classify_thesis_outcome(
                return_pct=return_pct,
                narrative_text=grounded.original_text,
                grounded=grounded,
                original_data=original_data,
            )

            # Clean conversational artifacts from web research narrative
            cleaned_narrative = clean_prose(grounded.original_text or "", OUTCOME_CHECKER_SPEC)

            return {
                "narrative": cleaned_narrative,
                "confidence": grounded.confidence,
                "thesis_played_out": thesis_played_out,
                "contradictions": grounded.contradictions,
                "warnings": grounded.warnings,
                "grounded": grounded.grounded,
                "search_cost": search_result.cost,
            }

        except Exception as e:
            log.warning(f"Outcome narrative research failed for {ticker}: {e}")
            return None

    def _classify_thesis_outcome(
        self,
        return_pct: float,
        narrative_text: str,
        grounded: Any,
        original_data: dict,
    ) -> bool | None:
        """Classify whether the screening thesis played out.

        Returns:
            True:  positive return and narrative confirms thesis drivers
            False: negative return or thesis broke (key assumptions violated)
            None:  insufficient evidence to determine
        """
        if not narrative_text:
            return None

        text_lower = narrative_text.lower()

        positive_signals = [
            "discount closed", "discount narrowed", "valuation re-rated",
            "multiple expanded", "multiple expansion",
            "margin expansion", "margins improved", "margins expanded",
            "growth accelerated", "growth exceeded", "beat expectations",
            "earnings beat", "revenue beat", "strong results",
            "upgraded", "analyst upgrade", "price target raised",
        ]

        negative_signals = [
            "margin compression", "margins declined", "margins contracted",
            "growth decelerated", "growth slowed", "missed expectations",
            "earnings miss", "revenue miss", "guidance cut",
            "downgraded", "analyst downgrade", "price target cut",
            "management departure", "ceo departed", "ceo resigned",
            "competitive pressure", "market share loss",
            "accounting issue", "restatement", "sec investigation",
            "debt covenant", "liquidity concern",
        ]

        pos_count = sum(1 for s in positive_signals if s in text_lower)
        neg_count = sum(1 for s in negative_signals if s in text_lower)

        has_contradictions = bool(
            hasattr(grounded, "contradictions") and grounded.contradictions
        )

        if return_pct > 5.0 and pos_count >= 2 and neg_count == 0:
            return True
        elif return_pct < -5.0 and neg_count >= 2:
            return False
        elif return_pct < -10.0 and pos_count == 0:
            return False
        elif return_pct > 10.0 and neg_count == 0 and pos_count >= 1:
            return True
        elif has_contradictions and neg_count > pos_count:
            return False

        return None
