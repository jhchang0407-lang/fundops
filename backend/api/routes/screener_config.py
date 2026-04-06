"""Screener configuration routes.

AI-assisted strategy wizard + manual criteria editor.
"""

import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.api.deps import get_config, get_llm

router = APIRouter()
log = logging.getLogger("fundops.screener_config")

# Default screener criteria (what ships out of the box)
DEFAULT_CRITERIA = {
    "hurdle_pct": 15,
    "handoff": {
        "max_candidates": 20,
        "min_expected_return_pct": 20,
        "min_gross_margin_pct": 30,
        "max_debt_equity": 3.0,
    },
    "lenses": [
        {
            "name": "dislocation",
            "enabled": True,
            "weights": {"cheapness": 0.70, "quality": 0.15, "health": 0.10, "growth": 0.05},
        },
        {
            "name": "compounder",
            "enabled": True,
            "weights": {"quality": 0.50, "cheapness": 0.30, "growth_durability": 0.20},
        },
    ],
    "filters": {
        "min_market_cap_m": 500,
        "max_market_cap_m": 0,  # 0 = no max
        "excluded_sectors": [],
        "min_pe": 0,
        "max_pe": 100,
    },
}

WIZARD_SYSTEM_PROMPT = """You are an investment strategy advisor helping configure a stock screener.
You have a natural conversation with the user to understand their strategy, then set filters.

AVAILABLE FILTERS (you can add/remove/update these):
SIZE: min_market_cap (USD), max_market_cap (USD), min_revenue (USD), min_enterprise_value (USD), excluded_sectors (list), min_price (USD)
VALUATION: max_pe, min_pe, max_pb, max_ps, max_ev_ebitda, max_ev_revenue, max_pfcf, min_fcf_yield (%), min_earnings_yield (%), max_peg
BACKWARD DCF: max_implied_growth (%), min_growth_gap (%) — implied growth = what market prices in. Growth gap = actual minus implied.
PROFITABILITY: min_gross_margin (%), min_operating_margin (%), min_net_margin (%), min_ebitda_margin (%), min_fcf_margin (%), min_roe (%), min_roa (%), min_roic (%), allow_negative_earnings (bool)
GROWTH: min_revenue_growth_1y (%), min_revenue_growth_3y (%), min_revenue_growth_5y (%), min_eps_growth_1y (%), min_growth_consistency (%)
CASH FLOW: min_fcf_yield_pct (%), min_fcf_conversion (%), min_income_quality (ratio), max_capex_to_revenue (%), positive_fcf_required (bool)
BALANCE SHEET: max_debt_equity (ratio), max_net_debt_ebitda (ratio), min_interest_coverage (ratio), min_current_ratio (ratio)
QUALITY: min_piotroski (0-9 score), min_altman_z (score), min_quality_score (0-10)
DIVIDENDS: min_dividend_yield (%), max_payout_ratio (%), requires_dividend (bool)
SECTOR-SPECIFIC: min_nim (% bank), max_efficiency_ratio (% bank), min_rule_of_40 (tech), max_sbc_to_revenue (% tech), min_ffo_yield (% REIT)

HOW TO RESPOND:
Return a JSON object with two fields:
1. "message": your conversational response to the user (ask clarifying questions, explain what you're setting up)
2. "filter_actions": list of actions to take on filters. Each action is {"action": "add"|"remove"|"update", "key": "filter_key", "value": <value>}

If you need more info, ask a question and return empty filter_actions.
If you have enough info, set filters AND explain what you did and why.
If the user says "looks good" or "apply it", return empty filter_actions (everything is already applied).

CONVERSATION STYLE:
- Be conversational, not robotic. Ask one or two questions at a time, not five.
- When you add a filter, explain WHY in plain English ("I set min gross margin to 40% because you want pricing power")
- If the user is vague ("I want good companies"), probe: "What does 'good' mean to you? High margins? Strong balance sheet? Consistent growth?"
- Reference real investing concepts naturally.

IMPORTANT: Return ONLY valid JSON. No markdown fences. Format:
{"message": "your response text", "filter_actions": [{"action": "add", "key": "min_gross_margin", "value": 40}, ...]}
"""


@router.get("/screener/config")
async def get_screener_config():
    """Get current screener configuration."""
    config = get_config()
    scout_config = config.resolved.get("agents", {}).get("screener", {}).get("config", {})

    # Merge with defaults for any missing fields
    criteria = {**DEFAULT_CRITERIA}
    if scout_config:
        criteria["hurdle_pct"] = scout_config.get("hurdle_pct", criteria["hurdle_pct"])
        if "handoff" in scout_config:
            criteria["handoff"] = {**criteria["handoff"], **scout_config["handoff"]}
        if "lenses" in scout_config:
            criteria["lenses"] = scout_config["lenses"]
        if "filters" in scout_config:
            criteria["filters"] = {**criteria["filters"], **scout_config["filters"]}

    return {"criteria": criteria, "defaults": DEFAULT_CRITERIA}


class ScreenerConfigUpdate(BaseModel):
    criteria: dict


@router.post("/screener/config")
async def update_screener_config(body: ScreenerConfigUpdate):
    """Save screener configuration."""
    config = get_config()
    scout_config = config.resolved.setdefault("agents", {}).setdefault("screener", {}).setdefault("config", {})

    # Merge into config
    for key, val in body.criteria.items():
        scout_config[key] = val

    return {"saved": True, "criteria": body.criteria}


class WizardMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class StrategyWizardRequest(BaseModel):
    message: str
    history: list[WizardMessage] = []
    current_filters: dict = {}

    # Legacy support: if 'description' is sent instead of 'message'
    description: str = ""


@router.post("/screener/wizard")
async def strategy_wizard(body: StrategyWizardRequest):
    """Multi-turn AI strategy wizard.

    Maintains conversation history. Each response includes:
    - message: conversational AI response
    - filter_actions: add/remove/update actions to apply to active filters
    """
    user_msg = body.message or body.description
    if not user_msg.strip():
        raise HTTPException(400, "Message cannot be empty")

    llm = get_llm()
    if not llm:
        raise HTTPException(503, "AI model not configured. Set up in Settings > AI Model.")

    # Build conversation for the LLM
    messages = [{"role": "system", "content": WIZARD_SYSTEM_PROMPT}]

    # Add context about current filters
    if body.current_filters:
        filter_summary = ", ".join(f"{k}={v}" for k, v in body.current_filters.items())
        messages.append({
            "role": "system",
            "content": f"Currently active filters: {filter_summary}" if filter_summary else "No filters are currently active.",
        })

    # Add conversation history
    for msg in body.history:
        messages.append({"role": msg.role, "content": msg.content})

    # Add current user message
    messages.append({"role": "user", "content": user_msg})

    try:
        result = await llm.generate_chat(
            messages=messages,
            agent="screener_wizard",
            reasoning_effort="medium",
        )

        # Parse JSON response
        text = result.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            response = json.loads(text)
        except json.JSONDecodeError:
            # If the AI returned plain text instead of JSON, wrap it
            response = {"message": text, "filter_actions": []}

        ai_message = response.get("message", "I've updated your filters.")
        filter_actions = response.get("filter_actions", [])

        # Validate filter actions
        valid_actions = []
        for action in filter_actions:
            if isinstance(action, dict) and "action" in action and "key" in action:
                valid_actions.append({
                    "action": action["action"],
                    "key": action["key"],
                    "value": action.get("value"),
                })

        return {
            "message": ai_message,
            "filter_actions": valid_actions,
        }

    except Exception as e:
        log.error(f"AI wizard failed: {e}")
        return {
            "message": f"Sorry, I had trouble processing that. Error: {str(e)}. Try rephrasing?",
            "filter_actions": [],
        }
