"""Portfolio Agent — Monitor held positions.

Tracks P&L, thesis health, concentration alerts, and drawdown alerts
for HELD positions only. Does NOT track non-held names.

Emits event_type="alert" if any alerts are triggered, otherwise "complete".
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime

from backend.agents import AgentPlugin, AgentResult
from backend.core.utils import safe_float
from backend.core.web_grounding import build_fact_anchor, ground_web_research

log = logging.getLogger("fundops.portfolio")

# ---------------------------------------------------------------------------
# Assumption parsing — maps natural-language assumptions to SEC ratio keys
# ---------------------------------------------------------------------------

# Map of keyword fragments (lowercase) to SEC ratio dict keys (camelCase)
_ASSUMPTION_METRIC_MAP = {
    "revenue growth": "revenueGrowth",
    "gross margin": "grossProfitMargin",
    "operating margin": "operatingProfitMargin",
    "net margin": "netProfitMargin",
    "ebitda margin": "ebitdaMargin",
    "roic": "returnOnInvestedCapital",
    "return on invested capital": "returnOnInvestedCapital",
    "roe": "returnOnEquity",
    "return on equity": "returnOnEquity",
    "roa": "returnOnAssets",
    "return on assets": "returnOnAssets",
    "fcf margin": "freeCashFlowMargin",
    "free cash flow margin": "freeCashFlowMargin",
    "debt to equity": "debtToEquity",
    "debt/equity": "debtToEquity",
    "current ratio": "currentRatio",
    "interest coverage": "interestCoverage",
}

# SEC ratios that are stored as decimals (0.60 = 60%)
_DECIMAL_RATIO_KEYS = {
    "revenueGrowth", "grossProfitMargin", "operatingProfitMargin",
    "netProfitMargin", "ebitdaMargin", "freeCashFlowMargin",
    "returnOnInvestedCapital", "returnOnEquity", "returnOnAssets",
}


def _parse_assumption(assumption: str) -> tuple[str | None, float | None, str]:
    """Parse a key assumption string into (metric_key, threshold, direction).

    Examples:
        "Revenue growth sustains above 15%"  -> ("revenueGrowth", 0.15, "above")
        "Gross margin holds above 60%"       -> ("grossProfitMargin", 0.60, "above")
        "Debt to equity stays below 1.5"     -> ("debtToEquity", 1.5, "below")
        "Multiple re-rates toward fair value" -> (None, None, "")

    Returns:
        (sec_ratio_key, threshold_as_decimal_or_raw, direction)
        If parsing fails, all values are None/"".
    """
    if not isinstance(assumption, str):
        return None, None, ""
    text = assumption.lower()

    # Find the metric
    metric_key = None
    for fragment, sec_key in _ASSUMPTION_METRIC_MAP.items():
        if fragment in text:
            metric_key = sec_key
            break

    if metric_key is None:
        return None, None, ""

    # Find direction: "above" or "below"
    if any(w in text for w in ("above", "exceeds", "greater")):
        direction = "above"
    elif any(w in text for w in ("below", "under", "less")):
        direction = "below"
    else:
        direction = "above"  # default: assumption is a floor

    # Extract numeric threshold (handle ranges like "10-15%")
    range_match = re.search(r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)\s*%?', text)
    if range_match:
        low_val = float(range_match.group(1))
        high_val = float(range_match.group(2))
        # For "above" direction, use lower bound (conservative)
        # For "below" direction, use upper bound (conservative)
        threshold = low_val if direction == "above" else high_val
    else:
        match = re.search(r'(\d+\.?\d*)\s*%?', text)
        if not match:
            return metric_key, None, direction
        threshold = float(match.group(1))

    # Convert percentage thresholds to decimals for margin/growth metrics
    if metric_key in _DECIMAL_RATIO_KEYS and threshold > 1:
        threshold = threshold / 100.0

    return metric_key, threshold, direction


class PortfolioAgent(AgentPlugin):
    """Monitor held positions with P&L and thesis health."""

    name = "portfolio"
    description = "Monitor held positions — P&L, thesis health, alerts"

    def __init__(self, config: dict = None, fmp=None, yfinance=None, db=None,
                 web_search=None, sec=None, v2db=None, llm=None):
        super().__init__(config)
        self.fmp = fmp
        self.yfinance = yfinance
        self.db = db
        self.web_search = web_search
        self.sec = sec
        self.v2db = v2db
        self.llm = llm

    @staticmethod
    def _compute_health_score(thesis_health: list[dict]) -> int | None:
        """Compute a 0-100 health score from per-assumption statuses."""
        if not thesis_health:
            return None
        scorable = [h for h in thesis_health if h.get("status") != "unknown"]
        if not scorable:
            return None
        weights = {"intact": 100, "at_risk": 50, "breach": 0, "monitoring": 70, "unknown": 50}
        total = sum(weights.get(h["status"], 50) for h in scorable)
        return round(total / len(scorable))

    async def _check_thesis_health(
        self,
        ticker: str,
        key_assumptions: list[str],
        constitution: dict | None = None,
    ) -> list[dict]:
        """Check key thesis assumptions against current SEC financial data.

        For each assumption, parses the metric + threshold, fetches the latest
        SEC ratios, and compares. Returns per-assumption status.

        Args:
            ticker: Stock ticker symbol.
            key_assumptions: Strings like "Revenue growth sustains above 15%".
            constitution: Optional constitution for additional context.

        Returns:
            List of dicts: {assumption, metric, threshold, current_value, status}
            Status is "intact", "at_risk", or "breach".
        """
        results: list[dict] = []

        if not self.sec or not key_assumptions:
            return results

        # Fetch SEC ratios once for this ticker
        try:
            ratios_result = await self.sec.get_ratios(ticker)
        except Exception as e:
            log.warning(f"SEC ratios fetch failed for {ticker}: {e}")
            return results

        if not ratios_result.ok or not ratios_result.data:
            return results

        # Use the most recent period's ratios
        ratios_list = ratios_result.data
        if isinstance(ratios_list, list) and ratios_list:
            latest_ratios = ratios_list[0]  # Sorted by date desc
        elif isinstance(ratios_list, dict):
            latest_ratios = ratios_list
        else:
            return results

        for assumption in key_assumptions:
            metric_key, threshold, direction = _parse_assumption(assumption)

            if metric_key is None or threshold is None:
                # Unparseable assumption (e.g. "Multiple re-rates toward fair value")
                results.append({
                    "assumption": assumption,
                    "metric": None,
                    "threshold": None,
                    "current_value": None,
                    "status": "unknown",  # Can't check — flag for review
                })
                continue

            current_value = latest_ratios.get(metric_key)
            if current_value is None:
                results.append({
                    "assumption": assumption,
                    "metric": metric_key,
                    "threshold": threshold,
                    "current_value": None,
                    "status": "unknown",  # No data — flag for review
                })
                continue

            current_value = safe_float(current_value)

            # Determine status
            if direction == "above":
                if current_value >= threshold:
                    status = "intact"
                elif current_value >= threshold * 0.9:
                    status = "at_risk"  # Within 10% of threshold
                else:
                    status = "breach"
            else:  # "below"
                if current_value <= threshold:
                    status = "intact"
                elif current_value <= threshold * 1.1:
                    status = "at_risk"
                else:
                    status = "breach"

            results.append({
                "assumption": assumption,
                "metric": metric_key,
                "threshold": threshold,
                "current_value": current_value,
                "status": status,
            })

        return results

    def _record_exit(
        self,
        ticker: str,
        entry_price: float,
        exit_price: float,
        entry_date: str,
        exit_date: str,
        thesis_health: list[dict] | None = None,
    ) -> None:
        """Record position exit as judgment event for learning (Loop 3).

        Non-blocking: failures are logged but never raise.

        Args:
            ticker: Stock ticker symbol.
            entry_price: Cost basis per share.
            exit_price: Exit price per share.
            entry_date: ISO date string of entry.
            exit_date: ISO date string of exit.
            thesis_health: Thesis health status at time of exit.
        """
        if not self.db:
            return

        try:
            return_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

            # Calculate hold duration in days
            hold_duration_days = None
            try:
                d_entry = datetime.fromisoformat(entry_date)
                d_exit = datetime.fromisoformat(exit_date)
                hold_duration_days = (d_exit - d_entry).days
            except (ValueError, TypeError):
                pass

            # Summarize thesis integrity at exit
            thesis_integrity = "unknown"
            if thesis_health:
                statuses = [h.get("status", "intact") for h in thesis_health]
                if any(s == "breach" for s in statuses):
                    thesis_integrity = "breached"
                elif any(s == "at_risk" for s in statuses):
                    thesis_integrity = "at_risk"
                else:
                    thesis_integrity = "intact"

            self.db.record_judgment_event(
                event_type="position_exited",
                ticker=ticker,
                agent="portfolio",
                data={
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "return_pct": round(return_pct, 2),
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "hold_duration_days": hold_duration_days,
                    "thesis_integrity_at_exit": thesis_integrity,
                    "thesis_health": thesis_health,
                },
                rationale=f"Position exited with {return_pct:+.1f}% return over {hold_duration_days or '?'} days. Thesis {thesis_integrity}.",
            )
            log.info(f"Recorded exit for {ticker}: {return_pct:+.1f}% return, thesis {thesis_integrity}")

        except Exception as e:
            log.warning(f"Failed to record exit for {ticker}: {e}")

    async def _llm_evaluate_thesis_event(
        self,
        ticker: str,
        assumption: str,
        web_text: str,
        financial_data: dict,
    ) -> dict:
        """Use LLM to evaluate whether web search results challenge a thesis assumption.

        Returns structured assessment instead of keyword counting.
        Falls back to keyword counting if LLM is unavailable.

        Args:
            ticker: Stock ticker symbol.
            assumption: The specific thesis assumption to evaluate.
            web_text: Raw web search result text.
            financial_data: Known financial data for grounding.

        Returns:
            Dict with signal_direction, relevance, reasoning, specific_threat.
        """
        if not self.llm:
            return self._keyword_fallback(web_text)

        # Build concise financial context
        fin_summary_parts = []
        for key in ("revenue", "gross_margin", "operating_margin", "roic",
                     "revenue_growth", "debt_equity", "fcf_yield", "pe"):
            val = financial_data.get(key)
            if val is not None:
                if "margin" in key or "growth" in key or "yield" in key or key in ("roic",):
                    fin_summary_parts.append(f"  {key}: {val:.1%}" if isinstance(val, float) and abs(val) < 1 else f"  {key}: {val}")
                else:
                    fin_summary_parts.append(f"  {key}: {val}")
        fin_summary = "\n".join(fin_summary_parts) if fin_summary_parts else "  (no financial data available)"

        prompt = f"""You are monitoring a held position in {ticker}.

THESIS ASSUMPTION: "{assumption}"

RECENT NEWS/RESEARCH:
{web_text[:1500]}

KNOWN FINANCIALS (from SEC filings):
{fin_summary}

TASK: Does this news SPECIFICALLY challenge, support, or have no relevance to the thesis assumption above?

Important:
- Only flag "negative" if the news DIRECTLY contradicts the specific assumption
- Generic bad news about the sector or market does NOT count unless it specifically threatens this assumption
- "Company declined to comment" is NOT a negative signal about the assumption
- Be precise: cite what specifically in the news relates to the assumption

Respond with ONLY this JSON:
{{
  "signal_direction": "negative" or "positive" or "neutral",
  "relevance": 0.0 to 1.0,
  "reasoning": "one sentence explaining why this news does or does not affect the assumption",
  "specific_threat": "what specifically threatens the assumption, or null if nothing does"
}}"""

        try:
            import asyncio as _asyncio
            result = await _asyncio.wait_for(
                self.llm.generate(
                    prompt=prompt,
                    agent="portfolio",
                    reasoning_effort="low",
                ),
                timeout=30.0,
            )
            text = result.text if hasattr(result, "text") else str(result)

            # Parse JSON from response
            import json as _json
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            text = text.strip()

            parsed = _json.loads(text)

            # Validate expected fields
            direction = parsed.get("signal_direction", "neutral")
            if direction not in ("negative", "positive", "neutral"):
                direction = "neutral"

            relevance = float(parsed.get("relevance", 0.5))
            relevance = max(0.0, min(1.0, relevance))

            # Discard low-relevance negative signals (LLM says it's negative but barely relevant)
            if direction == "negative" and relevance < 0.3:
                direction = "neutral"

            return {
                "signal_direction": direction,
                "relevance": relevance,
                "reasoning": str(parsed.get("reasoning", ""))[:300],
                "specific_threat": parsed.get("specific_threat"),
                "source": "llm",
            }
        except Exception as e:
            log.warning(f"LLM thesis event evaluation failed for {ticker}: {e}")
            return self._keyword_fallback(web_text)

    @staticmethod
    def _keyword_fallback(text: str) -> dict:
        """Fallback keyword counting when LLM is unavailable."""
        text_lower = text.lower()
        negative_signals = [
            "challenged", "contradicted", "violated",
            "deteriorated", "declined", "lost",
            "downgraded", "missed", "fell short",
            "abandoned", "reversed", "warning",
        ]
        positive_signals = [
            "confirmed", "reaffirmed", "on track",
            "exceeded", "improved", "maintained",
            "consistent", "intact", "supported",
        ]
        neg_count = sum(1 for s in negative_signals if s in text_lower)
        pos_count = sum(1 for s in positive_signals if s in text_lower)

        if neg_count > pos_count and neg_count >= 2:
            direction = "negative"
        elif pos_count > neg_count:
            direction = "positive"
        else:
            direction = "neutral"

        return {
            "signal_direction": direction,
            "relevance": 0.5,
            "reasoning": f"Keyword fallback: {neg_count} negative, {pos_count} positive signals",
            "specific_threat": None,
            "source": "keyword_fallback",
        }

    async def _check_thesis_events(
        self,
        ticker: str,
        company_name: str,
        key_assumptions: list[str],
        financial_data: dict,
    ) -> dict:
        """Web research: has anything happened that challenges the thesis?

        Three-tier signal system:
        - SEC-confirmed breach: only set by _check_thesis_health (ground truth)
        - Web-corroborated (2+ signals in 90 days): escalate to "at_risk"
        - Web-single (1 signal): "monitoring" — logged but no status change

        Web search alone NEVER sets "breach". Only SEC data can confirm "breach".

        Args:
            ticker: Stock ticker symbol.
            company_name: Full company name.
            key_assumptions: List of thesis assumptions to check.
            financial_data: Dict with financial metrics for fact anchoring.

        Returns:
            Dict with thesis_events list and any_at_risk flag.
        """
        events: list[dict] = []
        any_at_risk = False

        # Limit to 3 assumptions per position for cost management
        assumptions_to_check = key_assumptions[:3]

        # Build fact anchor once per position
        fact_anchor = build_fact_anchor(financial_data, ticker, company_name)

        for assumption in assumptions_to_check:
            try:
                query = (
                    f"{fact_anchor}\n\n"
                    f"We hold {ticker} ({company_name}) based on this assumption: "
                    f"'{assumption}'. "
                    f"Has anything in the last 3 months challenged or contradicted "
                    f"this assumption? Focus on earnings reports, management commentary, "
                    f"competitive developments, regulatory changes, or macro shifts."
                )

                result = await self.web_search.search(
                    query=query,
                    context={"ticker": ticker, "agent": "portfolio"},
                )

                if result.error or not result.text:
                    events.append({
                        "assumption": assumption,
                        "finding": result.error or "No results",
                        "confidence": 0.0,
                        "status": "unconfirmed",
                        "signal_direction": "neutral",
                        "signal_count": 0,
                    })
                    continue

                # Ground the web research against known financial data
                grounded = ground_web_research(
                    raw_text=result.text,
                    financial_data=financial_data,
                    ticker=ticker,
                    company_name=company_name,
                    fact_anchor=fact_anchor,
                )

                confidence = grounded.confidence

                # If grounding failed entirely, mark unconfirmed
                if not grounded.grounded:
                    events.append({
                        "assumption": assumption,
                        "finding": result.text[:500],
                        "confidence": confidence,
                        "status": "unconfirmed",
                        "signal_direction": "neutral",
                        "signal_count": 0,
                    })
                    continue

                # Evaluate signal direction using LLM (falls back to keywords)
                evaluation = await self._llm_evaluate_thesis_event(
                    ticker=ticker,
                    assumption=assumption,
                    web_text=result.text,
                    financial_data=financial_data,
                )
                signal_direction = evaluation["signal_direction"]

                # Persist web signal as judgment event for corroboration tracking
                if self.v2db and signal_direction == "negative":
                    try:
                        self.v2db.record_judgment_event(
                            event_type="thesis_web_signal",
                            ticker=ticker,
                            agent="portfolio",
                            data={
                                "assumption": assumption,
                                "signal_direction": signal_direction,
                                "finding": result.text[:500],
                                "confidence": confidence,
                                "reasoning": evaluation.get("reasoning", ""),
                                "specific_threat": evaluation.get("specific_threat"),
                                "relevance": evaluation.get("relevance", 0),
                                "evaluation_source": evaluation.get("source", "unknown"),
                            },
                            rationale=f"Web signal: {signal_direction} for '{assumption[:60]}' — {evaluation.get('reasoning', '')[:100]}",
                        )
                    except Exception as e:
                        log.warning(f"Failed to persist web signal for {ticker}: {e}")

                # Corroboration check: how many negative signals in last 90 days?
                signal_count = 0
                if self.v2db and signal_direction == "negative":
                    try:
                        signal_count = self.v2db.get_web_signal_count(
                            ticker, assumption, days=90
                        )
                    except Exception:
                        signal_count = 1  # At least this one

                # Status based on corroboration:
                # - 0-1 negative signals: "monitoring" (single hit, might be noise)
                # - 2+ negative signals: "at_risk" (corroborated, escalate)
                # - Web NEVER sets "breach" — only SEC data can do that
                if signal_direction == "negative":
                    if signal_count >= 2:
                        status = "at_risk"
                        any_at_risk = True
                    else:
                        status = "monitoring"
                elif signal_direction == "positive":
                    status = "intact"
                else:
                    status = "monitoring"

                events.append({
                    "assumption": assumption,
                    "finding": result.text[:500],
                    "confidence": confidence,
                    "status": status,
                    "signal_direction": signal_direction,
                    "signal_count": signal_count,
                    "reasoning": evaluation.get("reasoning", ""),
                    "specific_threat": evaluation.get("specific_threat"),
                    "relevance": evaluation.get("relevance", 0),
                    "evaluation_source": evaluation.get("source", "unknown"),
                })

            except Exception as e:
                log.warning(f"Thesis event check failed for {ticker} assumption '{assumption[:50]}': {e}")
                events.append({
                    "assumption": assumption,
                    "finding": f"Search failed: {e}",
                    "confidence": 0.0,
                    "status": "unconfirmed",
                    "signal_direction": "neutral",
                    "signal_count": 0,
                })

        return {"thesis_events": events, "any_at_risk": any_at_risk}

    async def _validate_web_signals(self, ticker: str, sec_health: list[dict]):
        """Compare past web signals against new SEC data to learn accuracy.

        After SEC data arrives (ground truth), check if prior web signals
        predicted the outcome correctly. Records accuracy for the learning loop.
        """
        if not self.v2db or not sec_health:
            return

        for check in sec_health:
            assumption = check.get("assumption", "")
            sec_status = check.get("status", "unknown")
            if sec_status == "unknown" or not assumption:
                continue

            # Look up recent web signals for this assumption
            try:
                from backend.core.db_v2 import ScreenerV2DB
                rows = self.v2db.conn.execute(
                    "SELECT data FROM judgment_events "
                    "WHERE event_type = 'thesis_web_signal' AND ticker = ? "
                    "AND data LIKE ? ORDER BY created_at DESC LIMIT 5",
                    (ticker, f'%{assumption[:60]}%')
                ).fetchall()

                for row in rows:
                    import json as _json
                    data = _json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    web_direction = data.get("signal_direction", "neutral")

                    # Map web direction to comparable status
                    if web_direction == "negative":
                        web_predicted = "at_risk"
                    elif web_direction == "positive":
                        web_predicted = "intact"
                    else:
                        continue  # Neutral signals don't count

                    self.v2db.record_web_signal_accuracy(
                        ticker=ticker,
                        assumption=assumption,
                        web_predicted=web_predicted,
                        sec_confirmed=sec_status,
                    )

            except Exception as e:
                log.debug(f"Web signal validation failed for {ticker}: {e}")

    async def run(self, context: dict) -> AgentResult:
        """Run portfolio monitoring.

        Steps:
        1. Load held positions from DB
        2. Fetch current prices
        3. Calculate P&L
        4. Check thesis health (assumption breaches)
        5. Generate alerts (concentration, drawdown)
        """
        t0 = time.time()
        config = self.config or {}
        alert_config = config.get("alert_on", [])

        # Step 1: Load positions
        positions = context.get("positions", [])
        if not positions and self.db:
            try:
                import json as _json
                snapshot = self.db.get_latest_portfolio_snapshot()
                raw = snapshot.get("holdings", []) if snapshot else []
                if isinstance(raw, str):
                    try:
                        raw = _json.loads(raw)
                    except Exception:
                        raw = []
                positions = raw if isinstance(raw, list) else []
            except Exception:
                positions = []

        if not positions:
            return AgentResult(
                agent=self.name, status="complete",
                event_type="complete",
                data={"holdings": [], "alerts": [], "message": "No positions to monitor"},
                duration_s=time.time() - t0,
            )

        # Step 2: Fetch current prices
        tickers = [p.get("ticker", "") for p in positions if p.get("ticker")]
        quote_source = self.fmp or self.yfinance
        prices = {}
        if quote_source and tickers:
            result = await quote_source.get_quotes(tickers)
            if result.ok:
                for q in result.data:
                    sym = q.get("symbol", "")
                    prices[sym] = safe_float(q.get("price", 0))

        # Step 3: Calculate P&L
        total_value = 0
        total_cost = 0
        holdings = []

        for pos in positions:
            ticker = pos.get("ticker", "")
            shares = safe_float(pos.get("shares", 0))
            cost_basis = safe_float(pos.get("cost_basis", 0))
            current_price = prices.get(ticker, cost_basis)

            market_value = shares * current_price
            cost_value = shares * cost_basis
            pnl = market_value - cost_value
            pnl_pct = (pnl / cost_value * 100) if cost_value > 0 else 0

            total_value += market_value
            total_cost += cost_value

            holdings.append({
                "ticker": ticker,
                "shares": shares,
                "cost_basis": cost_basis,
                "current_price": current_price,
                "market_value": round(market_value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 1),
                "weight": 0,  # Calculated after totals
                "type": pos.get("type", "core"),
            })

        # Calculate weights
        for h in holdings:
            h["weight"] = round(h["market_value"] / total_value * 100, 1) if total_value > 0 else 0

        # Step 3b: Handle exited positions (F2 — exit → learning feedback)
        constitution = context.get("constitution") or {}
        exited_positions = [p for p in positions if p.get("status") == "exited"]
        for pos in exited_positions:
            ticker = pos.get("ticker", "")
            if not ticker:
                continue
            # Check thesis health at exit before recording
            exit_thesis_health = []
            exit_assumptions = pos.get("key_assumptions", [])
            if self.sec and exit_assumptions:
                try:
                    exit_thesis_health = await self._check_thesis_health(
                        ticker, exit_assumptions, constitution,
                    )
                except Exception:
                    pass
            self._record_exit(
                ticker=ticker,
                entry_price=safe_float(pos.get("cost_basis", 0)),
                exit_price=safe_float(pos.get("exit_price", prices.get(ticker, 0))),
                entry_date=pos.get("entry_date", ""),
                exit_date=pos.get("exit_date", datetime.utcnow().strftime("%Y-%m-%d")),
                thesis_health=exit_thesis_health,
            )

        # Step 4: SEC thesis health checks (F1 — assumption refresh with real data)
        thesis_health_by_ticker: dict[str, list[dict]] = {}
        if self.sec:
            for pos in positions:
                ticker = pos.get("ticker", "")
                key_assumptions = pos.get("key_assumptions", [])
                if not ticker or not key_assumptions or pos.get("status") == "exited":
                    continue
                try:
                    health = await self._check_thesis_health(
                        ticker, key_assumptions, constitution,
                    )
                    if health:
                        thesis_health_by_ticker[ticker] = health
                except Exception as e:
                    log.warning(f"SEC thesis health check failed for {ticker}: {e}")

        # Persist aggregate health scores as judgment events + run learning loop
        for tk, health_list in thesis_health_by_ticker.items():
            score = self._compute_health_score(health_list)
            if score is not None and self.v2db:
                try:
                    checked_at = datetime.utcnow().isoformat()
                    self.v2db.record_judgment_event(
                        event_type="thesis_health_score",
                        ticker=tk,
                        agent="portfolio",
                        data={
                            "score": score,
                            "checks": health_list,
                            "checked_at": checked_at,
                        },
                        rationale=f"Thesis health score: {score}/100 ({len(health_list)} assumptions checked)",
                    )
                except Exception as e:
                    log.warning(f"Failed to persist thesis health score for {tk}: {e}")

            # Learning loop: validate prior web signals against fresh SEC data
            try:
                await self._validate_web_signals(tk, health_list)
            except Exception as e:
                log.debug(f"Web signal validation failed for {tk}: {e}")

        # Attach thesis_health to each holding
        for h in holdings:
            tk = h["ticker"]
            if tk in thesis_health_by_ticker:
                h["thesis_health"] = thesis_health_by_ticker[tk]
                h["thesis_health_score"] = self._compute_health_score(thesis_health_by_ticker[tk])

        # Step 4b: Web research thesis monitoring (runs when web_search is available)
        thesis_events_by_ticker: dict[str, dict] = {}

        if self.web_search:
            for pos in positions:
                ticker = pos.get("ticker", "")
                company_name = pos.get("company_name", pos.get("name", ticker))
                key_assumptions = pos.get("key_assumptions", [])
                if not key_assumptions or not ticker:
                    continue
                try:
                    financial_data = pos.get("financial_data", {})
                    events = await self._check_thesis_events(
                        ticker=ticker,
                        company_name=company_name,
                        key_assumptions=key_assumptions,
                        financial_data=financial_data,
                    )
                    thesis_events_by_ticker[ticker] = events
                except Exception as e:
                    log.warning(f"Thesis event check failed for {ticker}: {e}")
                    thesis_events_by_ticker[ticker] = {
                        "thesis_events": [],
                        "any_breach": False,
                    }

        # Step 5: Generate alerts
        alerts = []
        concentration_limit = 20
        drawdown_limit = -15

        # Override thresholds from alert_config
        for alert_rule in alert_config:
            if isinstance(alert_rule, dict):
                if "concentration_above_pct" in alert_rule:
                    concentration_limit = alert_rule["concentration_above_pct"]
                if "drawdown_below_pct" in alert_rule:
                    drawdown_limit = alert_rule["drawdown_below_pct"]

        # Further override from active constitution (if passed in context)
        # (constitution already loaded above for exit handling)
        if constitution:
            agent_profiles = constitution.get("agent_profiles") or {}
            portfolio_profile = agent_profiles.get("portfolio") or {}
            if portfolio_profile.get("concentration_limit_pct") is not None:
                concentration_limit = portfolio_profile["concentration_limit_pct"]
            if portfolio_profile.get("drawdown_threshold_pct") is not None:
                drawdown_limit = portfolio_profile["drawdown_threshold_pct"]
            # Negative convention: constitution may store as positive (e.g. 15 means -15%)
            if drawdown_limit > 0:
                drawdown_limit = -abs(drawdown_limit)

        for h in holdings:
            if h["weight"] > concentration_limit:
                alerts.append({
                    "type": "concentration",
                    "ticker": h["ticker"],
                    "message": f"{h['ticker']} concentration {h['weight']:.1f}% > {concentration_limit}% limit",
                    "severity": "warning",
                })
            if h["pnl_pct"] < drawdown_limit:
                alerts.append({
                    "type": "drawdown",
                    "ticker": h["ticker"],
                    "message": f"{h['ticker']} drawdown {h['pnl_pct']:.1f}% < {drawdown_limit}% threshold",
                    "severity": "warning",
                })

        # SEC thesis health breach alerts (from F1 — higher priority than drawdown)
        for ticker_key, health_list in thesis_health_by_ticker.items():
            for check in health_list:
                if check.get("status") == "breach":
                    alerts.append({
                        "type": "thesis_breach",
                        "ticker": ticker_key,
                        "message": (
                            f"{ticker_key} thesis assumption breached: "
                            f"'{check['assumption'][:80]}' "
                            f"(current {check.get('metric', '?')}: "
                            f"{check.get('current_value')}, "
                            f"threshold: {check.get('threshold')})"
                        ),
                        "severity": "critical",
                        "assumption": check["assumption"],
                        "metric": check.get("metric"),
                        "current_value": check.get("current_value"),
                        "threshold": check.get("threshold"),
                    })

        # Thesis event alerts (from web research — corroborated signals)
        for ticker_key, events_data in thesis_events_by_ticker.items():
            if events_data.get("any_at_risk") or events_data.get("any_breach"):
                at_risk_events = [
                    e for e in events_data.get("thesis_events", [])
                    if e.get("status") in ("at_risk", "breach")
                ]
                for ev in at_risk_events:
                    signal_count = ev.get("signal_count", 0)
                    alerts.append({
                        "type": "thesis_event_at_risk",
                        "ticker": ticker_key,
                        "message": (
                            f"{ticker_key} thesis assumption at risk "
                            f"({signal_count} web signals in 90 days): "
                            f"'{ev['assumption'][:80]}'"
                        ),
                        "severity": "warning",
                        "assumption": ev["assumption"],
                        "finding": ev.get("finding", ""),
                        "confidence": ev.get("confidence", 0.0),
                        "signal_count": signal_count,
                    })

        # Step 6: Portfolio snapshot to DB
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        snapshot = {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 1),
            "position_count": len(holdings),
            "invested_pct": round(total_value / (total_value + total_cost * 0.38) * 100, 1),  # Rough
            "holdings": holdings,
            "alerts": alerts,
        }

        if thesis_events_by_ticker:
            snapshot["thesis_events"] = thesis_events_by_ticker

        if self.db:
            try:
                self.db.record_portfolio_snapshot(
                    snapshot_date=datetime.utcnow().strftime("%Y-%m-%d"),
                    total_value=total_value,
                    holdings=holdings,
                    alerts=alerts,
                    daily_pnl=total_pnl,
                )
            except Exception as e:
                log.warning(f"Portfolio snapshot DB write failed: {e}")

        log.info(f"Portfolio: {len(holdings)} positions, ${total_value:,.0f}, {len(alerts)} alerts")

        return AgentResult(
            agent=self.name, status="complete",
            event_type="alert" if alerts else "complete",
            data=snapshot,
            duration_s=time.time() - t0,
        )
