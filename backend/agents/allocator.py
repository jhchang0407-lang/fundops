"""Allocator Agent — Position sizing and action recommendations.

Two modes:
1. **Held positions** — reads memos, thesis, financials to verify thesis health,
   detect drift, check concentration, and recommend TRIM/EXIT/HOLD/ADD.
2. **New opportunities** — reads IC-approved candidates with memos and sizes
   initial positions based on conviction, return profile, and portfolio fit.

Uses LLM for thesis verification and drift analysis when research data is available.
Falls back to rules-only when no LLM or no research data.
"""

from __future__ import annotations

import json
import logging
import time

from backend.agents import AgentPlugin, AgentResult
from backend.core.utils import safe_float

log = logging.getLogger("fundops.allocator")


class AllocatorAgent(AgentPlugin):
    """Position sizing and action recommendations."""

    name = "allocator"
    description = "Size positions and recommend actions"

    def __init__(self, config: dict = None, db=None, llm=None):
        super().__init__(config)
        self.db = db
        self.llm = llm

    def _apply_sell_discipline(
        self, holding: dict, alerts: list, sell_discipline: dict, constitution: dict
    ) -> dict | None:
        """Check sell discipline rules against a holding."""
        if not sell_discipline:
            return None

        ticker = holding.get("ticker", "")
        pnl_pct = safe_float(holding.get("pnl_pct", 0))
        weight = safe_float(holding.get("weight", 0))
        expected_return = safe_float(holding.get("expected_return", 0))
        pos_type = holding.get("type", "core")

        # EXIT: max loss
        max_loss_pct = sell_discipline.get("max_loss_pct")
        if max_loss_pct is not None and pnl_pct < -abs(max_loss_pct):
            return {
                "action": "EXIT",
                "ticker": ticker,
                "urgency": "high",
                "reason": f"Sell discipline: loss {pnl_pct:.1f}% exceeds max_loss_pct -{abs(max_loss_pct)}%",
                "detail": f"Position down {pnl_pct:.1f}%. Constitution max_loss_pct rule triggered.",
                "current_weight": weight,
                "type": pos_type,
                "pnl_pct": pnl_pct,
                "sell_discipline_triggered": True,
                "sell_rule": f"max_loss_pct: -{abs(max_loss_pct)}%",
            }

        # EXIT: consecutive thesis breaches
        breach_quarters = sell_discipline.get("thesis_breach_consecutive_quarters")
        if breach_quarters is not None:
            consecutive = safe_float(holding.get("consecutive_breach_quarters", 0))
            if consecutive >= breach_quarters:
                return {
                    "action": "EXIT",
                    "ticker": ticker,
                    "urgency": "high",
                    "reason": (
                        f"Sell discipline: {int(consecutive)} consecutive thesis breach quarters "
                        f"(limit: {breach_quarters})"
                    ),
                    "detail": (
                        f"Thesis breached for {int(consecutive)} consecutive quarters. "
                        f"Constitution requires exit after {breach_quarters}."
                    ),
                    "current_weight": weight,
                    "type": pos_type,
                    "pnl_pct": pnl_pct,
                    "sell_discipline_triggered": True,
                    "sell_rule": f"thesis_breach_consecutive_quarters: {breach_quarters}",
                }

        # TRIM: remaining return too low
        min_remaining_return = sell_discipline.get("min_remaining_return_pct")
        if min_remaining_return is not None and expected_return > 0:
            if expected_return < min_remaining_return:
                return {
                    "action": "TRIM",
                    "ticker": ticker,
                    "urgency": "medium",
                    "reason": (
                        f"Sell discipline: expected return {expected_return:.1f}% "
                        f"below min_remaining_return_pct {min_remaining_return}%"
                    ),
                    "detail": (
                        f"Remaining expected return ({expected_return:.1f}%) is below "
                        f"constitution threshold ({min_remaining_return}%). Trim position."
                    ),
                    "current_weight": weight,
                    "type": pos_type,
                    "pnl_pct": pnl_pct,
                    "sell_discipline_triggered": True,
                    "sell_rule": f"min_remaining_return_pct: {min_remaining_return}%",
                }

        return None

    async def _llm_analyze_holdings(
        self, holdings: list, research_context: dict, constitution: dict, config: dict,
    ) -> dict:
        """Use LLM to analyze held positions against their research data.

        Returns dict of {ticker: {action, urgency, reason, detail, thesis_health, ...}}
        """
        if not self.llm or not research_context:
            return {}

        # Build position summaries for LLM
        position_summaries = []
        for h in holdings:
            ticker = h.get("ticker", "")
            rc = research_context.get(ticker, {})
            if not rc:
                continue

            lines = [f"\n## {ticker}"]
            lines.append(f"Current price: ${h.get('current_price', 'N/A')}")
            lines.append(f"Cost basis: ${h.get('cost_basis', 'N/A')}")
            lines.append(f"P&L: {h.get('pnl_pct', 0):+.1f}%")
            lines.append(f"Weight: {h.get('weight', 0):.1f}%")
            lines.append(f"Position type: {h.get('type', 'core')}")
            lines.append(f"Sector: {h.get('sector', 'Unknown')}")

            # Thesis data
            thesis = rc.get("thesis", {})
            if thesis:
                lines.append(f"\n### Thesis")
                lines.append(f"Fair value: ${thesis.get('fair_value', 'N/A')}")
                exp_ret = thesis.get("expected_return")
                if exp_ret is not None:
                    lines.append(f"Expected return: {exp_ret}%")
                if thesis.get("return_sources"):
                    lines.append(f"Return sources: {json.dumps(thesis['return_sources'])}")
                if thesis.get("key_assumptions"):
                    lines.append(f"Key assumptions: {json.dumps(thesis['key_assumptions'])}")
                if thesis.get("summary"):
                    lines.append(f"Summary: {thesis['summary'][:500]}")

            # IC review
            ic = rc.get("ic_review", {})
            if ic:
                lines.append(f"\n### IC Review")
                lines.append(f"Verdict: {ic.get('verdict', 'N/A')}")
                lines.append(f"Conviction: {ic.get('conviction', 'N/A')}/5")
                if ic.get("base_return") is not None:
                    lines.append(f"Base return: {ic['base_return']}%")
                if ic.get("bear_return") is not None:
                    lines.append(f"Bear return: {ic['bear_return']}%")

            # Memo content
            memos = rc.get("memos", {})
            for memo_type, memo_data in memos.items():
                lines.append(f"\n### Memo ({memo_type})")
                if memo_data.get("content_preview"):
                    lines.append(memo_data["content_preview"][:1500])

            # Financial data
            fins = rc.get("financials", {})
            if fins:
                lines.append(f"\n### Current Financials")
                for key in ("gross_margin", "operating_margin", "roic", "roe",
                           "revenue_growth", "earnings_growth", "fcf_yield",
                           "earnings_yield", "debt_equity", "pe"):
                    val = fins.get(key)
                    if val is not None:
                        pct = "%" if "margin" in key or "growth" in key or "yield" in key or key in ("roic", "roe") else ""
                        if pct:
                            lines.append(f"  {key}: {val:.1f}{pct}")
                        else:
                            lines.append(f"  {key}: {val:.2f}")

            position_summaries.append("\n".join(lines))

        if not position_summaries:
            return {}

        concentration_limit = config.get("concentration_limit_pct", 25)
        prompt = f"""You are a portfolio manager analyzing held positions. For each position, evaluate:

1. **Thesis Health** (0-100): Is the original thesis still intact? Look for:
   - Revenue/earnings growth tracking vs thesis assumptions
   - Margin trends (expanding/contracting vs thesis)
   - Competitive position changes
   - Valuation gap (current price vs fair value)
   - Any red flags in the financials

2. **Thesis Drift**: Has the reason you own this stock changed from the original thesis?

3. **Sizing Assessment**: Given the current data, is the position sized appropriately?
   - Concentration limit: {concentration_limit}% max per position
   - Core compounder: 5-10% target
   - Tactical: 3-5% target
   - Balanced: 4-7% target

4. **Action Recommendation**: One of:
   - HOLD: Thesis intact, sizing appropriate
   - TRIM: Oversized or thesis weakening
   - ADD_ON_WEAKNESS: Underweight and thesis strengthening
   - REUNDERWRITE: Thesis may be broken, needs fresh analysis
   - EXIT: Thesis broken or sell discipline triggered

For each position, respond with a JSON object.

POSITIONS:
{"".join(position_summaries)}

Respond with ONLY a JSON object mapping ticker to analysis:
```json
{{
  "TICKER": {{
    "thesis_health": 0-100,
    "thesis_drift": "none|minor|significant",
    "drift_detail": "what changed from original thesis, if anything",
    "action": "HOLD|TRIM|ADD_ON_WEAKNESS|REUNDERWRITE|EXIT",
    "urgency": "none|low|medium|high",
    "reason": "one-line reason for the action",
    "detail": "2-3 sentence explanation with specific data points",
    "expected_return_current": estimated current expected return as number,
    "key_risks": ["risk1", "risk2"]
  }}
}}
```"""

        try:
            # Inject memory context
            from backend.api.deps import get_memory
            memory_block = get_memory().format_for_injection()
            if memory_block:
                prompt = f"{memory_block}\n\n{prompt}"

            import asyncio
            result = await asyncio.wait_for(
                self.llm.generate(prompt=prompt, agent="allocator", reasoning_effort="medium"),
                timeout=60.0,
            )
            text = result.text if hasattr(result, "text") else str(result)
            # Strip markdown fences
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            text = text.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Retry with correction prompt
                retry_result = await self.llm.generate(
                    prompt=f"Fix this JSON and return ONLY valid JSON:\n{text}",
                    agent="allocator",
                    reasoning_effort="low",
                )
                retry_text = retry_result.text.strip()
                if retry_text.startswith("```"):
                    retry_text = retry_text.split("\n", 1)[1] if "\n" in retry_text else retry_text[3:]
                if retry_text.endswith("```"):
                    retry_text = retry_text[:-3]
                return json.loads(retry_text.strip())
        except Exception as e:
            log.warning(f"LLM analysis failed: {e}")
            return {}

    async def _llm_size_opportunities(
        self, opportunities: list, holdings: list, constitution: dict, config: dict,
    ) -> list:
        """Use LLM to size new approved opportunities for the portfolio.

        Returns list of opportunity dicts with sizing recommendations.
        """
        if not self.llm or not opportunities:
            return []

        concentration_limit = config.get("concentration_limit_pct", 25)
        total_value = sum(safe_float(h.get("market_value", 0)) for h in holdings)
        cash = safe_float(context.get("cash", 0))

        held_summary = []
        for h in holdings:
            held_summary.append(
                f"  {h.get('ticker')}: {h.get('weight', 0):.1f}% weight, "
                f"{h.get('sector', 'Unknown')} sector, {h.get('pnl_pct', 0):+.1f}% P&L"
            )

        opp_summaries = []
        for opp in opportunities:
            lines = [f"\n## {opp['ticker']}"]
            if opp.get("thesis_summary"):
                lines.append(f"Thesis: {opp['thesis_summary'][:400]}")
            if opp.get("fair_value"):
                lines.append(f"Fair value: ${opp['fair_value']}")
            if opp.get("expected_return") is not None:
                lines.append(f"Expected return: {opp['expected_return']}%")
            if opp.get("base_return") is not None:
                lines.append(f"IC base return: {opp['base_return']}%")
            if opp.get("bear_return") is not None:
                lines.append(f"IC bear return: {opp['bear_return']}%")
            if opp.get("conviction") is not None:
                lines.append(f"Conviction: {opp['conviction']}/5")
            if opp.get("return_sources"):
                lines.append(f"Return sources: {json.dumps(opp['return_sources'])}")
            fins = opp.get("financials", {})
            if fins:
                for key in ("gross_margin", "operating_margin", "roic", "revenue_growth",
                           "fcf_yield", "pe", "debt_equity"):
                    val = fins.get(key)
                    if val is not None:
                        lines.append(f"  {key}: {val}")
            if opp.get("has_memo"):
                lines.append(f"Memo available: {opp.get('memo_summary', '')[:200]}")
            opp_summaries.append("\n".join(lines))

        prompt = f"""You are a portfolio manager sizing new positions for IC-approved opportunities.

CURRENT PORTFOLIO (total value ~${total_value:,.0f}):
{chr(10).join(held_summary)}

CONCENTRATION LIMIT: {concentration_limit}% max per position

APPROVED OPPORTUNITIES:
{"".join(opp_summaries)}

For each opportunity, recommend:
1. **Position type**: tactical (3-5%), core (5-10%), or balanced (4-7%)
2. **Initial weight**: Starting position size as % of portfolio
3. **Entry strategy**: Full position now, or scale in?
4. **Priority**: How urgent is it to initiate? (high/medium/low)

Consider:
- Sector overlap with existing holdings
- Conviction level and expected return
- Bear case downside protection
- Portfolio diversification

Respond with ONLY a JSON array:
```json
[
  {{
    "ticker": "TICKER",
    "position_type": "core|tactical|balanced",
    "recommended_weight": number (% of portfolio),
    "entry_strategy": "full|scale_in",
    "priority": "high|medium|low",
    "reason": "1-2 sentence rationale",
    "sector": "sector name",
    "expected_return": number,
    "bear_return": number or null
  }}
]
```"""

        try:
            # Inject memory context
            from backend.api.deps import get_memory
            memory_block = get_memory().format_for_injection()
            if memory_block:
                prompt = f"{memory_block}\n\n{prompt}"

            import asyncio
            result = await asyncio.wait_for(
                self.llm.generate(prompt=prompt, agent="allocator", reasoning_effort="medium"),
                timeout=60.0,
            )
            text = result.text if hasattr(result, "text") else str(result)
            # Strip markdown fences
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            text = text.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Retry with correction prompt
                retry_result = await self.llm.generate(
                    prompt=f"Fix this JSON and return ONLY valid JSON:\n{text}",
                    agent="allocator",
                    reasoning_effort="low",
                )
                retry_text = retry_result.text.strip()
                if retry_text.startswith("```"):
                    retry_text = retry_text.split("\n", 1)[1] if "\n" in retry_text else retry_text[3:]
                if retry_text.endswith("```"):
                    retry_text = retry_text[:-3]
                return json.loads(retry_text.strip())
        except Exception as e:
            log.warning(f"LLM opportunity sizing failed: {e}")
            return []

    async def run(self, context: dict) -> AgentResult:
        """Generate allocation recommendations.

        1. Load holdings + research data
        2. LLM analyzes thesis health + drift for held positions
        3. Rules-based sell discipline + concentration checks
        4. LLM sizes IC-approved new opportunities
        5. Group by urgency
        """
        t0 = time.time()
        config = self.config or {}
        update_progress = context.get("_update_progress", lambda msg: None)

        # Apply constitution overrides
        constitution = context.get("constitution") or {}
        if constitution:
            pos_sizing = constitution.get("position_sizing") or {}
            agent_profiles = constitution.get("agent_profiles") or {}
            alloc_profile = agent_profiles.get("allocator") or {}
            if pos_sizing.get("max_position_pct") is not None:
                config = dict(config, concentration_limit_pct=pos_sizing["max_position_pct"])
            if alloc_profile.get("max_position_pct") is not None:
                config = dict(config, concentration_limit_pct=alloc_profile["max_position_pct"])
            if alloc_profile.get("min_expected_return_pct") is not None:
                config = dict(config, min_expected_return_pct=alloc_profile["min_expected_return_pct"])
            if alloc_profile.get("position_types") and isinstance(alloc_profile["position_types"], dict):
                config = dict(config, position_types=alloc_profile["position_types"])

        position_types = config.get("position_types", {})
        concentration_limit = config.get("concentration_limit_pct", 25)
        sell_discipline = constitution.get("sell_discipline") or {}

        holdings = context.get("holdings", [])
        alerts = context.get("alerts", [])
        research_context = context.get("research_context", {})
        approved_opps = context.get("approved_opportunities", [])

        if not holdings and not approved_opps:
            return AgentResult(
                agent=self.name, status="complete",
                event_type="complete",
                data={"actions": [], "message": "No holdings or approved opportunities to analyze"},
                duration_s=time.time() - t0,
            )

        # Step 1: LLM thesis analysis for held positions (if research data available)
        update_progress("Analyzing thesis health...")
        llm_analysis = {}
        if holdings and research_context:
            llm_analysis = await self._llm_analyze_holdings(
                holdings, research_context, constitution, config,
            )

        # Step 2: Rules-based checks + merge LLM insights
        actions_required = []
        monitoring = []
        no_action = []

        for h in holdings:
            ticker = h.get("ticker", "")
            weight = safe_float(h.get("weight", 0))
            pnl_pct = safe_float(h.get("pnl_pct", 0))
            pos_type = h.get("type", "core")

            # Get LLM analysis for this ticker
            llm_rec = llm_analysis.get(ticker, {})
            thesis_health = llm_rec.get("thesis_health", 0)
            thesis_drift = llm_rec.get("thesis_drift", "unknown")
            expected_return = safe_float(llm_rec.get("expected_return_current", 0))

            # Enrich holding with LLM data for downstream use
            h["thesis_health"] = thesis_health
            h["thesis_drift"] = thesis_drift
            h["expected_return"] = expected_return
            h["key_risks"] = llm_rec.get("key_risks", [])

            # Sell discipline check (highest priority)
            sell_action = self._apply_sell_discipline(h, alerts, sell_discipline, constitution)
            if sell_action is not None:
                sell_action["thesis_health"] = thesis_health
                sell_action["thesis_drift"] = thesis_drift
                sell_action["expected_return"] = expected_return
                sell_action["key_risks"] = llm_rec.get("key_risks", [])
                actions_required.append(sell_action)
                continue

            # If LLM recommended an action, use it (but override with rules if needed)
            llm_action = llm_rec.get("action", "")

            # Concentration check (rules always win)
            if weight > concentration_limit:
                target_weight = min(15, concentration_limit)
                actions_required.append({
                    "action": "TRIM",
                    "ticker": ticker,
                    "urgency": "high",
                    "reason": f"Concentration {weight:.1f}% > {concentration_limit}% limit",
                    "detail": llm_rec.get("detail", f"Trim to {target_weight}% target."),
                    "current_weight": weight,
                    "target_weight": target_weight,
                    "type": pos_type,
                    "pnl_pct": pnl_pct,
                    "thesis_health": thesis_health,
                    "thesis_drift": thesis_drift,
                    "expected_return": expected_return,
                    "key_risks": llm_rec.get("key_risks", []),
                })
                continue

            # LLM-driven actions
            if llm_action == "EXIT":
                actions_required.append({
                    "action": "EXIT",
                    "ticker": ticker,
                    "urgency": llm_rec.get("urgency", "high"),
                    "reason": llm_rec.get("reason", "Thesis broken"),
                    "detail": llm_rec.get("detail", ""),
                    "current_weight": weight,
                    "type": pos_type,
                    "pnl_pct": pnl_pct,
                    "thesis_health": thesis_health,
                    "thesis_drift": thesis_drift,
                    "expected_return": expected_return,
                    "key_risks": llm_rec.get("key_risks", []),
                })
            elif llm_action == "TRIM":
                actions_required.append({
                    "action": "TRIM",
                    "ticker": ticker,
                    "urgency": llm_rec.get("urgency", "medium"),
                    "reason": llm_rec.get("reason", "Position oversized or thesis weakening"),
                    "detail": llm_rec.get("detail", ""),
                    "current_weight": weight,
                    "type": pos_type,
                    "pnl_pct": pnl_pct,
                    "thesis_health": thesis_health,
                    "thesis_drift": thesis_drift,
                    "expected_return": expected_return,
                    "key_risks": llm_rec.get("key_risks", []),
                })
            elif llm_action == "REUNDERWRITE":
                actions_required.append({
                    "action": "REUNDERWRITE",
                    "ticker": ticker,
                    "urgency": llm_rec.get("urgency", "medium"),
                    "reason": llm_rec.get("reason", "Thesis drift detected"),
                    "detail": llm_rec.get("detail", ""),
                    "current_weight": weight,
                    "type": pos_type,
                    "pnl_pct": pnl_pct,
                    "thesis_health": thesis_health,
                    "thesis_drift": thesis_drift,
                    "expected_return": expected_return,
                    "key_risks": llm_rec.get("key_risks", []),
                })
            elif llm_action == "ADD_ON_WEAKNESS":
                type_config = position_types.get(pos_type, {})
                weight_range = type_config.get("weight_range", [3, 7])
                monitoring.append({
                    "action": "ADD_ON_WEAKNESS",
                    "ticker": ticker,
                    "urgency": "low",
                    "reason": llm_rec.get("reason", f"Below target weight ({weight:.1f}%)"),
                    "detail": llm_rec.get("detail", ""),
                    "current_weight": weight,
                    "target_range": weight_range,
                    "type": pos_type,
                    "thesis_health": thesis_health,
                    "expected_return": expected_return,
                    "key_risks": llm_rec.get("key_risks", []),
                })
            else:
                # HOLD or no LLM analysis — fall back to rules
                has_breach = any(
                    a.get("ticker") == ticker and a.get("type") in ("thesis_breach", "drawdown")
                    for a in alerts
                )
                if has_breach:
                    actions_required.append({
                        "action": "REUNDERWRITE",
                        "ticker": ticker,
                        "urgency": "medium",
                        "reason": "Key assumption breached",
                        "detail": llm_rec.get("detail", "Re-evaluate thesis before adding."),
                        "current_weight": weight,
                        "type": pos_type,
                        "pnl_pct": pnl_pct,
                        "thesis_health": thesis_health,
                        "expected_return": expected_return,
                    })
                else:
                    no_action.append({
                        "action": "HOLD",
                        "ticker": ticker,
                        "urgency": "none",
                        "reason": llm_rec.get("reason", "Thesis intact, no action needed"),
                        "detail": llm_rec.get("detail", ""),
                        "current_weight": weight,
                        "type": pos_type,
                        "pnl_pct": pnl_pct,
                        "thesis_health": thesis_health,
                        "thesis_drift": thesis_drift,
                        "expected_return": expected_return,
                        "key_risks": llm_rec.get("key_risks", []),
                    })

        # Step 3: Size new opportunities
        new_positions = []
        if approved_opps:
            update_progress("Sizing new opportunities...")
            new_positions = await self._llm_size_opportunities(
                approved_opps, holdings, constitution, config,
            )

        # Cash deployment calculation
        cash = safe_float(context.get("cash", 0))
        invested_value = sum(safe_float(h.get("market_value", 0)) for h in holdings)
        total_value = invested_value + cash
        cash_pct = round(cash / total_value * 100, 1) if total_value > 0 else 0
        trim_proceeds = sum(
            safe_float(a.get("current_weight", 0)) - safe_float(a.get("target_weight", 0))
            for a in actions_required if a["action"] == "TRIM" and a.get("target_weight")
        ) / 100 * total_value if total_value else 0

        # Risk engine check
        risk_health = {"healthy": True, "alerts": []}
        try:
            from backend.core.risk_engine import RiskGate
            risk_gate = RiskGate(constitution)
            portfolio_state = {
                "holdings": holdings,
                "cash_pct": cash_pct,
                "total_positions": len(holdings),
            }
            risk_health = risk_gate.check_portfolio_health(portfolio_state)
        except Exception as e:
            log.debug(f"Risk engine check failed: {e}")

        result_data = {
            "actions_required": actions_required,
            "monitoring": monitoring,
            "no_action": no_action,
            "new_positions": new_positions,
            "risk_health": risk_health,
            "summary": {
                "total_positions": len(holdings),
                "actions_required_count": len(actions_required),
                "monitoring_count": len(monitoring),
                "no_action_count": len(no_action),
                "new_opportunities_count": len(new_positions),
                "trim_proceeds_est": round(trim_proceeds, 2),
                "cash_available": round(cash + trim_proceeds, 2),
                "cash_pct": cash_pct,
            },
            "position_types": {
                "core": len([h for h in holdings if h.get("type") == "core"]),
                "tactical": len([h for h in holdings if h.get("type") == "tactical"]),
                "legacy": len([h for h in holdings if h.get("type") == "legacy"]),
            },
        }

        log.info(
            f"Allocator: {len(actions_required)} actions, "
            f"{len(monitoring)} monitoring, {len(no_action)} hold, "
            f"{len(new_positions)} new opportunities"
        )

        return AgentResult(
            agent=self.name, status="complete",
            event_type="complete",
            data=result_data,
            duration_s=time.time() - t0,
        )
