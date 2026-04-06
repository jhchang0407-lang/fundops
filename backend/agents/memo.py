"""Memo Agent — Full deep-dive analysis.

Two modes:
- Research Report: 13-section company deep-dive (no valuation section)
- Investment Memo: 4-section buy thesis with valuation + return decomposition

Both share the same data layer. Memo is the most expensive agent (~$1/run).

Emits event_type="complete" with memo content in result.data.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import re as _re

from backend.agents import AgentPlugin, AgentResult


def _normalize_money_prose(text: str) -> str:
    """Normalize dollar amounts in prose for consistency.

    Converts e.g. '$200,966M' → '$201.0B', '$1,500B' → '$1.5T'.
    Leaves amounts already in appropriate units alone.
    """
    def _replace(m: _re.Match) -> str:
        sign = m.group(1) or ""
        num_str = m.group(2).replace(",", "")
        unit = m.group(3).upper()
        try:
            val = float(num_str)
        except ValueError:
            return m.group(0)

        # Convert to raw dollars
        multipliers = {"M": 1e6, "B": 1e9, "T": 1e12}
        raw = val * multipliers.get(unit, 1)

        # Format in the most readable unit
        if raw >= 1e12:
            formatted = raw / 1e12
            u = "T"
        elif raw >= 1e9:
            formatted = raw / 1e9
            u = "B"
        elif raw >= 1e6:
            formatted = raw / 1e6
            u = "M"
        else:
            return m.group(0)

        # Clean trailing zeros: 201.0B → $201B, 59.9B → $59.9B
        if formatted == int(formatted):
            return f"{sign}${int(formatted)}{u}"
        elif formatted * 10 == int(formatted * 10):
            return f"{sign}${formatted:.1f}{u}"
        else:
            return f"{sign}${formatted:.2f}{u}"

    # Match patterns like $200,966M, $59.893B, -$1.5T
    return _re.sub(
        r"(-?)\$([0-9,]+(?:\.[0-9]+)?)\s*([MBTmbt])\b",
        _replace,
        text,
    )
from backend.core.prose_spec import MEMO_RESEARCH_SPEC, MEMO_INVESTMENT_SPEC
from backend.core.prose_prompt import build_prose_system_prompt
from backend.core.prose_validate import clean_prose

log = logging.getLogger("fundops.memo")


class MemoAgent(AgentPlugin):
    """Full deep-dive analysis agent."""

    name = "memo"
    description = "Full deep-dive analysis (research + investment modes)"

    def __init__(self, config: dict = None, fmp=None, sec=None, yfinance=None,
                 llm=None, web_search=None, db=None):
        super().__init__(config)
        self.fmp = fmp
        self.sec = sec
        self.yfinance = yfinance
        self.llm = llm
        self.web_search = web_search
        self.db = db

    def _build_strategy_lens(self, strategy: dict | None) -> str:
        """Build a strategy-aware lens directive for memo prompts.

        Adapts the analysis emphasis based on the user's strategy profile.
        Same backbone structure, different focus per section.
        """
        if not strategy:
            return ""

        north_star = strategy.get("north_star", "")
        dims = strategy.get("dimensions", {})
        if not north_star and not dims:
            return ""

        parts = ["\n--- STRATEGY LENS ---"]
        if north_star:
            parts.append(f"Investment philosophy: {north_star}")

        # Map dimensions to analysis directives
        if dims.get("cheapness") or dims.get("cheapness_valuation"):
            val_pref = dims.get("cheapness") or dims.get("cheapness_valuation")
            parts.append(f"Valuation emphasis: {val_pref}")
        if dims.get("quality") or dims.get("roic_quality") or dims.get("margin_quality"):
            qual_pref = dims.get("quality") or dims.get("roic_quality") or dims.get("margin_quality")
            parts.append(f"Quality emphasis: {qual_pref}")
        if dims.get("growth"):
            parts.append(f"Growth perspective: {dims['growth']}")
        if dims.get("risk"):
            parts.append(f"Risk tolerance: {dims['risk']}")
        if dims.get("momentum_signal"):
            parts.append(f"Momentum/technical emphasis: {dims['momentum_signal']}")
        if dims.get("catalyst_type"):
            parts.append(f"Catalyst focus: {dims['catalyst_type']}")

        # Inject ALL constitution dimensions as specific directives
        # (covers arbitrary user-defined dimensions beyond the hardcoded set above)
        _handled = {"cheapness", "cheapness_valuation", "quality", "roic_quality",
                     "margin_quality", "growth", "risk", "momentum_signal", "catalyst_type"}
        if not isinstance(dims, dict):
            dims = {}
        extra_dims = {k: v for k, v in dims.items() if k not in _handled and v}
        if extra_dims:
            parts.append("Additional investor focus areas:")
            for dim_name, dim_desc in extra_dims.items():
                label = dim_name.replace("_", " ").title()
                parts.append(f"  - {label}: {str(dim_desc) if not isinstance(dim_desc, str) else dim_desc}")

        parts.append("Adapt your analysis emphasis to match this strategy. Spend more words on the dimensions this investor cares about most.")
        parts.append("--- END STRATEGY LENS ---")
        return "\n".join(parts)

    async def _extract_section_structured_data(
        self, section_title: str, content: str, budget_so_far: float,
    ) -> dict | None:
        """Extract structured data from investment memo section prose.

        Uses the investment extraction schema to pull key findings,
        scores, and structured data from free-form section content.
        Returns None if no schema matches or extraction fails.
        """
        if not self.llm or not content or len(content.split()) < 30:
            return None

        from backend.memo.schemas import get_investment_extraction_schema
        schema = get_investment_extraction_schema(section_title)
        if not schema:
            return None

        import json as _json

        # Build extraction prompt
        props = schema.get("properties", {})
        field_descriptions = []
        for field_name, field_def in props.items():
            desc = field_def.get("description", "")
            ftype = field_def.get("type", "string")
            if ftype == "array":
                field_descriptions.append(f'  "{field_name}": [...] // {desc}')
            elif ftype == "object":
                field_descriptions.append(f'  "{field_name}": {{...}} // {desc}')
            elif ftype == "number" or ftype == "integer":
                field_descriptions.append(f'  "{field_name}": <number> // {desc}')
            else:
                field_descriptions.append(f'  "{field_name}": "<string>" // {desc}')

        prompt = f"""Extract structured data from this investment memo section.

SECTION: {section_title}

CONTENT:
{content[:3000]}

Return a JSON object with these fields:
{{
{chr(10).join(field_descriptions)}
}}

Extract values directly from the text. Use null for any field not mentioned.
Return ONLY the JSON object — no markdown fences, no explanation."""

        try:
            import asyncio as _aio
            result = await _aio.wait_for(
                self.llm.generate(
                    prompt=prompt,
                    agent="memo_investment",
                    system="You are a data extraction assistant. Return only valid JSON.",
                    reasoning_effort="low",
                ),
                timeout=30.0,
            )
            text = (result.text or "").strip()
            # Strip markdown fences
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            text = text.strip()
            parsed = _json.loads(text)
            return {"data": parsed, "cost": result.cost}
        except Exception as e:
            log.warning(f"Investment memo extraction failed for '{section_title}': {e}")
            return None

    def _build_constitution_section_lens(self, section_title: str, strategy: dict | None) -> str:
        """Build dimension-specific directives for a particular memo section.

        Maps constitution dimensions to sections where they are most relevant,
        so each section gets targeted emphasis rather than the full generic lens.
        """
        if not strategy:
            return ""
        dims = strategy.get("dimensions", {})
        if not dims:
            return ""

        # Map section titles to relevant dimension keys
        _section_dim_map = {
            "Executive Summary": None,  # gets the full lens
            "Company Overview": None,
            "History & Milestones": None,
            "Product & Technology": ["moat", "value_creation", "innovation", "technology"],
            "Competitive Moats": ["moat", "value_creation", "quality", "roic_quality", "margin_quality", "switching_costs"],
            "Industry Dynamics": ["competitive_intensity", "industry", "market_structure"],
            "Customer Analysis": ["customer", "retention", "switching_costs", "network_effects"],
            "Management & Capital Allocation": ["capital_allocation", "management", "governance", "insider_ownership"],
            "Growth Prospects": ["growth", "reinvestment", "tam", "value_creation"],
            "Financial Analysis": ["quality", "roic_quality", "margin_quality", "cheapness", "cheapness_valuation", "fcf", "earnings_quality"],
            "Peer Benchmarking": ["cheapness", "cheapness_valuation", "quality", "roic_quality"],
            "Risk Assessment": ["risk", "downside", "trap_risk", "leverage"],
            "Key Takeaways": None,
            # Investment memo sections
            "Opportunity Brief": ["cheapness", "cheapness_valuation", "catalyst_type", "value_creation"],
            "Valuation Analysis": ["cheapness", "cheapness_valuation", "growth", "margin_expansion"],
            "Financial Quality": ["quality", "roic_quality", "margin_quality", "fcf", "earnings_quality"],
            "Risks & Bear Case": ["risk", "downside", "trap_risk", "leverage"],
        }

        relevant_keys = _section_dim_map.get(section_title)
        if relevant_keys is None:
            return ""  # section gets the full strategy lens, no extra section-specific directives

        # Find matching dimensions (exact key match or substring match)
        matched = []
        for dim_key, dim_desc in dims.items():
            if not dim_desc:
                continue
            if dim_key in relevant_keys or any(rk in dim_key for rk in relevant_keys):
                label = dim_key.replace("_", " ").title()
                matched.append(f"- {label}: {dim_desc}")

        if not matched:
            return ""

        return "\n".join([
            "INVESTOR FOCUS AREAS (emphasize these in this section):",
            *matched,
        ])

    async def run(self, context: dict) -> AgentResult:
        """Generate memo for a ticker.

        Args:
            context: Must contain "ticker". Optional "mode": "research"|"investment"|"both".
                     Optional "strategy": dict with north_star, dimensions, sector_routing.
        """
        t0 = time.time()
        ticker = context.get("ticker", "").upper()
        mode = context.get("mode", "research")

        # Strategy context: use constitution first, fall back to strategy_profiles
        constitution = context.get("constitution")
        self._strategy = context.get("strategy")
        if not self._strategy and constitution:
            self._strategy = {
                "north_star": constitution.get("north_star", ""),
                "dimensions": constitution.get("dimensions", {}),
                "sector_routing": constitution.get("sector_routing", {}),
            }
        if not self._strategy and self.db:
            try:
                from backend.core.db_v2 import ScreenerV2DB
                v2db = ScreenerV2DB(db_path=self.db.db_path if hasattr(self.db, 'db_path') else None)
                active_constitution = v2db.get_active_constitution()
                v2db.close()
                if active_constitution:
                    self._strategy = {
                        "north_star": active_constitution.get("north_star", ""),
                        "dimensions": active_constitution.get("dimensions", {}),
                        "sector_routing": active_constitution.get("sector_routing", {}),
                    }
            except Exception as e:
                log.debug(f"Could not fetch constitution for memo lens: {e}")

        if not ticker:
            return AgentResult(
                agent=self.name, status="failed",
                errors=["No ticker provided"],
                duration_s=time.time() - t0,
            )

        log.info(f"Generating {mode} memo for {ticker}...")

        # Step 1: Fetch all data (shared between both modes)
        from backend.memo.data_fetcher import fetch_pipeline_data
        data = await fetch_pipeline_data(
            ticker, fmp=self.fmp, sec=self.sec, yfinance=self.yfinance,
        )

        # Check data quality — abort if we don't have enough to write a real memo
        coverage = data.data_coverage_report()
        if not data.has_minimum_viable_data:
            missing = ", ".join(coverage["missing"][:4])
            errors = coverage["fetch_errors"]
            log.warning(f"Insufficient data for {ticker} memo. Missing: {missing}. Errors: {errors}")
            return AgentResult(
                agent=self.name,
                ticker=ticker,
                status="failed",
                errors=[
                    f"Insufficient data to generate a reliable memo for {ticker}.",
                    f"Missing: {missing}.",
                    "Add FMP API key in Settings for richer data, or try again when market is open.",
                ] + (errors or []),
                duration_s=time.time() - t0,
            )

        if coverage["warnings"]:
            log.warning(f"Data warnings for {ticker}: {coverage['warnings']}")

        # Step 2: Run market research (shared)
        market_intel = {}
        if self.web_search:
            from backend.memo.market_research import fetch_market_intelligence
            market_intel = await fetch_market_intelligence(
                ticker=ticker,
                company_name=data.profile.name,
                sector=data.profile.sector,
                web_search=self.web_search,
            )

        # Step 3: Run valuation (shared, deterministic)
        valuation = await self._run_valuation(ticker, data)

        # Step 4: Generate memo based on mode
        results = {}
        if mode in ("research", "both"):
            results["research"] = await self._generate_research(
                ticker, data, market_intel, valuation,
            )

        if mode in ("investment", "both"):
            results["investment"] = await self._generate_investment(
                ticker, data, market_intel, valuation,
            )

        # Step 5: Store in DB
        total_cost = sum(r.get("cost", 0) for r in results.values())

        if self.db:
            try:
                for doc_type, memo in results.items():
                    self.db.record_run(
                        agent=self.name,
                        ticker=ticker,
                        run_type=doc_type,
                        fair_value=valuation.get("fair_value"),
                        scores={"quality_score": memo.get("quality_score", 0)},
                        summary=f"{doc_type} memo, {len(memo.get('content', ''))} chars, ${total_cost:.2f}",
                        full_output=memo,
                    )
            except Exception as e:
                log.warning(f"DB write failed: {e}")

        elapsed = time.time() - t0
        log.info(f"Memo {ticker} ({mode}): {elapsed:.1f}s, ${total_cost:.2f}")

        return AgentResult(
            agent=self.name,
            ticker=ticker,
            status="complete",
            event_type="complete",
            data={
                "ticker": ticker,
                "mode": mode,
                "results": results,
                "valuation": valuation,
                "market_intel_available": market_intel.get("_available", False),
                "cost": total_cost,
                "duration_s": elapsed,
            },
            duration_s=elapsed,
        )

    async def _run_valuation(self, ticker: str, data) -> dict:
        """Run sector-appropriate valuation model (DCF / financial-peer P/E / industry-peer EV/EBITDA)."""
        try:
            from backend.memo.valuation.industry_config import detect_valuation_mode
            from backend.memo.valuation.dcf import DCFAnchors, run_dcf

            annual = data.financials_annual
            if not annual:
                return {"fair_value": 0, "method": "none", "error": "No financial data"}

            latest = annual[0] if annual else {}
            prev = annual[1] if len(annual) > 1 else {}

            revenue = latest.get("revenue", 0) or 0
            net_income = latest.get("netIncome", 0) or 0
            ebitda = latest.get("ebitda", 0) or 0
            fcf = latest.get("freeCashFlow", 0) or 0
            total_debt = latest.get("totalDebt", 0) or 0
            cash = latest.get("cashAndCashEquivalents", 0) or 0
            shares = latest.get("weightedAverageShsOutDil", 0) or 0
            price = (data.market_data or {}).get("price", 0) or 0
            mkt_cap = (data.market_data or {}).get("marketCap", 0) or 0

            if not shares:
                return {"fair_value": 0, "method": "none", "error": "Missing shares data"}

            # Detect valuation mode from industry + SIC code
            industry = (data.profile.industry or "") if data.profile else ""
            sic_code = (data.profile.sic_code or "") if data.profile else ""
            mode, config = detect_valuation_mode(industry, str(sic_code))

            # ── Financial Peer (banks, insurance, asset managers) ──
            # EV is meaningless; use P/E or P/B with sector-appropriate multiples
            if mode == "financial_peer":
                eps = net_income / shares if shares else 0
                # Asset managers / capital markets: target P/E ~20x (fee-based premium)
                # Banks / insurance: target P/E ~12–15x (regulated, capital-constrained)
                ind_lower = industry.lower()
                if any(w in ind_lower for w in ("asset", "capital market", "wealth", "exchange", "brokerage")):
                    target_pe = 20.0
                    method_label = "pe_asset_manager"
                    rationale = f"Asset manager valued on P/E ({target_pe}x) — fee & AUM-based earnings, DCF EV meaningless"
                elif any(w in ind_lower for w in ("bank", "thrift", "mortgage", "credit")):
                    target_pe = 13.0
                    method_label = "pe_bank"
                    rationale = f"Bank/credit valued on P/E ({target_pe}x) — NIM-driven earnings, EV not applicable"
                elif any(w in ind_lower for w in ("insurance", "reinsur")):
                    target_pe = 14.0
                    method_label = "pe_insurance"
                    rationale = f"Insurer valued on P/E ({target_pe}x) — combined ratio + float, DCF inappropriate"
                else:
                    target_pe = 15.0
                    method_label = "pe_financial"
                    rationale = f"Financial company valued on P/E ({target_pe}x) — EV/EBITDA not meaningful"

                fair_value = eps * target_pe if eps > 0 else 0
                # Cross-check: if we have market cap and revenue, add AUM/revenue multiple context
                rev_multiple = mkt_cap / revenue if revenue else 0

                return {
                    "fair_value": round(fair_value, 2),
                    "method": method_label,
                    "industry": industry,
                    "valuation_mode": "financial_peer",
                    "eps": round(eps, 2),
                    "target_pe": target_pe,
                    "revenue_multiple": round(rev_multiple, 2),
                    "rationale": rationale,
                    "assumptions": {
                        "method": method_label,
                        "target_pe": target_pe,
                        "eps": eps,
                        "note": "DCF skipped — financial institution where EV is not meaningful",
                    },
                }

            # ── Industry Peer (commodity/cyclical/regulated) ──
            # Use EV/EBITDA multiple; DCF FCF projections are unreliable
            if mode == "industry_peer" and config:
                if ebitda > 0 and shares > 0:
                    net_debt = total_debt - cash
                    ev = mkt_cap + net_debt if mkt_cap else 0
                    ev_ebitda = ev / ebitda if ebitda else 0

                    # Sector median EV/EBITDA targets
                    ind_lower = industry.lower()
                    if any(w in ind_lower for w in ("oil", "gas", "energy", "mining", "gold", "coal", "metal")):
                        target_ev_ebitda = 7.0
                    elif any(w in ind_lower for w in ("airline", "transport")):
                        target_ev_ebitda = 8.0
                    elif any(w in ind_lower for w in ("utilit", "regulated")):
                        target_ev_ebitda = 12.0
                    elif any(w in ind_lower for w in ("reit",)):
                        target_ev_ebitda = 18.0
                    else:
                        target_ev_ebitda = 9.0

                    implied_ev = ebitda * target_ev_ebitda
                    implied_equity = implied_ev - net_debt
                    fair_value = implied_equity / shares if shares > 0 else 0

                    return {
                        "fair_value": round(max(0, fair_value), 2),
                        "method": "ev_ebitda",
                        "industry": industry,
                        "valuation_mode": "industry_peer",
                        "ebitda": round(ebitda / 1e6, 1),
                        "target_ev_ebitda": target_ev_ebitda,
                        "current_ev_ebitda": round(ev_ebitda, 1),
                        "rationale": config.rationale if config else "EV/EBITDA used for cyclical/commodity industry",
                        "assumptions": {
                            "method": "ev_ebitda",
                            "target_multiple": target_ev_ebitda,
                            "ebitda_m": round(ebitda / 1e6, 1),
                            "net_debt_m": round(net_debt / 1e6, 1),
                            "note": config.rationale if config else "",
                        },
                    }

            # ── Standard DCF (tech, consumer, healthcare, industrials) ──
            if not revenue or not shares:
                return {"fair_value": 0, "method": "none", "error": "Missing revenue or shares for DCF"}

            prev_rev = prev.get("revenue", revenue) or revenue
            growth = (revenue - prev_rev) / prev_rev if prev_rev else 0.05
            fcf_margin = fcf / revenue if revenue else 0.1

            anchors = DCFAnchors(
                revenue_latest=revenue,
                fcf_margin=max(0.05, fcf_margin),
                revenue_growth=max(0.02, min(0.30, growth)),
                net_debt=total_debt - cash,
                shares_diluted=shares,
                wacc=0.10,
                terminal_growth=0.025,
            )

            result = run_dcf(anchors)

            return {
                "fair_value": result.fair_value_per_share or 0,
                "method": "dcf",
                "industry": industry,
                "valuation_mode": "dcf",
                "enterprise_value": result.enterprise_value or 0,
                "assumptions": result.assumptions,
                "sensitivity": result.sensitivity_table[:3] if result.sensitivity_table else [],
            }

        except Exception as e:
            log.warning(f"Valuation failed for {ticker}: {e}")
            return {"fair_value": 0, "method": "failed", "error": str(e)}

    def _build_data_constraints(self, coverage: dict) -> str:
        """Build a data constraints block injected into every prompt.

        This tells the AI exactly what data it has so it cannot fabricate figures
        for fields that weren't fetched. Critical for memo quality control.
        """
        lines = ["## DATA AVAILABILITY (HARD CONSTRAINTS)"]
        lines.append(f"Overall coverage: {coverage['overall'].upper()}")
        if coverage["available"]:
            lines.append("Available: " + "; ".join(coverage["available"]))
        if coverage["missing"]:
            lines.append("NOT available (do NOT fabricate): " + "; ".join(coverage["missing"]))
        if coverage["warnings"]:
            lines.append("Warnings: " + "; ".join(coverage["warnings"]))
        lines.append("")
        lines.append("RULES: Only use numbers from the data provided. If a metric is listed as NOT available, "
                     "state explicitly that the data was not available rather than estimating or fabricating. "
                     "Sections that rely on missing data should be shorter and clearly note the data gap.")
        return "\n".join(lines)

    async def _generate_research(self, ticker: str, data, market_intel: dict, valuation: dict) -> dict:
        """Generate research report (14 sections, structured JSON output per section).

        Body sections (S2–S13) use structured JSON schemas embedded in the prompt.
        The LLM returns a JSON object; we parse it and render it to markdown using
        the section renderer. Falls back to raw text if JSON parsing fails.

        Synthesis sections (Executive Summary, Key Takeaways) use free-form text
        since they depend on the full body and don't benefit from a fixed schema.
        """
        from backend.memo.schemas import get_section_schema, build_json_schema_prompt
        from backend.memo.renderer import render_section_to_markdown

        if not self.llm:
            return {"content": "LLM not configured", "sections": [], "cost": 0}

        # Build context for the LLM
        filing_context = ""
        if data.filing_text:
            from backend.core.sec.filings import build_agent_context
            tenk = data.filing_text.get("10k", {})
            tenq = data.filing_text.get("10q", {})
            filing_context = build_agent_context(tenk, tenq, max_chars=60000)

        coverage = data.data_coverage_report()
        data_constraints = self._build_data_constraints(coverage)

        # Build financial snapshot for context
        annual = data.financials_annual or []
        latest = annual[0] if annual else {}
        prev = annual[1] if len(annual) > 1 else {}
        rev = latest.get("revenue", 0) or 0
        prev_rev = prev.get("revenue", rev) or rev
        rev_growth = ((rev - prev_rev) / prev_rev * 100) if prev_rev else 0
        gm = latest.get("grossProfitRatio") or latest.get("grossMargin") or 0
        op_margin = latest.get("operatingIncomeRatio") or latest.get("operatingMargin") or 0
        net_margin = latest.get("netProfitMargin") or latest.get("netIncomeRatio") or 0
        # Ratios may be stored as 0–1 decimals
        if gm and abs(gm) <= 1: gm *= 100
        if op_margin and abs(op_margin) <= 1: op_margin *= 100
        if net_margin and abs(net_margin) <= 1: net_margin *= 100
        price = (data.market_data or {}).get("price", 0) or 0
        fv = valuation.get("fair_value", 0) or 0

        val_method = valuation.get("method", "dcf")
        val_label = {
            "dcf": "DCF fair value",
            "pe_asset_manager": "P/E fair value (asset mgr)",
            "pe_bank": "P/E fair value (bank)",
            "pe_insurance": "P/E fair value (insurer)",
            "pe_financial": "P/E fair value",
            "ev_ebitda": "EV/EBITDA fair value",
            "bank_equity": "Bank equity fair value",
        }.get(val_method, "Fair value")

        fin_snapshot = (
            f"Key financials (latest annual):\n"
            f"- Revenue: ${rev/1e6:.0f}M | YoY growth: {rev_growth:.1f}%\n"
            f"- Gross margin: {gm:.1f}% | Operating margin: {op_margin:.1f}% | Net margin: {net_margin:.1f}%\n"
            f"- Current price: ${price:.2f} | {val_label}: ${fv:.2f}\n"
            f"- Sector: {data.profile.sector} | Industry: {data.profile.industry}"
        )

        mi_context = market_intel.get("opportunity_risk") or market_intel.get("summary") or "N/A"
        company = data.profile.name or ticker
        sector = (data.profile.sector or "") if data.profile else ""
        industry = (data.profile.industry or "") if data.profile else ""

        # Body sections: section_num → display title
        # Section numbers match the old pipeline (S2–S13, skipping S12 which is valuation-only)
        body_section_nums = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13]

        section_outputs = []
        total_cost = 0

        # Research report uses fixed schemas — system prompt is straightforward
        sys_prompt = (
            f"You are a senior sell-side equity research analyst writing a structured research report on {company} ({ticker}). "
            f"Write in a factual, evidence-based analytical tone. Use specific numbers from the data provided. "
            f"Do NOT write investment recommendations, price targets, or buy/sell advice. "
            f"Do NOT reference the analyst's personal strategy or portfolio. "
            f"This is a pure research document — describe the company objectively.\n\n"
            f"OUTPUT FORMAT: You must return a valid JSON object matching the schema provided. "
            f"Do not wrap the JSON in markdown code fences. Return raw JSON only. "
            f"All string values must be complete analytical prose — not placeholders.\n\n"
            f"{data_constraints}"
        )

        # Generate body sections using structured JSON output
        for section_num in body_section_nums:
            schema = get_section_schema(section_num, sector=sector, industry=industry)
            if not schema:
                continue

            section_title = schema["title"]
            word_target = schema.get("word_target", 500)
            fields = schema.get("fields", [])
            json_schema_block = build_json_schema_prompt(schema)

            prompt = (
                f"{fin_snapshot}\n\n"
                f"{data_constraints}\n\n"
                f"Filing context (10-K/10-Q excerpts):\n{filing_context[:10000]}\n\n"
                f"Market intelligence:\n{mi_context[:2000]}\n\n"
                f"TASK — Write Section: {section_title} for {company} ({ticker})\n\n"
                f"Target length: ~{word_target} words of analytical prose across all fields.\n"
                f"Use specific numbers. Do not fabricate data not in the provided context.\n\n"
                f"{json_schema_block}"
            )

            try:
                result = await self.llm.generate(
                    prompt=prompt,
                    agent="memo_research",
                    system=sys_prompt,
                    reasoning_effort="medium",
                )
                raw_text = result.text or ""
                total_cost += result.cost

                # Parse JSON response
                structured = None
                try:
                    # Strip markdown fences if the model wrapped it anyway
                    clean = raw_text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("```", 2)[-1] if clean.count("```") >= 2 else clean
                        # Remove language tag if present (```json\n...)
                        if "\n" in clean:
                            first_line, rest = clean.split("\n", 1)
                            if first_line.strip().lower() in ("json", ""):
                                clean = rest
                        if clean.endswith("```"):
                            clean = clean[:-3]
                    structured = json.loads(clean)
                except (json.JSONDecodeError, ValueError) as parse_err:
                    log.warning(
                        f"JSON parse failed for section {section_num} ({section_title}): {parse_err}. "
                        f"Falling back to raw text."
                    )

                if structured and isinstance(structured, dict):
                    # ── Validate structured output against schema ──
                    from backend.memo.validate import validate_section_json, build_retry_prompt
                    is_valid, val_errors = validate_section_json(structured, fields, section_title)

                    if not is_valid:
                        log.info(f"Section {section_num} ({section_title}) validation failed ({len(val_errors)} errors), retrying...")
                        retry_prompt = build_retry_prompt(prompt, val_errors)
                        try:
                            retry_result = await self.llm.generate(
                                prompt=retry_prompt,
                                agent="memo_research",
                                system=sys_prompt,
                                reasoning_effort="low",
                            )
                            total_cost += retry_result.cost
                            retry_text = (retry_result.text or "").strip()
                            # Strip markdown fences
                            if retry_text.startswith("```"):
                                retry_text = retry_text.split("```", 2)[-1] if retry_text.count("```") >= 2 else retry_text
                                if "\n" in retry_text:
                                    fl, rest = retry_text.split("\n", 1)
                                    if fl.strip().lower() in ("json", ""):
                                        retry_text = rest
                                if retry_text.endswith("```"):
                                    retry_text = retry_text[:-3]
                            retry_structured = json.loads(retry_text)
                            is_valid_retry, retry_errors = validate_section_json(retry_structured, fields, section_title)
                            if is_valid_retry:
                                structured = retry_structured
                                log.info(f"Section {section_num} retry passed validation")
                            else:
                                log.warning(f"Section {section_num} retry still failed: {retry_errors[:2]}")
                        except Exception as retry_err:
                            log.warning(f"Section {section_num} retry failed: {retry_err}")

                    # Render structured JSON to markdown
                    content = render_section_to_markdown(
                        section_title=section_title,
                        structured=structured,
                        fields=fields,
                    )
                    source = "structured"
                else:
                    # Fallback: use raw LLM text as-is
                    content = raw_text
                    source = "fallback_raw"

                word_count = len(content.split())
                quality_flag = None
                if word_count < 80:
                    quality_flag = f"short ({word_count} words)"
                elif any(phrase in content.lower() for phrase in [
                    "i don't have access", "i cannot provide", "unable to access",
                ]):
                    quality_flag = "model flagged data gap"

                section_outputs.append({
                    "title": section_title,
                    "section_num": section_num,
                    "content": content,
                    "cost": result.cost,
                    "word_count": word_count,
                    "source": source,
                    **({"quality_flag": quality_flag} if quality_flag else {}),
                })

            except Exception as e:
                log.warning(f"Section {section_num} ({section_title}) generation failed: {e}")
                section_outputs.append({
                    "title": section_title,
                    "section_num": section_num,
                    "content": f"[Section generation failed: {e}]",
                    "cost": 0,
                    "word_count": 0,
                    "source": "error",
                    "quality_flag": "error",
                })

        # ── Fact-check all body sections against known financial data ──
        try:
            from backend.memo.fact_check import fact_check_section, cross_section_coherence_check
            fact_sheet = {
                "financials_annual": data.financials_annual or [],
                "financials_quarterly": data.financials_quarterly or [],
                "market_data": data.market_data or {},
                "ratios": data.ratios or {},
                "key_metrics": data.key_metrics or [],
            }
            total_violations = 0
            for sec in section_outputs:
                violations = fact_check_section(sec["content"], fact_sheet)
                if violations:
                    sec["_fact_check"] = {"violations": violations, "count": len(violations)}
                    total_violations += len(violations)
                    log.info(f"Fact-check {sec['title']}: {len(violations)} violation(s)")

            # Cross-section coherence
            section_texts = {s["title"]: s["content"] for s in section_outputs}
            coherence_warnings = cross_section_coherence_check(section_texts)
            if coherence_warnings:
                log.info(f"Cross-section coherence: {len(coherence_warnings)} warning(s)")
        except Exception as fc_err:
            log.warning(f"Fact-check step failed: {fc_err}")
            total_violations = 0
            coherence_warnings = []

        # Build body text for synthesis sections
        body_text = "\n\n".join(
            f"## {s['title']}\n{s['content']}" for s in section_outputs
        )

        # Synthesis sections written after body: Executive Summary (S1) and Key Takeaways (S14)
        # These use free-form text (no schema) since they synthesize the full body
        synthesis_sections = [
            ("Executive Summary & Investment Thesis",
             f"Based on the full research report body below, write an Executive Summary for {company} ({ticker}).\n\n"
             f"Required subsections (use ### for each):\n"
             f"### Company Snapshot — 2–3 sentence description of what the company does and its scale\n"
             f"### Key Financials — a compact table: | Metric | Value | with rows for Revenue, Growth %, Gross Margin, Op Margin, Market Cap, and the model fair value (${fv:.2f} via {val_method})\n"
             f"### Business Strengths — bullet list of the 3 most important competitive advantages\n"
             f"### Key Risks — bullet list of the 2–3 most important risks\n"
             f"### Analyst Watch List — bullet list of 3–4 specific metrics/events to monitor\n\n"
             f"Research-neutral — no buy/sell language. 400–500 words.\n\nFull report body:\n{body_text[:8000]}"),

            ("Key Takeaways",
             f"Write a Conclusion section for the {company} ({ticker}) research report.\n\n"
             f"Required subsections (use ### for each):\n"
             f"### Summary Verdict — one tight paragraph: business quality, financial health, competitive position\n"
             f"### What Would Change the View — bullet list of 3–4 specific conditions that would improve or worsen the assessment\n"
             f"### Key Indicators to Monitor — bullet list of 4–6 specific data points, filings events, or milestones to watch\n\n"
             f"Research-neutral tone. 300–400 words.\n\nFull report body:\n{body_text[:6000]}"),
        ]

        synthesis_sys_prompt = (
            f"You are a senior sell-side equity research analyst writing a structured research report on {company} ({ticker}). "
            f"Write in a factual, evidence-based tone. Use markdown throughout — ### headers, bold key terms, bullet lists.\n"
            f"Do NOT write investment recommendations, price targets, or buy/sell advice. "
            f"Do NOT repeat the section title at the top of your response."
        )

        for title, synthesis_prompt in synthesis_sections:
            try:
                result = await self.llm.generate(
                    prompt=synthesis_prompt,
                    agent="memo_research",
                    system=synthesis_sys_prompt,
                    reasoning_effort="medium",
                )
                content = result.text or ""
                section_outputs.append({
                    "title": title,
                    "content": content,
                    "cost": result.cost,
                    "word_count": len(content.split()),
                    "source": "synthesis",
                    "synthesis": True,
                })
                total_cost += result.cost
            except Exception as e:
                log.warning(f"Synthesis section '{title}' failed: {e}")
                section_outputs.append({
                    "title": title,
                    "content": f"[Section generation failed: {e}]",
                    "cost": 0,
                    "word_count": 0,
                    "source": "error",
                    "quality_flag": "error",
                })

        # Re-order: Executive Summary first, Key Takeaways last, body in between
        exec_summary = next((s for s in section_outputs if s["title"] == "Executive Summary & Investment Thesis"), None)
        key_takeaways = next((s for s in section_outputs if s["title"] == "Key Takeaways"), None)
        body_only = [s for s in section_outputs if s not in (exec_summary, key_takeaways)]
        ordered = ([exec_summary] if exec_summary else []) + body_only + ([key_takeaways] if key_takeaways else [])

        # Assemble full report
        cov = coverage
        coverage_header = (
            f"*Data coverage: {cov['overall']}. "
            f"{len(cov['available'])} sources available"
            + (f"; {len(cov['missing'])} missing: {', '.join(cov['missing'][:3])}" if cov['missing'] else "")
            + ".*\n\n"
        )
        flagged = [s["title"] for s in ordered if s.get("quality_flag")]

        full_content = f"# {company} ({ticker}) — Research Report\n\n{coverage_header}"
        for i, sec in enumerate(ordered, 1):
            sec["content"] = _normalize_money_prose(sec["content"])
            full_content += f"## {i}. {sec['title']}\n\n{sec['content']}\n\n"

        return {
            "type": "research",
            "content": full_content,
            "sections": ordered,
            "section_count": len(ordered),
            "word_count": len(full_content.split()),
            "flagged_sections": flagged,
            "data_coverage": cov,
            "fact_check": {
                "violations": total_violations,
                "coherence_warnings": len(coherence_warnings),
            },
            "cost": total_cost,
        }

    async def _generate_investment(self, ticker: str, data, market_intel: dict, valuation: dict) -> dict:
        """Generate investment memo (4 sections with valuation)."""
        if not self.llm:
            return {"content": "LLM not configured", "sections": [], "cost": 0}

        company = data.profile.name or ticker
        strategy_lens = self._build_strategy_lens(getattr(self, '_strategy', None))
        price = 0
        if data.market_data:
            price = data.market_data.get("price", 0)

        fv = valuation.get("fair_value", 0)
        discount = ((fv - price) / fv * 100) if fv > 0 and price > 0 else 0

        coverage = data.data_coverage_report()
        data_constraints = self._build_data_constraints(coverage)

        val_method_label = valuation.get("method", "dcf").replace("_", " ").upper()
        strategy_lens = self._build_strategy_lens(getattr(self, '_strategy', None)) if hasattr(self, '_strategy') else ""
        inv_sys_prompt = build_prose_system_prompt(
            MEMO_INVESTMENT_SPEC,
            company=company,
            ticker=ticker,
            data_constraints=self._build_data_constraints(coverage),
            strategy_lens=strategy_lens,
        )

        sections = [
            ("Opportunity Brief", f"""Write the Opportunity Brief section for {company} ({ticker}).

**Price:** ${price:.2f} | **Fair Value:** ${fv:.2f} ({val_method_label}) | **Discount:** {discount:.0f}%

Required subsections (use ### for each):
### The Setup — why is this stock dislocated or undervalued right now? What does the market misunderstand?
### Variant View — what does this analyst believe that consensus doesn't? Be specific.
### Key Business Strengths — bullet list of 3–4 durable competitive advantages
### Investment Snapshot — a compact table:
| Metric | Value |
|---|---|
| Current Price | ${price:.2f} |
| Fair Value ({val_method_label}) | ${fv:.2f} |
| Upside | {discount:.0f}% |
| Sector | {data.profile.sector} |

Market context: {market_intel.get('opportunity_risk', 'N/A')[:2000]}
{strategy_lens}
{data_constraints}"""),

            ("Valuation Analysis", f"""Write the Valuation Analysis section for {company} ({ticker}).

Valuation method: {val_method_label}. Model fair value: ${fv:.2f}.
Model assumptions: {json.dumps(valuation.get('assumptions', {}), default=str)[:800]}

Required subsections (use ### for each):
### Base Case Valuation — explain the model inputs, key assumptions, and resulting fair value
### Scenario Analysis — use a table:
| Scenario | Key Assumption | Fair Value | Upside |
|---|---|---|---|
| Bull | (higher growth/margins) | $X | X% |
| Base | (current model) | ${fv:.2f} | {discount:.0f}% |
| Bear | (25-30% haircut) | $X | X% |
### Peer Multiples Cross-Check — compare implied multiples to 3–5 peers
### Historical Valuation Range — where stock traded over last 3–5 years (if data available)

{strategy_lens}
{data_constraints}"""),

            ("Financial Quality", f"""Write the Financial Quality section for {company} ({ticker}).

Sector: {data.profile.sector}.

Required subsections (use ### for each):
### Revenue Quality & Trend — table showing Revenue, Growth %, and Recurring % for last 3 years
### Margin Trajectory — table showing Gross, Operating, Net, FCF margins for last 3 years
### Returns on Capital — ROIC, ROE trend; is the business creating economic value above cost of capital?
### Balance Sheet & Cash Conversion — net debt position, FCF conversion rate, SBC dilution

{strategy_lens}
{data_constraints}"""),

            ("Risks & Bear Case", f"""Write the Risks & Bear Case section for {company} ({ticker}).

Base case fair value: ${fv:.2f}.

Required subsections (use ### for each):
### Risk Matrix — use a table:
| Risk | Probability | Impact | Mitigant |
|---|---|---|---|
List 5–7 risks. Probability/Impact: High/Med/Low.
### Bear Case Scenario — what goes wrong? Quantify bear case fair value (apply 25–35% haircut to base).
Show your bear case math explicitly.
### What Would Break the Thesis — 2–3 specific conditions that would invalidate the investment case

Market risks: {market_intel.get('opportunity_risk', 'N/A')[:1500]}
{strategy_lens}
{data_constraints}"""),
        ]

        # ── Dynamic schema generation: AI adapts section topics to the strategy ──
        # If we have a strategy/constitution, ask the AI to adapt the section
        # topics and emphasis — then use those adapted topics for each section prompt.
        strategy_obj = getattr(self, '_strategy', None)
        total_cost = 0
        adapted_sections = sections  # default: use fixed sections
        if strategy_lens and strategy_obj:
            adapt_prompt = (
                f"You are configuring an investment memo for {company} ({ticker}).\n"
                f"The investor's strategy:\n{strategy_lens}\n\n"
                f"The default investment memo has these 4 sections:\n"
                + "\n".join(f"  {i+1}. {t}" for i, (t, _) in enumerate(sections))
                + "\n\nYour task: Return a JSON array of 4 section objects, each with:\n"
                f'  {{"title": "...", "key_focus": "...", "subsections": ["...", "...", "..."]}}\n'
                f"Adapt the titles and subsections to best serve this investor's strategy. "
                f"Keep the same STRUCTURE (opportunity, valuation, financial quality, risks) but change the emphasis and topics "
                f"to match what matters most for this strategy. "
                f"For example, a ROIC-focused investor's 'Financial Quality' section should emphasize ROIC, reinvestment rates, and capital allocation above all else. "
                f"Return ONLY the JSON array — no explanation."
            )
            try:
                adapt_result = await self.llm.generate(
                    prompt=adapt_prompt,
                    agent="memo_investment",
                    system="You are a research structuring assistant. Return only valid JSON.",
                    reasoning_effort="low",
                )
                adapt_raw = (adapt_result.text or "").strip()
                if adapt_raw.startswith("```"):
                    adapt_raw = adapt_raw.split("```")[1]
                    if adapt_raw.startswith("json\n"):
                        adapt_raw = adapt_raw[5:]
                adapted_plan = json.loads(adapt_raw)
                total_cost += adapt_result.cost

                # ── Validate adaptation plan ──
                from backend.memo.validate import validate_investment_adaptation
                is_valid, adapt_errors = validate_investment_adaptation(adapted_plan)
                if not is_valid:
                    log.warning(f"Investment adaptation validation failed: {adapt_errors[:3]} — using default sections")
                    adapted_plan = None

                # Merge adapted section plan with original prompts
                # The prompts provide data context; the adapted plan provides focus
                if adapted_plan is not None and isinstance(adapted_plan, list) and len(adapted_plan) >= 4:
                    adapted_sections = []
                    for i, plan_item in enumerate(adapted_plan[:4]):
                        orig_title, orig_prompt = sections[i]
                        new_title = plan_item.get("title", orig_title)
                        key_focus = plan_item.get("key_focus", "")
                        subsections = plan_item.get("subsections", [])
                        # Augment original prompt with strategy-adapted focus
                        focus_block = f"\n\nSTRATEGY FOCUS FOR THIS SECTION:\n{key_focus}\n"
                        if subsections:
                            focus_block += "Required subsections (use ### for each):\n"
                            focus_block += "\n".join(f"### {s}" for s in subsections)
                        adapted_sections.append((new_title, orig_prompt + focus_block))
            except Exception as e:
                log.warning(f"Strategy section adaptation failed: {e} — using default sections")

        section_outputs = []

        for title, prompt in adapted_sections:
            # Inject constitution dimension-specific directives per section
            section_lens = self._build_constitution_section_lens(title, strategy_obj)
            if section_lens:
                prompt = f"{prompt}\n\n{section_lens}"
            try:
                result = await self.llm.generate(
                    prompt=prompt,
                    agent="memo_investment",
                    system=inv_sys_prompt,
                    reasoning_effort="medium",
                )
                content = result.text or ""
                word_count = len(content.split())
                quality_flag = None
                if word_count < 60:
                    quality_flag = f"short ({word_count} words)"
                elif any(phrase in content.lower() for phrase in [
                    "i don't have access", "i cannot provide", "data not available",
                    "unable to access", "no information available",
                ]):
                    quality_flag = "model flagged data gap"
                section_data = {
                    "title": title,
                    "content": content,
                    "cost": result.cost,
                    "word_count": word_count,
                    **({"quality_flag": quality_flag} if quality_flag else {}),
                }
                total_cost += result.cost

                # Extract structured data from prose (investment memo meta-schema)
                extracted = await self._extract_section_structured_data(
                    title, content, total_cost,
                )
                if extracted:
                    section_data["structured"] = extracted["data"]
                    total_cost += extracted.get("cost", 0)

                section_outputs.append(section_data)
            except Exception as e:
                section_outputs.append({
                    "title": title,
                    "content": f"[Section generation failed: {e}]",
                    "cost": 0,
                    "quality_flag": "error",
                })

        # ── Fact-check investment memo sections ──
        inv_violations = 0
        inv_coherence_warnings = []
        try:
            from backend.memo.fact_check import fact_check_section, cross_section_coherence_check
            fact_sheet = {
                "financials_annual": data.financials_annual or [],
                "financials_quarterly": data.financials_quarterly or [],
                "market_data": data.market_data or {},
                "ratios": data.ratios or {},
                "key_metrics": data.key_metrics or [],
            }
            for sec in section_outputs:
                violations = fact_check_section(sec["content"], fact_sheet)
                if violations:
                    sec["_fact_check"] = {"violations": violations, "count": len(violations)}
                    inv_violations += len(violations)
            section_texts = {s["title"]: s["content"] for s in section_outputs}
            inv_coherence_warnings = cross_section_coherence_check(section_texts)
        except Exception as fc_err:
            log.warning(f"Investment memo fact-check failed: {fc_err}")

        cov = coverage
        coverage_header = (
            f"*Data coverage: {cov['overall']}. "
            + (f"Warnings: {'; '.join(cov['warnings'])}" if cov["warnings"] else "All key data present.")
            + "*\n\n"
        )
        flagged = [s["title"] for s in section_outputs if s.get("quality_flag")]

        full_content = f"# {company} ({ticker}) — Investment Memo\n\n"
        full_content += f"**Price:** ${price:.2f} | **Fair Value:** ${fv:.2f} | **Discount:** {discount:.0f}%\n\n"
        full_content += coverage_header
        for sec in section_outputs:
            sec["content"] = _normalize_money_prose(sec["content"])
            full_content += f"## {sec['title']}\n\n{sec['content']}\n\n"

        return {
            "type": "investment",
            "content": full_content,
            "sections": section_outputs,
            "section_count": len(section_outputs),
            "word_count": len(full_content.split()),
            "flagged_sections": flagged,
            "data_coverage": cov,
            "fact_check": {
                "violations": inv_violations,
                "coherence_warnings": len(inv_coherence_warnings),
            },
            "fair_value": fv,
            "discount_pct": round(discount, 1),
            "cost": total_cost,
        }
