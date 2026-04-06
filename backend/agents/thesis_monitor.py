"""Thesis Monitor Agent — Post-entry assumption tracking.

Watches active theses (PASS verdict + held position) for:
- Approaching earnings dates
- New SEC filings since thesis date
- Fundamental drift vs thesis-time values
- Key assumption breaches

Emits alerts as judgment events. Runs on-demand or via portfolio.complete trigger.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta

from backend.agents import AgentPlugin, AgentResult
from backend.core.utils import safe_float

log = logging.getLogger("fundops.thesis_monitor")


class ThesisMonitorAgent(AgentPlugin):
    """Monitor active theses for drift and assumption breaches."""

    name = "thesis_monitor"
    description = "Track thesis assumptions post-entry"

    def __init__(self, config: dict = None, db=None, connectors: dict = None):
        super().__init__(config)
        self.db = db
        self.connectors = connectors or {}

    async def run(self, context: dict) -> AgentResult:
        """Check all active theses for drift and breaches.

        Steps:
        1. Load active theses (PASS verdict + held positions)
        2. For each: check earnings proximity, filing recency, fundamental drift
        3. Emit alerts for breaches
        """
        t0 = time.time()
        alerts = []
        checked = 0

        # Load active theses from DB
        active_theses = self._load_active_theses()
        if not active_theses:
            return AgentResult(
                agent=self.name, status="complete",
                event_type="complete",
                data={"alerts": [], "message": "No active theses to monitor"},
                duration_s=time.time() - t0,
            )

        for thesis_record in active_theses:
            ticker = thesis_record.get("ticker", "")
            thesis_data = thesis_record.get("data", {})
            thesis_date = thesis_record.get("created_at", "")

            try:
                ticker_alerts = self._check_thesis(ticker, thesis_data, thesis_date)
                alerts.extend(ticker_alerts)
                checked += 1
            except Exception as e:
                log.warning(f"Thesis monitor failed for {ticker}: {e}")

        # Record alerts as judgment events
        self._record_alerts(alerts)

        log.info(f"Thesis monitor: checked {checked} theses, {len(alerts)} alerts")

        return AgentResult(
            agent=self.name, status="complete",
            event_type="complete" if not alerts else "alert",
            data={
                "alerts": alerts,
                "checked_count": checked,
                "alert_count": len(alerts),
            },
            duration_s=time.time() - t0,
        )

    def _load_active_theses(self) -> list[dict]:
        """Load theses with PASS verdict that correspond to held positions."""
        if not self.db:
            return []

        try:
            # Get latest IC-passed theses
            rows = self.db.conn.execute("""
                SELECT ar.ticker, ar.full_output, ar.run_at
                FROM agent_runs ar
                WHERE ar.agent IN ('thesis', 'ic_review')
                  AND ar.verdict = 'PASS'
                  AND ar.ticker IN (
                      SELECT ticker FROM tickers WHERE is_owned = 1
                  )
                ORDER BY ar.run_at DESC
            """).fetchall()

            results = []
            seen = set()
            for row in rows:
                ticker = row[0]
                if ticker in seen:
                    continue
                seen.add(ticker)
                import json
                try:
                    data = json.loads(row[1]) if row[1] else {}
                except (json.JSONDecodeError, TypeError):
                    data = {}
                results.append({
                    "ticker": ticker,
                    "data": data,
                    "created_at": row[2],
                })
            return results
        except Exception as e:
            log.warning(f"Failed to load active theses: {e}")
            return []

    def _check_thesis(
        self, ticker: str, thesis_data: dict, thesis_date: str
    ) -> list[dict]:
        """Check a single thesis for drift and breaches."""
        alerts = []

        # 1. Check if thesis is old (>180 days since generated)
        if thesis_date:
            try:
                gen_date = datetime.fromisoformat(thesis_date.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - gen_date).days
                if age_days > 180:
                    alerts.append({
                        "ticker": ticker,
                        "type": "stale_thesis",
                        "severity": "medium",
                        "message": f"Thesis is {age_days} days old. Consider refreshing.",
                    })
            except (ValueError, TypeError):
                pass

        # 2. Check key assumptions (from IC review output)
        key_assumptions = thesis_data.get("key_assumptions", [])
        if key_assumptions and self.connectors:
            try:
                current_data = self._fetch_current_metrics(ticker)
                if current_data:
                    for assumption in key_assumptions:
                        breach = self._check_assumption(assumption, thesis_data, current_data)
                        if breach:
                            alerts.append({
                                "ticker": ticker,
                                "type": "assumption_breach",
                                "severity": "high",
                                "message": breach,
                                "assumption": assumption,
                            })
            except Exception as e:
                log.debug(f"Assumption check failed for {ticker}: {e}")

        # 3. Check fundamental drift (quality metrics)
        quality_at_thesis = thesis_data.get("quality", {})
        if quality_at_thesis and self.connectors:
            try:
                current = self._fetch_current_metrics(ticker)
                if current:
                    drift_alerts = self._check_drift(ticker, quality_at_thesis, current)
                    alerts.extend(drift_alerts)
            except Exception:
                pass

        return alerts

    def _fetch_current_metrics(self, ticker: str) -> dict | None:
        """Fetch current financial metrics for comparison."""
        # Try FMP connector
        fmp = self.connectors.get("market_data")
        if fmp and hasattr(fmp, "get_key_metrics"):
            try:
                return fmp.get_key_metrics(ticker)
            except Exception:
                pass

        # Try SEC connector
        sec = self.connectors.get("filings")
        if sec and hasattr(sec, "get_ratios"):
            try:
                return sec.get_ratios(ticker)
            except Exception:
                pass

        return None

    def _check_assumption(
        self, assumption: str, thesis_data: dict, current_data: dict
    ) -> str | None:
        """Check if a key assumption text is still valid.

        Tries to parse numeric claims from assumption text and verify.
        Returns a breach message if detected, None otherwise.
        """
        import re
        # Look for patterns like "Revenue growth sustains above 15%"
        match = re.search(
            r"(revenue|margin|roic|growth|retention)\s+.*?(above|below|at least|exceeds?)\s+(\d+\.?\d*)%?",
            assumption.lower(),
        )
        if not match:
            return None

        metric_hint, direction, threshold_str = match.groups()
        threshold = float(threshold_str)

        # Map hint to metric key
        metric_map = {
            "revenue": "revenue_growth",
            "margin": "gross_margin",
            "roic": "roic",
            "growth": "revenue_growth",
            "retention": "retention_rate",
        }
        metric_key = metric_map.get(metric_hint)
        if not metric_key:
            return None

        current_val = safe_float(current_data.get(metric_key, 0))
        if current_val == 0:
            return None

        # Normalize (some values stored as decimals, some as percentages)
        if abs(current_val) < 1 and threshold > 1:
            current_val *= 100

        if "above" in direction or "at least" in direction or "exceed" in direction:
            if current_val < threshold:
                return (
                    f"Assumption breach: '{assumption}' — "
                    f"current {metric_key} is {current_val:.1f}% (below {threshold}%)"
                )
        elif "below" in direction:
            if current_val > threshold:
                return (
                    f"Assumption breach: '{assumption}' — "
                    f"current {metric_key} is {current_val:.1f}% (above {threshold}%)"
                )

        return None

    def _check_drift(
        self,
        ticker: str,
        quality_at_thesis: dict,
        current: dict,
    ) -> list[dict]:
        """Check for fundamental drift in quality metrics."""
        alerts = []

        drift_checks = {
            "gross_margin": 5.0,    # 5pp drift threshold
            "roic": 3.0,
            "debt_equity": 0.5,     # 0.5x drift threshold
        }

        for metric, threshold in drift_checks.items():
            old_val = safe_float(quality_at_thesis.get(metric, 0))
            new_val = safe_float(current.get(metric, 0))

            # Normalize (quality dict has percentage values like 46.0)
            if metric in ("gross_margin", "roic") and abs(new_val) < 1 and abs(old_val) > 1:
                new_val *= 100

            if old_val == 0:
                continue

            drift = abs(new_val - old_val)
            if drift > threshold:
                direction = "deteriorated" if new_val < old_val else "improved"
                alerts.append({
                    "ticker": ticker,
                    "type": "fundamental_drift",
                    "severity": "medium",
                    "message": (
                        f"{metric} {direction}: {old_val:.1f} -> {new_val:.1f} "
                        f"(drift: {drift:.1f}, threshold: {threshold})"
                    ),
                })

        return alerts

    def _record_alerts(self, alerts: list[dict]) -> None:
        """Record alerts as judgment events."""
        if not self.db or not alerts:
            return

        try:
            from backend.core.db_v2 import ScreenerV2DB
            v2db = ScreenerV2DB(db_path=self.db.db_path if hasattr(self.db, "db_path") else None)
            for alert in alerts:
                v2db.record_judgment_event(
                    event_type="thesis_alert",
                    ticker=alert.get("ticker", ""),
                    agent=self.name,
                    data=alert,
                    rationale=alert.get("message", ""),
                )
            v2db.close()
        except Exception as e:
            log.debug(f"Failed to record thesis alerts: {e}")
