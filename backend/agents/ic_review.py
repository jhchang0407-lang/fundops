"""IC Review Agent — Stress-test thesis and gate decisions.

Takes a Thesis output, applies bear case haircuts (70% growth reduction),
checks growth-aware discount floors, and runs an AI IC review via the
shared LLM client. Produces a binary PASS/NO_PASS verdict.

Emits event_type="pass" or event_type="fail".
"""

from __future__ import annotations

import logging
import time

from backend.agents import AgentPlugin, AgentResult
from backend.core.metric_schema import resolve_alias, get_metric
from backend.core.utils import safe_float
from backend.core.prose_spec import IC_REVIEW_SPEC
from backend.core.prose_prompt import build_prose_system_prompt
from backend.core.prose_validate import clean_prose

log = logging.getLogger("fundops.ic_review")

IC_REVIEW_EXTRACTION_SYSTEM = """You extract structured IC review data from an investment committee review.
Extract the verdict (PASS or NO_PASS), conviction level (1-5), the single biggest risk, return assessments, a 2-sentence rationale, and style fit.
If the reviewer did not state a clear verdict, infer from the overall tone — lean NO_PASS when ambiguous."""

IC_REVIEW_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["PASS", "NO_PASS"],
            "description": "Binary IC verdict"
        },
        "conviction": {
            "type": "integer",
            "description": "Conviction level 1-5"
        },
        "key_risk": {
            "type": "string",
            "description": "Single biggest risk, one sentence"
        },
        "base_return_pct": {
            "type": "number",
            "description": "AI assessed base case return percentage"
        },
        "bear_return_pct": {
            "type": "number",
            "description": "AI assessed bear case return percentage"
        },
        "rationale": {
            "type": "string",
            "description": "2-sentence verdict rationale"
        },
        "style_fit": {
            "type": "string",
            "enum": ["strong", "moderate", "weak", "none"],
            "description": "How well this fits the investment strategy"
        }
    },
    "required": ["verdict", "conviction", "key_risk", "rationale"],
    "additionalProperties": False
}


class ICReviewAgent(AgentPlugin):
    """IC stress-test with binary PASS/NO_PASS verdict."""

    name = "ic_review"
    description = "Stress-test thesis with bear case and AI review"

    def __init__(self, config: dict = None, llm=None, db=None, library=None):
        super().__init__(config)
        self.llm = llm
        self.db = db
        self.library = library

    async def run(self, context: dict) -> AgentResult:
        """Stress-test a thesis.

        Steps:
        1. Extract return sources from thesis
        2. Apply 70% haircut for bear case
        3. Check growth-aware discount floors
        4. Run AI IC review (style fit, conviction)
        5. Produce verdict
        """
        t0 = time.time()
        ticker = context.get("ticker", "")
        thesis = context.get("thesis") or context
        constitution = context.get("constitution")

        if not ticker:
            ticker = thesis.get("ticker", "")
        if not ticker:
            return AgentResult(
                agent=self.name, status="failed",
                errors=["No ticker or thesis provided"],
                duration_s=time.time() - t0,
            )

        config = self.config or {}

        # Load hurdles from constitution first, fall back to config
        ic_hurdles = (constitution or {}).get("ic_hurdles") or {}
        hurdle_base = ic_hurdles.get("base_return_pct") or config.get("hurdle_base_pct", 20)
        hurdle_bear = ic_hurdles.get("bear_return_pct") or config.get("hurdle_bear_pct", 15)
        bear_haircut_pct = ic_hurdles.get("haircut_pct") or 70
        bear_haircut = bear_haircut_pct / 100  # Convert to decimal

        log.info(f"IC Review for {ticker}...")

        # Step 0a: Load SEC financial data from DB for richer context
        financial_data = None
        try:
            from backend.core.db_v2 import ScreenerV2DB
            from backend.core.financial_data import FinancialData
            db_path = self.db.db_path if self.db else None
            v2db = ScreenerV2DB(db_path=db_path)
            stored = v2db.get_ticker_financials(ticker)
            v2db.close()
            if stored and stored.get("financial_data"):
                financial_data = FinancialData.from_dict(stored["financial_data"])
                log.debug(f"[{ticker}] Loaded SEC financial data for IC review")
        except Exception as e:
            log.debug(f"[{ticker}] ticker_financials lookup in IC review failed: {e}")

        # Step 0b: Check data freshness from thesis
        data_freshness = thesis.get("data_freshness", {})
        ic_risk_factors = []
        if data_freshness.get("warning"):
            ic_risk_factors.append(f"Stale data: {data_freshness['warning']}")
            log.warning(f"[{ticker}] IC review on stale thesis data: {data_freshness['warning']}")

        # Step 1: Extract return data
        return_sources = thesis.get("return_sources", {})
        base_return = safe_float(thesis.get("expected_return", 0))
        discount_pct = safe_float(thesis.get("discount_pct", 0))
        quality = thesis.get("quality", {})

        # Enrich quality from stored SEC data if thesis quality is sparse
        if financial_data and not quality.get("roic"):
            flat = financial_data.to_flat_metrics()
            quality.setdefault("gross_margin", round(flat.get("gross_margin", 0) * 100, 1))
            quality.setdefault("roic", round(flat.get("roic", 0) * 100, 1))
            quality.setdefault("roe", round(flat.get("roe", 0) * 100, 1))
            quality.setdefault("debt_equity", round(flat.get("debt_equity", 0), 2))
            quality.setdefault("fcf_yield", round(flat.get("fcf_yield", 0), 1))

        gm = safe_float(quality.get("gross_margin", 0))
        growth_rate = safe_float(thesis.get("valuation", {}).get("growth_rate", 0))

        # Step 2: Bear case (70% haircut on growth and margin sources)
        bear_sources = {
            "discount": return_sources.get("discount", 0),
            "growth": round(return_sources.get("growth", 0) * (1 - bear_haircut), 1),
            "margin": round(return_sources.get("margin", 0) * (1 - bear_haircut), 1),
            "dividends": return_sources.get("dividends", 0),
        }
        bear_return = sum(bear_sources.values())

        # Step 3: Growth-aware discount floors
        growth_discounts = config.get("growth_aware_discounts", {})
        min_discount = 30  # default steady-state

        if growth_rate >= 15 and gm >= 60:
            # High-growth compounder
            min_discount = growth_discounts.get("high_growth", {}).get("min_discount", 15)
        elif growth_rate >= 10 and gm >= 50:
            # Moderate growth
            min_discount = growth_discounts.get("moderate", {}).get("min_discount", 20)
        else:
            # Steady-state
            min_discount = growth_discounts.get("steady_state", {}).get("min_discount", 30)

        discount_floor_met = discount_pct >= min_discount

        # Step 4: Mechanical verdict
        base_passes = base_return >= hurdle_base
        bear_passes = bear_return >= hurdle_bear
        mechanical_pass = base_passes and bear_passes and discount_floor_met

        # Step 5: Fetch similar research from library (precedent context)
        similar_research = []
        if self.library:
            try:
                sector = thesis.get("sector", "")
                lib_gm = safe_float(quality.get("gross_margin", 0))
                lib_roic = safe_float(quality.get("roic", 0))
                similar_research = await self.library.find_similar(
                    ticker=ticker, sector=sector,
                    gross_margin=lib_gm / 100, roic=lib_roic / 100,
                    top_k=5,
                )
            except Exception as e:
                log.warning(f"Library similarity lookup failed: {e}")

        # Step 6: AI IC review (pass constitution for style-aware review)
        ai_review = {}
        if config.get("ai_review", True) and self.llm:
            thesis_with_constitution = {**thesis, "_constitution": constitution}
            ai_review = await self._run_ai_review(
                ticker, thesis_with_constitution, base_return, bear_return,
                similar_research=similar_research,
            )

        # AI can override mechanical decision
        ai_verdict = ai_review.get("verdict", "")
        if ai_verdict == "NO_PASS" and mechanical_pass:
            log.info(f"{ticker}: AI overrode mechanical PASS to NO_PASS")
            verdict = "NO_PASS"
        elif ai_verdict == "PASS" and not mechanical_pass and bear_return >= hurdle_bear * 0.9:
            log.info(f"{ticker}: AI overrode near-miss mechanical NO_PASS to PASS")
            verdict = "PASS"
        else:
            verdict = "PASS" if mechanical_pass else "NO_PASS"

        # Conviction score (1-5)
        conviction = 1
        if verdict == "PASS":
            if bear_return >= 20 and discount_pct >= 30:
                conviction = 5
            elif bear_return >= 18:
                conviction = 4
            elif bear_return >= 15:
                conviction = 3
            else:
                conviction = 2

        # Key assumptions to monitor (flows to Portfolio agent)
        key_assumptions = []
        if return_sources.get("growth", 0) > 10:
            key_assumptions.append(f"Revenue growth sustains above {growth_rate:.0f}%")
        if return_sources.get("margin", 0) > 3:
            key_assumptions.append(f"Gross margin holds above {gm:.0f}%")
        if discount_pct > 25:
            key_assumptions.append("Multiple re-rates toward fair value")

        # Constitution scorecard: check each must-have and anti-signal
        constitution_scorecard = self._build_constitution_scorecard(thesis, constitution)

        # Check disqualifiers
        disqualified = False
        disqualifier_reason = ""
        if constitution and constitution.get("disqualifiers"):
            for dq in constitution["disqualifiers"]:
                # Disqualifiers are free-text, checked by AI review
                pass

        result_data = {
            "ticker": ticker,
            "verdict": verdict,
            "conviction": conviction,
            "base_return": round(base_return, 1),
            "bear_return": round(bear_return, 1),
            "return_sources_base": return_sources,
            "return_sources_bear": bear_sources,
            "discount_pct": round(discount_pct, 1),
            "discount_floor": min_discount,
            "discount_floor_met": discount_floor_met,
            "hurdle_base": hurdle_base,
            "hurdle_bear": hurdle_bear,
            "key_assumptions": key_assumptions,
            "key_risk": ai_review.get("key_risk", ""),
            "ai_review": ai_review.get("review", ""),
            "ai_verdict": ai_verdict,
            "constitution_scorecard": constitution_scorecard,
            "similar_research": similar_research,
            "data_freshness": data_freshness,
            "risk_factors": ic_risk_factors,
        }

        # Record in DB
        if self.db:
            try:
                self.db.record_run(
                    agent=self.name, ticker=ticker,
                    verdict=verdict,
                    scores={"conviction": conviction, "base_return": base_return, "bear_return": bear_return},
                    summary=f"{verdict} (conv {conviction}/5, base {base_return:.0f}%, bear {bear_return:.0f}%)",
                    full_output=result_data,
                )
            except Exception as e:
                log.warning(f"DB write failed: {e}")

        # Record judgment event
        try:
            from backend.core.db_v2 import ScreenerV2DB
            v2db = ScreenerV2DB(db_path=self.db.db_path if self.db else None)
            event_id = v2db.record_judgment_event(
                event_type="ic_passed" if verdict == "PASS" else "ic_failed",
                ticker=ticker,
                constitution_version=constitution.get("version") if constitution else None,
                agent=self.name,
                data={
                    "verdict": verdict,
                    "conviction": conviction,
                    "base_return": round(base_return, 1),
                    "bear_return": round(bear_return, 1),
                    "key_assumptions": key_assumptions,
                    "scorecard_signals_met": len(constitution_scorecard.get("signals_met", [])),
                    "scorecard_anti_triggered": len(constitution_scorecard.get("anti_signals_triggered", [])),
                },
                rationale=f"{verdict} conv={conviction}/5, base={base_return:.0f}% bear={bear_return:.0f}%",
                parent_event_id=context.get("parent_event_id"),
            )
            v2db.close()
        except Exception as e:
            log.debug(f"Judgment event write failed: {e}")

        log.info(f"IC Review {ticker}: {verdict} (base {base_return:.0f}%, bear {bear_return:.0f}%)")

        return AgentResult(
            agent=self.name, ticker=ticker, status="complete",
            event_type="pass" if verdict == "PASS" else "fail",
            data=result_data,
            duration_s=time.time() - t0,
        )

    def _build_constitution_scorecard(self, thesis: dict, constitution: dict | None) -> dict:
        """Build a constitution scorecard for the IC review.

        Uses metric_schema.resolve_alias() to handle any alias form
        (e.g. "Return on Invested Capital > 15%" resolves to canonical "roic").
        """
        if not constitution:
            return {"available": False}

        scorecard = {
            "available": True,
            "signals_met": [],
            "signals_missed": [],
            "anti_signals_triggered": [],
            "hurdles": {
                "base": {"threshold": (constitution.get("ic_hurdles") or {}).get("base_return_pct", 20) if isinstance(constitution.get("ic_hurdles"), dict) else 20},
                "bear": {"threshold": (constitution.get("ic_hurdles") or {}).get("bear_return_pct", 15) if isinstance(constitution.get("ic_hurdles"), dict) else 15},
            },
        }

        quality = thesis.get("quality", {})

        # Check must-have signals against thesis quality metrics
        # Fallback: if must_have_signals not set, derive from dimensions dict values
        must_have = constitution.get("must_have_signals") or []
        if not must_have:
            dims = constitution.get("dimensions") or {}
            must_have = [v for k, v in dims.items() if k not in ("universe", "style_identity", "north_star", "time_horizon") and isinstance(v, str)]
        for signal in must_have:
            if not isinstance(signal, str):
                continue
            metric_name = self._extract_metric_from_signal(signal)
            canonical = self._resolve_metric_name(metric_name) if metric_name else None

            if canonical:
                actual = self._get_quality_value(quality, canonical)
                threshold = self._parse_threshold(signal)
                met = actual >= threshold if threshold else True
                scorecard["signals_met" if met else "signals_missed"].append(
                    {"signal": signal, "metric": canonical, "actual": actual, "met": met}
                )
            else:
                scorecard["signals_met"].append(
                    {"signal": signal, "actual": "N/A", "met": "unchecked"}
                )

        # Check anti-signals (same resolution logic, but "triggered" = bad)
        for signal in constitution.get("anti_signals") or []:
            if not isinstance(signal, str):
                continue
            metric_name = self._extract_metric_from_signal(signal)
            canonical = self._resolve_metric_name(metric_name) if metric_name else None

            if canonical:
                actual = self._get_quality_value(quality, canonical)
                threshold = self._parse_threshold(signal)
                triggered = actual > threshold if threshold else False
                if triggered:
                    scorecard["anti_signals_triggered"].append(
                        {"signal": signal, "metric": canonical, "actual": actual}
                    )
            # If canonical is None, we can't check — silently skip

        return scorecard

    @staticmethod
    def _extract_metric_from_signal(signal: str) -> str:
        """Extract the metric name portion from a signal string.

        Examples:
            "ROIC > 15%"                       → "ROIC"
            "Return on Invested Capital > 15%"  → "Return on Invested Capital"
            "Gross Margin >= 50%"               → "Gross Margin"
            "Debt to Equity > 2"               → "Debt to Equity"
            "FCF positive"                     → "FCF"
        """
        import re
        # Split on comparison operators (>=, <=, >, <, ==, =) or "positive"/"negative"
        parts = re.split(r'\s*(?:>=|<=|>|<|==|=)\s*', signal, maxsplit=1)
        metric_part = parts[0].strip()
        # Also handle "FCF positive" style
        metric_part = re.sub(r'\s+(positive|negative)\s*$', '', metric_part, flags=re.IGNORECASE)
        # Strip trailing % if present in the metric name itself
        metric_part = metric_part.rstrip('%').strip()
        return metric_part

    @staticmethod
    def _resolve_metric_name(metric_name: str) -> str | None:
        """Try to resolve a metric name through multiple normalization strategies.

        resolve_alias() handles canonical names, display names, and registered aliases.
        This method adds fallback attempts for common natural-language forms like
        "Debt to Equity" (not an exact alias but close to "debt_to_equity").
        """
        if not metric_name:
            return None
        # Direct resolution (handles canonical, display, camelCase, snake_case aliases)
        canonical = resolve_alias(metric_name)
        if canonical:
            return canonical
        # Fallback: replace spaces with underscores (e.g. "Debt to Equity" → "debt_to_equity")
        underscore_form = metric_name.replace(" ", "_")
        canonical = resolve_alias(underscore_form)
        if canonical:
            return canonical
        # Fallback: replace " to " with "_to_", " of " with "_of_", etc.
        # Already covered by the above, but try stripping common words
        return None

    @staticmethod
    def _get_quality_value(quality: dict, canonical_name: str) -> float:
        """Map a canonical metric name to the corresponding value in the quality dict.

        The quality dict uses canonical names as keys (roic, gross_margin, etc.).
        """
        return safe_float(quality.get(canonical_name, 0))

    @staticmethod
    def _parse_threshold(signal: str) -> float | None:
        import re
        match = re.search(r'[><=]+\s*(\d+\.?\d*)', signal)
        return float(match.group(1)) if match else None

    async def _run_ai_review(self, ticker: str, thesis: dict,
                              base_return: float, bear_return: float,
                              similar_research: list[dict] | None = None) -> dict:
        """Run AI IC review for style fit and conviction.

        Uses the constitution for style context if available.
        Injects library precedent context when similar_research is provided.
        """
        config = self.config or {}

        # Build strategy lens from constitution (same pattern as thesis/memo)
        constitution = thesis.get("_constitution") or {}
        from backend.core.thesis_schema import build_thesis_strategy_lens, build_thesis_data_constraints
        strategy_lens = build_thesis_strategy_lens(constitution) if constitution else ""

        if not strategy_lens:
            style = config.get("style_profile", "concentrated, quality-at-a-discount, 3-5yr compounder")
            strategy_lens = f"Investment style: {style}"

        # Build data constraints so AI knows what's verified vs estimated
        data_constraints = build_thesis_data_constraints(thesis)

        quality = thesis.get("quality", {})

        prompt = f"""You are on the Investment Committee reviewing {ticker}.

{strategy_lens}

{data_constraints}

THESIS SUMMARY:
Company: {thesis.get('company_name', ticker)}
Sector: {thesis.get('sector', '')}
Price: ${thesis.get('price', 0):.2f}
Fair Value: ${thesis.get('fair_value', 0):.2f}
Discount: {thesis.get('discount_pct', 0):.0f}%
Expected Return (base): {base_return:.0f}%
Expected Return (bear): {bear_return:.0f}%

QUALITY METRICS (from SEC filings):
- Gross Margin: {quality.get('gross_margin', 0):.1f}%
- ROIC: {quality.get('roic', 0):.1f}%
- ROE: {quality.get('roe', 0):.1f}%
- D/E: {quality.get('debt_equity', 0):.2f}
- FCF Yield: {quality.get('fcf_yield', 0):.1f}%

RETURN SOURCES:
- Discount closing: {thesis.get('return_sources', {}).get('discount', 0):.1f}%
- Growth: {thesis.get('return_sources', {}).get('growth', 0):.1f}%
- Margin expansion: {thesis.get('return_sources', {}).get('margin', 0):.1f}%
- Dividends: {thesis.get('return_sources', {}).get('dividends', 0):.1f}%

Variant View: {thesis.get('variant_view', 'N/A')}

YOUR JOB:
1. Does this fit our investment strategy? (reference specific dimensions)
2. Are the return sources credible given the SEC data, or is this a value trap?
3. What is the single biggest risk?
4. What conviction level (1-5) would you assign?

## IC Verdict
State PASS or NO_PASS with a 2-sentence rationale."""

        # Inject few-shot examples (Phase 3)
        try:
            from backend.core.examples import load_examples, select_relevant_examples, format_examples_for_prompt
            all_examples = load_examples("ic_review")
            relevant = select_relevant_examples(all_examples, sector=thesis.get("sector", ""), n=2)
            if relevant:
                prompt += format_examples_for_prompt(relevant, agent="ic_review")
        except Exception:
            pass

        # Inject library precedent context if available
        if similar_research:
            precedent_lines = []
            for s in similar_research[:3]:
                precedent_lines.append(
                    f"- {s.get('ticker')}: {s.get('verdict', 'N/A')} "
                    f"(return: {s.get('expected_return', 'N/A')}%, "
                    f"type: {s.get('entry_type', 'N/A')})"
                )
            precedent_context = (
                "\n\nPRECEDENT — Similar names you've evaluated:\n"
                + "\n".join(precedent_lines)
            )
            prompt += precedent_context

        try:
            company = thesis.get('company_name', ticker)
            sys_prompt = build_prose_system_prompt(IC_REVIEW_SPEC, company=company, ticker=ticker)

            # Inject memory context
            from backend.api.deps import get_memory
            memory_block = get_memory().format_for_injection()
            if memory_block:
                sys_prompt += f"\n\n{memory_block}"

            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt},
            ]

            two_pass = await self.llm.generate_then_extract(
                messages=messages,
                extraction_system=IC_REVIEW_EXTRACTION_SYSTEM,
                extraction_schema=IC_REVIEW_EXTRACTION_SCHEMA,
                agent="ic_review",
                reasoning_effort="high",
                extraction_reasoning_effort="low",
            )

            text = clean_prose(two_pass.raw_text or "", IC_REVIEW_SPEC)
            extracted = two_pass.extracted

            verdict = extracted.get("verdict", "")
            key_risk = extracted.get("key_risk", "")
            conviction_ai = extracted.get("conviction", 0)
            rationale = extracted.get("rationale", "")
            style_fit = extracted.get("style_fit", "")

            return {
                "review": text,
                "verdict": verdict,
                "key_risk": key_risk,
                "conviction_ai": conviction_ai,
                "rationale": rationale,
                "style_fit": style_fit,
                "base_return_pct": extracted.get("base_return_pct"),
                "bear_return_pct": extracted.get("bear_return_pct"),
                "cost": two_pass.total_cost,
            }

        except Exception as e:
            log.warning(f"AI IC review failed: {e}")
            return {"review": "", "verdict": "", "key_risk": "", "error": str(e)}
