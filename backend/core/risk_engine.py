"""Policy/risk engine — deterministic gates for position sizing.

Enforces mechanical limits from the constitution's position_sizing and
concentration_rules. These gates run before any human or AI override.

Checks:
- Max single position weight
- Max sector concentration
- Cash reserve minimum
- Portfolio-level concentration alerts
"""

import logging
from typing import Any

from backend.core.utils import safe_float

log = logging.getLogger("fundops.risk_engine")

# Defaults if constitution doesn't specify
_DEFAULTS = {
    "max_position_pct": 20.0,
    "max_sector_pct": 35.0,
    "min_cash_pct": 5.0,
    "max_positions": 20,
}


class RiskGate:
    """Deterministic risk gate that checks position and portfolio limits."""

    def __init__(self, constitution: dict | None = None):
        constitution = constitution or {}
        pos_sizing = constitution.get("position_sizing") or {}
        concentration = constitution.get("concentration_rules") or {}

        self.max_position_pct = safe_float(
            pos_sizing.get("max_position_pct") or
            concentration.get("max_position_pct"),
            _DEFAULTS["max_position_pct"],
        )
        self.max_sector_pct = safe_float(
            concentration.get("max_sector_pct") or
            concentration.get("theme_overlap_max_pct"),
            _DEFAULTS["max_sector_pct"],
        )
        self.min_cash_pct = safe_float(
            pos_sizing.get("min_cash_pct"),
            _DEFAULTS["min_cash_pct"],
        )
        self.max_positions = int(safe_float(
            pos_sizing.get("max_positions") or
            concentration.get("max_positions"),
            _DEFAULTS["max_positions"],
        ))

    def check_new_position(
        self,
        ticker: str,
        proposed_weight: float,
        sector: str,
        portfolio_state: dict,
    ) -> dict:
        """Check if a new position or weight increase passes risk limits.

        Args:
            ticker: Stock ticker
            proposed_weight: Proposed portfolio weight (0-100%)
            sector: Stock sector
            portfolio_state: {
                "holdings": [{"ticker": ..., "weight": ..., "sector": ...}, ...],
                "cash_pct": float,
                "total_positions": int,
            }

        Returns:
            {
                "approved": bool,
                "violations": list[str],
                "adjusted_weight": float,  # capped weight if violation
            }
        """
        violations = []
        adjusted_weight = proposed_weight
        holdings = portfolio_state.get("holdings", [])
        cash_pct = safe_float(portfolio_state.get("cash_pct", 100))

        # 1. Max position weight
        if proposed_weight > self.max_position_pct:
            violations.append(
                f"Position weight {proposed_weight:.1f}% exceeds max {self.max_position_pct:.0f}%"
            )
            adjusted_weight = self.max_position_pct

        # 2. Sector concentration
        sector_weight = sum(
            safe_float(h.get("weight", 0))
            for h in holdings
            if (h.get("sector", "") or "").lower() == (sector or "").lower()
            and h.get("ticker") != ticker  # exclude self if rebalancing
        )
        if sector_weight + proposed_weight > self.max_sector_pct:
            violations.append(
                f"Sector '{sector}' would be {sector_weight + proposed_weight:.1f}% "
                f"(max {self.max_sector_pct:.0f}%)"
            )
            adjusted_weight = min(adjusted_weight, max(0, self.max_sector_pct - sector_weight))

        # 3. Cash reserve
        if cash_pct - proposed_weight < self.min_cash_pct:
            violations.append(
                f"Cash would drop to {cash_pct - proposed_weight:.1f}% "
                f"(min {self.min_cash_pct:.0f}%)"
            )
            adjusted_weight = min(adjusted_weight, max(0, cash_pct - self.min_cash_pct))

        # 4. Position count
        existing_tickers = {h.get("ticker") for h in holdings}
        if ticker not in existing_tickers and len(existing_tickers) >= self.max_positions:
            violations.append(
                f"Portfolio already has {len(existing_tickers)} positions "
                f"(max {self.max_positions})"
            )
            adjusted_weight = 0

        approved = len(violations) == 0

        if violations:
            log.info(
                f"[{ticker}] Risk gate: {len(violations)} violation(s). "
                f"Weight adjusted {proposed_weight:.1f}% -> {adjusted_weight:.1f}%"
            )

        return {
            "approved": approved,
            "violations": violations,
            "adjusted_weight": round(adjusted_weight, 1),
        }

    def check_portfolio_health(
        self,
        portfolio_state: dict,
    ) -> dict:
        """Check overall portfolio health against risk limits.

        Returns:
            {"healthy": bool, "alerts": list[str]}
        """
        alerts = []
        holdings = portfolio_state.get("holdings", [])

        # Top-3 concentration
        weights = sorted(
            [safe_float(h.get("weight", 0)) for h in holdings],
            reverse=True,
        )
        if len(weights) >= 3:
            top3 = sum(weights[:3])
            if top3 > 55:
                alerts.append(f"Top-3 concentration: {top3:.1f}% (threshold: 55%)")

        # Sector concentration
        sector_weights: dict[str, float] = {}
        for h in holdings:
            s = (h.get("sector", "") or "Unknown").lower()
            sector_weights[s] = sector_weights.get(s, 0) + safe_float(h.get("weight", 0))

        for sector, weight in sector_weights.items():
            if weight > self.max_sector_pct:
                alerts.append(
                    f"Sector '{sector}' at {weight:.1f}% (max {self.max_sector_pct:.0f}%)"
                )

        # Position count
        if len(holdings) > self.max_positions:
            alerts.append(
                f"Too many positions: {len(holdings)} (max {self.max_positions})"
            )

        return {
            "healthy": len(alerts) == 0,
            "alerts": alerts,
        }
