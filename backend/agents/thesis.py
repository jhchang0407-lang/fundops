"""Thesis Agent — Write quick thesis with web research.

Takes a single ticker, fetches financial data via connectors, runs web research
via the shared LLM client, and generates a structured investment thesis with
independent valuation and return source decomposition.

Emits event_type="complete" with thesis data.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.agents import AgentPlugin, AgentResult
from backend.core.utils import safe_float
from backend.core.web_grounding import build_fact_anchor, ground_web_research, clean_web_research
from backend.core.prose_spec import THESIS_SPEC
from backend.core.prose_prompt import build_prose_system_prompt
from backend.core.prose_validate import clean_prose

log = logging.getLogger("fundops.thesis")


class ThesisAgent(AgentPlugin):
    """Write quick thesis with independent valuation."""

    name = "thesis"
    description = "Quick thesis with web research and independent valuation"

    def __init__(self, config: dict = None, fmp=None, sec=None, yfinance=None,
                 llm=None, web_search=None, db=None, library=None):
        super().__init__(config)
        self.fmp = fmp
        self.sec = sec
        self.yfinance = yfinance
        self.llm = llm
        self.web_search = web_search
        self.db = db
        self.library = library

    async def run(self, context: dict) -> AgentResult:
        """Generate thesis for a ticker.

        Steps:
        1. Fetch financial data (SEC + FMP/yfinance)
        2. Run web research (why is it cheap? bull case?)
        3. Calculate independent valuation
        4. Decompose expected return sources
        5. Assemble thesis
        """
        t0 = time.time()
        ticker = context.get("ticker", "")
        if not ticker:
            return AgentResult(
                agent=self.name, status="failed",
                errors=["No ticker provided"],
                duration_s=time.time() - t0,
            )

        # Load constitution for strategy-aware thesis
        constitution = context.get("constitution")

        log.info(f"Generating thesis for {ticker}...")

        # Step 1: Fetch financial data (seeded with screener data if available)
        screener_data = context.get("screener_data")
        data = await self._fetch_data(ticker, screener_seed=screener_data)
        if not data:
            return AgentResult(
                agent=self.name, ticker=ticker, status="failed",
                errors=[f"Failed to fetch data for {ticker}"],
                duration_s=time.time() - t0,
            )

        # Step 1b: Check data freshness
        from backend.core.utils import check_data_freshness
        freshness = check_data_freshness(data, max_age_days=90)
        data_warnings = []
        if freshness.get("warning"):
            data_warnings.append(freshness["warning"])
            log.warning(f"[{ticker}] {freshness['warning']}")

        # Step 2: Web research (with 180s timeout to prevent hanging)
        import asyncio as _asyncio
        web_research = {}
        config = self.config or {}
        if config.get("web_search", True) and self.web_search:
            try:
                web_research = await _asyncio.wait_for(
                    self._run_web_research(ticker, data),
                    timeout=180.0,
                )
            except _asyncio.TimeoutError:
                log.warning(f"[{ticker}] Web research timed out after 180s, continuing without it")
                web_research = {"error": "Web research timed out"}

        # Step 3: Calculate valuation
        valuation = self._calculate_valuation(ticker, data)

        # Step 3b: Write thesis narrative using LLM (with 120s timeout)
        try:
            thesis_narrative = await _asyncio.wait_for(
                self._write_thesis_narrative(
                    ticker, data, web_research, valuation, constitution),
                timeout=120.0,
            )
        except _asyncio.TimeoutError:
            log.warning(f"[{ticker}] Thesis narrative timed out after 120s, using data summary")
            thesis_narrative = self._build_data_summary(ticker, data, valuation)

        # Step 4: Return decomposition
        price = safe_float(data.get("price", 0))
        fair_value = valuation.get("fair_value_base", 0)
        discount = ((fair_value - price) / fair_value * 100) if fair_value > 0 else 0

        rev_growth = safe_float(data.get("revenue_growth", 0))
        gm = safe_float(data.get("gross_margin", 0))

        return_sources = {
            "discount": round(max(0, discount * 0.5), 1),  # Half of discount as return
            "growth": round(min(rev_growth * 100, 20), 1),
            "margin": round(max(0, (gm - 0.3) * 10), 1),  # Margin above 30% baseline
            "dividends": round(safe_float(data.get("dividend_yield", 0)) * 100, 1),
        }
        expected_return = sum(return_sources.values())

        # Step 4b: Validate return sources
        validation_data = {**data, "discount_pct": discount}
        return_validation = self._validate_return_sources(
            return_sources, expected_return, validation_data,
        )
        if return_validation["warnings"]:
            log.warning(f"Return validation warnings for {ticker}: {return_validation['warnings']}")

        # Step 4c: Library similarity lookup
        similar_research = []
        if self.library:
            try:
                similar_research = await self.library.find_similar(
                    ticker=ticker,
                    sector=data.get("sector"),
                    gross_margin=safe_float(data.get("gross_margin", 0)),
                    roic=safe_float(data.get("roic", 0)),
                    top_k=5,
                )
            except Exception as e:
                log.warning(f"Library similarity lookup failed: {e}")

        # Step 5: Determine conviction
        conviction = "LOW"
        if expected_return >= 30 and discount >= 25:
            conviction = "HIGH"
        elif expected_return >= 20:
            conviction = "MEDIUM"

        # Step 5b: Constitution fit check
        constitution_fit = self._check_constitution_fit(data, constitution)

        thesis = {
            "ticker": ticker,
            "company_name": data.get("company_name", ""),
            "sector": data.get("sector", ""),
            "industry": data.get("industry", ""),
            "price": price,
            "fair_value": fair_value,
            "discount_pct": round(discount, 1),
            "expected_return": round(expected_return, 1),
            "return_sources": return_sources,
            "return_validation": return_validation,
            "conviction": conviction,
            "valuation": valuation,
            "quality": {
                # All percentages as 0-1 decimals (consistent with screener output)
                "gross_margin": round(gm, 4),
                "operating_margin": round(safe_float(data.get("operating_margin", 0)), 4),
                "net_margin": round(safe_float(data.get("net_margin", 0)), 4),
                "roic": round(safe_float(data.get("roic", 0)), 4),
                "roe": round(safe_float(data.get("roe", 0)), 4),
                "debt_equity": round(safe_float(data.get("debt_equity", 0)), 2),
                "fcf_yield": round(safe_float(data.get("fcf_yield", 0)), 4),
                "revenue_growth": round(safe_float(data.get("revenue_growth", 0)), 4),
                # Absolute financials
                "revenue": safe_float(data.get("revenue", 0)),
                "net_income": safe_float(data.get("net_income", 0)),
                "fcf": safe_float(data.get("fcf", 0)),
                "pe": safe_float(data.get("pe", 0)),
            },
            "web_research": web_research,
            "thesis_narrative": thesis_narrative,
            "thesis_summary": await self._generate_summary(ticker, thesis_narrative, data, valuation),
            "variant_view": thesis_narrative,
            "constitution_fit": constitution_fit,
            "data_freshness": freshness,
            "data_warnings": data_warnings,
            "similar_research": [
                {
                    "ticker": s.get("ticker"),
                    "verdict": s.get("verdict"),
                    "expected_return": s.get("expected_return"),
                    "entry_type": s.get("entry_type"),
                    "conviction": s.get("conviction"),
                }
                for s in similar_research
            ],
        }

        # Capture evidence artifacts (data lineage)
        evidence_ids = []
        try:
            from backend.core.evidence import EvidenceCapture
            import sqlite3
            db_path = self.db.db_path if self.db else None
            ev_conn = sqlite3.connect(str(db_path))
            ev = EvidenceCapture(ev_conn)

            # Capture SEC/FMP financial data snapshot
            evidence_ids.append(ev.capture(
                ticker=ticker, artifact_type="sec_filing",
                source="sec_edgar+yfinance", data={
                    k: data.get(k) for k in [
                        "revenue", "gross_margin", "roic", "roe",
                        "debt_equity", "fcf_yield", "pe", "price",
                        "revenue_growth", "sector", "industry",
                        "latestFilingDate", "date",
                    ] if data.get(k) is not None
                },
            ))

            # Capture price quote
            evidence_ids.append(ev.capture(
                ticker=ticker, artifact_type="price_quote",
                source="yfinance", data={
                    "price": price, "fair_value": fair_value,
                    "discount_pct": round(discount, 1),
                },
            ))

            ev_conn.close()
            thesis["evidence_artifact_ids"] = evidence_ids
        except Exception as e:
            log.debug(f"Evidence capture failed (non-critical): {e}")

        # Record in DB
        if self.db:
            try:
                self.db.upsert_ticker(ticker, company_name=data.get("company_name"),
                                       sector=data.get("sector"), industry=data.get("industry"))
                self.db.record_run(
                    agent=self.name, ticker=ticker,
                    fair_value=fair_value, price_at_run=price,
                    scores={"expected_return": expected_return, "conviction": conviction},
                    summary=f"FV ${fair_value:.0f}, disc {discount:.0f}%, ret {expected_return:.0f}%",
                    full_output=thesis,
                )
            except Exception as e:
                log.warning(f"DB write failed: {e}")

        # Record judgment event
        try:
            from backend.core.db_v2 import ScreenerV2DB
            v2db = ScreenerV2DB(db_path=self.db.db_path if self.db else None)
            v2db.record_judgment_event(
                event_type="thesis_generated",
                ticker=ticker,
                constitution_version=constitution.get("version") if constitution else None,
                agent=self.name,
                data={
                    "fair_value": fair_value,
                    "expected_return": round(expected_return, 1),
                    "conviction": conviction,
                    "discount_pct": round(discount, 1),
                    "constitution_fit": constitution_fit,
                },
                rationale=f"FV ${fair_value:.0f}, {discount:.0f}% disc, {expected_return:.0f}% ret, {conviction} conviction",
                parent_event_id=context.get("parent_event_id"),
            )
            v2db.close()
        except Exception as e:
            log.debug(f"Judgment event write failed: {e}")

        log.info(f"Thesis for {ticker}: FV=${fair_value:.0f}, disc={discount:.0f}%, ret={expected_return:.0f}%")

        return AgentResult(
            agent=self.name, ticker=ticker, status="complete",
            event_type="complete",
            data=thesis,
            duration_s=time.time() - t0,
        )

    def _validate_return_sources(self, return_sources: dict, expected_return: float,
                                data: dict, tolerance: float = 2.0) -> dict:
        """Validate return source decomposition.

        Checks:
        1. Sources sum to expected_return within ±tolerance pp
        2. Discount source matches actual discount_pct
        3. Growth source is reasonable vs SEC revenue CAGR
        4. Each source is non-negative

        Returns: {valid: bool, warnings: list[str], adjustments: dict}
        """
        warnings: list[str] = []
        adjustments: dict[str, Any] = {}

        # 1. Sum check
        source_sum = sum(return_sources.values())
        if abs(source_sum - expected_return) > tolerance:
            warnings.append(
                f"Return sources sum to {source_sum:.1f}% but expected_return is "
                f"{expected_return:.1f}% (diff {abs(source_sum - expected_return):.1f}pp, "
                f"tolerance {tolerance}pp)"
            )

        # 2. Discount source vs actual discount_pct
        discount_pct = safe_float(return_sources.get("discount", 0))
        actual_discount = safe_float(data.get("discount_pct", 0))
        # The formula is discount * 0.5, so expected discount source ≈ actual_discount * 0.5
        expected_discount_source = round(max(0, actual_discount * 0.5), 1)
        if abs(discount_pct - expected_discount_source) > tolerance:
            warnings.append(
                f"Discount source ({discount_pct:.1f}%) inconsistent with "
                f"discount_pct ({actual_discount:.1f}% * 0.5 = {expected_discount_source:.1f}%)"
            )
            adjustments["discount"] = {
                "stated": discount_pct,
                "implied": expected_discount_source,
            }

        # 3. Growth source vs actual revenue growth
        growth_source = safe_float(return_sources.get("growth", 0))
        rev_growth = safe_float(data.get("revenue_growth", 0))
        actual_growth_pct = rev_growth * 100  # convert decimal to percentage
        # Growth source is min(rev_growth * 100, 20), so it should be close to actual
        # Flag if growth source exceeds actual growth by more than 5pp
        if growth_source > actual_growth_pct + 5.0 and actual_growth_pct >= 0:
            warnings.append(
                f"Growth source ({growth_source:.1f}%) exceeds actual revenue growth "
                f"({actual_growth_pct:.1f}%) by more than 5pp"
            )
            adjustments["growth"] = {
                "stated": growth_source,
                "actual_revenue_growth": round(actual_growth_pct, 1),
            }

        # 4. Non-negative check
        for source_name, value in return_sources.items():
            if value < 0:
                warnings.append(f"Return source '{source_name}' is negative ({value:.1f}%)")

        valid = len(warnings) == 0
        return {"valid": valid, "warnings": warnings, "adjustments": adjustments}

    def _check_constitution_fit(self, data: dict, constitution: dict | None) -> dict:
        """Check how well this stock fits the investor's constitution.

        Returns a scorecard of must-have signals, anti-signals, and style fit.
        """
        if not constitution:
            return {"available": False}

        fit = {"available": True, "signals_met": [], "signals_missed": [], "anti_signals_triggered": [], "style_notes": []}

        # Check must-have signals
        must_haves = constitution.get("must_have_signals") or []
        for signal in must_haves:
            if not isinstance(signal, str):
                continue
            sig_lower = signal.lower()
            met = False
            # Parse common signal patterns
            if "roic" in sig_lower and ">" in sig_lower:
                threshold = self._extract_threshold(signal)
                actual = safe_float(data.get("roic", 0)) * 100
                met = actual >= threshold if threshold else False
                fit["signals_met" if met else "signals_missed"].append(
                    f"{signal} (actual: {actual:.1f}%)"
                )
            elif "gm" in sig_lower or "gross margin" in sig_lower:
                threshold = self._extract_threshold(signal)
                actual = safe_float(data.get("gross_margin", 0)) * 100
                met = actual >= threshold if threshold else False
                fit["signals_met" if met else "signals_missed"].append(
                    f"{signal} (actual: {actual:.1f}%)"
                )
            elif "fcf" in sig_lower and "positive" in sig_lower:
                fcf_yield = safe_float(data.get("fcf_yield", 0))
                met = fcf_yield > 0
                fit["signals_met" if met else "signals_missed"].append(
                    f"{signal} (FCF yield: {fcf_yield*100:.1f}%)"
                )
            else:
                fit["signals_met"].append(f"{signal} (not auto-checked)")

        # Check anti-signals
        anti_signals = constitution.get("anti_signals") or []
        for signal in anti_signals:
            if not isinstance(signal, str):
                continue
            sig_lower = signal.lower()
            triggered = False
            if "d/e" in sig_lower or "debt" in sig_lower.split("/")[0] if "/" in sig_lower else False:
                threshold = self._extract_threshold(signal)
                actual = safe_float(data.get("debt_equity", 0))
                triggered = actual > threshold if threshold else False
                if triggered:
                    fit["anti_signals_triggered"].append(f"{signal} (actual: {actual:.2f})")
            elif "declining revenue" in sig_lower:
                rev_growth = safe_float(data.get("revenue_growth", 0))
                if rev_growth < 0:
                    fit["anti_signals_triggered"].append(f"{signal} (growth: {rev_growth*100:.1f}%)")

        # Style fit note
        style = constitution.get("style_identity", "")
        if style:
            fit["style_notes"].append(f"Constitution style: {style}")

        # Summary score
        total_signals = len(must_haves)
        met_count = len(fit["signals_met"])
        anti_count = len(fit["anti_signals_triggered"])
        if total_signals > 0:
            fit["fit_score"] = round((met_count / total_signals) * 100 - (anti_count * 20), 1)
        else:
            fit["fit_score"] = None

        return fit

    @staticmethod
    def _extract_threshold(signal: str) -> float | None:
        """Extract a numeric threshold from a signal string like 'ROIC > 15%'."""
        import re
        match = re.search(r'[><=]+\s*(\d+\.?\d*)', signal)
        if match:
            return float(match.group(1))
        return None

    async def _write_thesis_narrative(self, ticker: str, data: dict,
                                      web_research: dict, valuation: dict,
                                      constitution: dict | None) -> str:
        """Write thesis narrative using constitution-driven section schema.

        Uses the meta-schema to generate per-section structured content:
        1. Determine which sections to include (from constitution or defaults)
        2. For each section, build a focused prompt with relevant data + dimension lens
        3. Generate all sections in one structured LLM call
        4. Assemble into final narrative

        Falls back to unstructured generation if meta-schema fails.
        """
        if not self.llm:
            return self._build_data_summary(ticker, data, valuation)

        from backend.core.thesis_schema import (
            build_thesis_data_constraints,
            build_thesis_strategy_lens,
            get_enabled_sections,
            get_section_data_package,
            get_section_dimension_lens,
        )

        company = data.get("company_name", ticker)
        sector = data.get("sector", "")

        price = safe_float(data.get("price", 0))
        fv = safe_float(valuation.get("fair_value_base", 0))
        discount_pct = ((fv - price) / fv * 100) if fv > 0 else 0

        # Build strategy-aware context
        data_constraints = build_thesis_data_constraints(data)
        strategy_lens = build_thesis_strategy_lens(constitution)

        # Get constitution-customized section schema (or defaults)
        section_schema = None
        if constitution:
            agent_profiles = constitution.get("agent_profiles") or {}
            thesis_profile = agent_profiles.get("thesis") or agent_profiles.get("val") or {}
            section_schema = thesis_profile.get("section_schema")
        sections = get_enabled_sections(section_schema)

        # Build flat metrics dict for section data packaging
        flat_metrics = {
            "ticker": ticker, "company_name": company, "sector": sector,
            "industry": data.get("industry", ""),
            "price": price, "market_cap": safe_float(data.get("market_cap", 0)),
            "pe": safe_float(data.get("pe", 0)),
            "fcf_yield": safe_float(data.get("fcf_yield", 0)),
            "earnings_yield": safe_float(data.get("earnings_yield", 0)),
            "gross_margin": safe_float(data.get("gross_margin", 0)),
            "operating_margin": safe_float(data.get("operating_margin", 0)),
            "net_margin": safe_float(data.get("net_margin", 0)),
            "roic": safe_float(data.get("roic", 0)),
            "roe": safe_float(data.get("roe", 0)),
            "roa": safe_float(data.get("roa", 0)),
            "fcf_margin": safe_float(data.get("fcf_margin", 0)),
            "fcf_conversion": safe_float(data.get("fcf_conversion", 0)),
            "debt_equity": safe_float(data.get("debt_equity", 0)),
            "current_ratio": safe_float(data.get("current_ratio", 0)),
            "interest_coverage": safe_float(data.get("interest_coverage", 0)),
            "revenue_growth": safe_float(data.get("revenue_growth", 0)),
            "earnings_growth": safe_float(data.get("earnings_growth", 0)),
            "revenue": safe_float(data.get("revenue", 0)),
            "net_income": safe_float(data.get("net_income", 0)),
            "fcf": safe_float(data.get("fcf", 0)),
            "fcf_per_share": safe_float(data.get("fcf_per_share", 0)),
            "dividend_yield": safe_float(data.get("dividend_yield", 0)),
            "discount_pct": discount_pct,
            "return_sources": data.get("return_sources") or {},
        }

        # Build per-section prompts with relevant data and dimension lens
        section_prompts = []
        for sec in sections:
            sec_data = get_section_data_package(sec, flat_metrics, web_research, valuation)
            dim_lens = get_section_dimension_lens(sec, constitution)
            title = sec.get("title", sec.get("title_default", sec["id"]))
            purpose = sec.get("emphasis") or sec.get("purpose", "")

            section_block = f"""## {title}
Purpose: {purpose}

DATA FOR THIS SECTION:
{sec_data}
"""
            if dim_lens:
                section_block += f"\n{dim_lens}\n"
            section_prompts.append(section_block)

        prompt = f"""Write a structured investment thesis for {company} ({ticker}).

{data_constraints}

VALUATION:
- Fair Value: ${fv:.2f}
- Method: {valuation.get('method', 'N/A')}
- Discount to FV: {discount_pct:.1f}%

{"".join(section_prompts)}

INSTRUCTIONS:
Write each section as a focused paragraph (150-400 words each).
Use the section headers provided above. For each section:
- ONLY use data listed under that section's DATA block
- Focus on the investor's emphasis areas if listed
- Be specific with numbers from the data — no generic statements
- Write like a hedge fund analyst, not a news article
- Cite specific financial metrics to support each claim"""

        # Inject few-shot examples
        try:
            from backend.core.examples import load_examples, select_relevant_examples, format_examples_for_prompt
            all_examples = load_examples("thesis")
            relevant = select_relevant_examples(all_examples, sector=sector, n=2)
            if relevant:
                prompt += format_examples_for_prompt(relevant, agent="thesis")
        except Exception:
            pass

        try:
            try:
                from backend.api.deps import get_memory
                memory_block = get_memory().format_for_injection()
            except Exception:
                memory_block = ""

            sys_prompt = build_prose_system_prompt(
                THESIS_SPEC, company=company, ticker=ticker,
                data_constraints=data_constraints,
                strategy_lens=strategy_lens,
                memory_context=memory_block,
            )
            result = await self.llm.generate(
                prompt=prompt,
                agent="thesis",
                system=sys_prompt,
                reasoning_effort="medium",
            )
            cleaned = clean_prose(result.text or "", THESIS_SPEC)
            return cleaned
        except Exception as e:
            log.warning(f"LLM thesis narrative failed for {ticker}: {e}")
            return self._build_data_summary(ticker, data, valuation)

    async def _generate_summary(self, ticker: str, narrative: str, data: dict, valuation: dict) -> str:
        """Generate a 3-4 sentence summary of the thesis for the dropdown card.

        Uses a fast LLM call to distill the key ideas. Falls back to a
        data-driven summary if LLM is unavailable.
        """
        if not self.llm or not narrative:
            company = data.get("company_name", ticker)
            fv = safe_float(valuation.get("fair_value_base", 0))
            price = safe_float(data.get("price", 0))
            disc = ((fv - price) / fv * 100) if fv > 0 else 0
            return (
                f"{company} ({ticker}) trades at ${price:.0f} vs fair value ${fv:.0f} ({disc:.0f}% discount). "
                f"Expected return {sum((data.get('return_sources') or {}).values()):.0f}% driven by "
                f"{'growth and margin expansion' if safe_float(data.get('revenue_growth', 0)) > 0.1 else 'discount closing'}."
            )

        try:
            import asyncio as _aio
            result = await _aio.wait_for(
                self.llm.generate(
                    prompt=(
                        f"Summarize this investment thesis in 3-4 sentences. "
                        f"Focus on: why it's cheap, where the return comes from, and the key risk. "
                        f"No markdown, no bullet points, no headers. Plain text only.\n\n"
                        f"{narrative[:3000]}"
                    ),
                    agent="thesis",
                    reasoning_effort="low",
                ),
                timeout=30.0,
            )
            summary = (result.text or "").strip()
            # Strip any markdown that slipped through
            summary = summary.replace("**", "").replace("##", "").replace("- ", "")
            return summary[:500]  # Hard cap
        except Exception as e:
            log.debug(f"[{ticker}] Summary generation failed: {e}")
            return ""

    def _build_data_summary(self, ticker: str, data: dict, valuation: dict) -> str:
        """Build a structured text summary from data when LLM is unavailable."""
        company = data.get("company_name", ticker)
        parts = [f"{company} ({ticker}) in {data.get('sector', 'N/A')}."]

        gm = safe_float(data.get("gross_margin", 0))
        if gm:
            parts.append(f"Gross margin {gm*100:.1f}%.")

        roic = safe_float(data.get("roic", 0))
        if roic:
            parts.append(f"ROIC {roic*100:.1f}%.")

        growth = safe_float(data.get("revenue_growth", 0))
        if growth:
            parts.append(f"Revenue growing {growth*100:.1f}% YoY.")

        fv = safe_float(valuation.get("fair_value_base", 0))
        price = safe_float(data.get("price", 0))
        if fv and price:
            disc = (fv - price) / fv * 100
            parts.append(f"Fair value ${fv:.0f} vs ${price:.0f} ({disc:.0f}% discount).")

        return " ".join(parts)

    async def _fetch_data(self, ticker: str, screener_seed: dict = None) -> dict:
        """Fetch financial data for thesis generation.

        Priority: ticker_financials DB (SEC-enriched) → screener seed → FMP fallback.
        Always fetches live price from yfinance for price-dependent metrics.
        """
        data = {"ticker": ticker}

        # 1. Try loading from ticker_financials DB (persisted by screener)
        db_loaded = False
        try:
            from backend.core.db_v2 import ScreenerV2DB
            from backend.core.financial_data import FinancialData
            db_path = self.db.db_path if self.db else None
            v2db = ScreenerV2DB(db_path=db_path)
            stored = v2db.get_ticker_financials(ticker)
            v2db.close()

            if stored and stored.get("financial_data"):
                fd = FinancialData.from_dict(stored["financial_data"])
                flat = fd.to_flat_metrics()
                data.update(flat)
                # Store the full FinancialData for downstream use (fact_anchor, etc.)
                data["_financial_data"] = fd
                db_loaded = True
                # Include fetch/filing dates so data freshness can compute age
                if stored.get("fetched_at"):
                    data["latestFilingDate"] = stored["fetched_at"][:10]  # YYYY-MM-DD
                log.info(f"[{ticker}] Loaded financial data from DB (fetched {stored.get('fetched_at', '?')})")
        except Exception as e:
            log.debug(f"[{ticker}] ticker_financials lookup failed: {e}")

        # 2. Fallback: screener seed data (if DB didn't have it)
        if not db_loaded and screener_seed and isinstance(screener_seed, dict):
            seed_map = {
                "pe": "pe", "revenue_growth": "revenueGrowth",
                "earnings_growth": "earningsGrowth", "gross_margin": "grossProfitMargin",
                "operating_margin": "operatingMargin", "net_margin": "netProfitMargin",
                "roic": "returnOnInvestedCapital", "roe": "returnOnEquity",
                "fcf_yield": "fcfYield", "debt_equity": "debtEquity",
                "owner_eps": "ownerEarningsPerShare", "company_name": "companyName",
                "sector": "sector", "industry": "industry",
            }
            for data_key, seed_key in seed_map.items():
                val = screener_seed.get(seed_key)
                if val is not None and val != 0 and val != "":
                    data[data_key] = val
            if screener_seed.get("price"):
                data["price"] = screener_seed["price"]
            log.debug(f"[{ticker}] Seeded from screener handoff (DB fallback)")

        # 3. Always fetch live price from yfinance (price changes daily)
        quote_source = self.yfinance or self.fmp
        if quote_source:
            result = await quote_source.get_quotes([ticker])
            if result.ok and result.data:
                q = result.data[0] if isinstance(result.data, list) else result.data
                live_price = q.get("price", 0)
                if live_price:
                    data["price"] = live_price
                    data["market_cap"] = q.get("marketCap") or q.get("mktCap", 0)
                if not data.get("company_name"):
                    data["company_name"] = q.get("companyName") or q.get("name", "")

        # 4. Get profile for sector/industry if not already set
        if not data.get("sector"):
            profile_source = self.yfinance or self.fmp
            if profile_source:
                result = await profile_source.get_profile(ticker)
                if result.ok:
                    p = result.data
                    data["sector"] = p.get("sector", "")
                    data["industry"] = p.get("industry", "")
                    data["company_name"] = data.get("company_name") or p.get("companyName", "")

        # 5. Recompute price-dependent metrics with live price
        live_price = safe_float(data.get("price", 0))
        if live_price > 0 and data.get("owner_eps"):
            eps = safe_float(data["owner_eps"])
            if eps > 0:
                data["pe"] = round(live_price / eps, 1)

        # 6. FMP enrichment (only if available — optional paid upgrade)
        if self.fmp and not db_loaded:
            result = await self.fmp.get_key_metrics(ticker)
            if result.ok and result.data:
                km = result.data[0] if isinstance(result.data, list) else result.data
                data["roic"] = km.get("roicTTM") or data.get("roic", 0)
                data["roe"] = km.get("roeTTM") or data.get("roe", 0)
                data["revenue_growth"] = km.get("revenueGrowthTTM") or data.get("revenue_growth", 0)
                data["gross_margin"] = km.get("grossProfitMarginTTM") or data.get("gross_margin", 0)

        return data

    async def _run_web_research(self, ticker: str, data: dict) -> dict:
        """Run web research: why is it cheap + bull case.

        Integrates the web grounding layer (A4):
        - Pre-search: builds a fact anchor from SEC/FMP data and prepends to queries.
        - Post-search: grounds each result against known financials.
        - Re-search: retries once with a tighter query if confidence < 0.4.
        """
        company = data.get("company_name", ticker)
        sector = data.get("sector", "")
        industry = data.get("industry", "")
        price = data.get("price", 0)

        results = {}

        # Pre-search: build fact anchor from known financial data
        try:
            fact_anchor = build_fact_anchor(data, ticker, company)
        except Exception as e:
            log.warning(f"Failed to build fact anchor for {ticker}: {e}")
            fact_anchor = ""

        try:
            # --- Why is it cheap? ---
            why_cheap_query = (
                f"{fact_anchor}\n\n"
                f"Why is {company} ({ticker}) stock trading at a discount? "
                f"What happened in the last 12 months? Price is ${price:.2f}. "
                f"Sector: {sector}. Be specific with dates and numbers."
            ) if fact_anchor else (
                f"Why is {company} ({ticker}) stock trading at a discount? "
                f"What happened in the last 12 months? Price is ${price:.2f}. "
                f"Sector: {sector}. Be specific with dates and numbers."
            )

            import asyncio as _aio
            discount_result = await _aio.wait_for(
                self.web_search.search(
                    query=why_cheap_query,
                    context={"agent": "thesis", "ticker": ticker},
                ),
                timeout=90.0,
            )
            results["why_cheap"] = discount_result.text
            results["why_cheap_cost"] = discount_result.cost

            # Post-search grounding for why_cheap
            try:
                why_cheap_grounded = ground_web_research(
                    discount_result.text, data, ticker, company, fact_anchor,
                )

                # Re-search on low confidence
                if why_cheap_grounded.confidence < 0.4:
                    log.info(f"Low confidence ({why_cheap_grounded.confidence:.2f}) on why_cheap for {ticker}, retrying with tighter query")
                    retry_query = (
                        f"{fact_anchor}\n\n"
                        f"Why is {ticker} {company} stock cheap? "
                        f"Industry: {industry}. Sector: {sector}. "
                        f"Focus specifically on {company} ({ticker}) only. "
                        f"Recent earnings, guidance, or sector headwinds. Be specific with dates."
                    ) if fact_anchor else (
                        f"Why is {ticker} {company} stock cheap? "
                        f"Industry: {industry}. Sector: {sector}. "
                        f"Focus specifically on {company} ({ticker}) only. "
                        f"Recent earnings, guidance, or sector headwinds. Be specific with dates."
                    )
                    retry_result = await _aio.wait_for(
                        self.web_search.search(
                            query=retry_query,
                            context={"agent": "thesis", "ticker": ticker},
                        ),
                        timeout=60.0,
                    )
                    retry_grounded = ground_web_research(
                        retry_result.text, data, ticker, company, fact_anchor,
                    )
                    if retry_grounded.confidence > why_cheap_grounded.confidence:
                        log.info(f"Retry improved why_cheap confidence: {why_cheap_grounded.confidence:.2f} -> {retry_grounded.confidence:.2f}")
                        results["why_cheap"] = retry_result.text
                        results["why_cheap_cost"] = results.get("why_cheap_cost", 0) + retry_result.cost
                        why_cheap_grounded = retry_grounded

                results["why_cheap_grounding"] = {
                    "confidence": why_cheap_grounded.confidence,
                    "recency_score": why_cheap_grounded.recency_score,
                    "contradictions": why_cheap_grounded.contradictions,
                    "warnings": why_cheap_grounded.warnings,
                    "entity_confidence": why_cheap_grounded.entity_check.confidence,
                    "claims_confirmed": sum(1 for c in why_cheap_grounded.claims if c.status == "confirmed"),
                    "claims_contradicted": sum(1 for c in why_cheap_grounded.claims if c.status == "contradicted"),
                }

                if not why_cheap_grounded.grounded:
                    results["why_cheap_warning"] = "LOW CONFIDENCE — web research may be unreliable"

            except Exception as e:
                log.warning(f"Grounding failed for why_cheap ({ticker}): {e}")

            # --- Bull case ---
            bull_query = (
                f"{fact_anchor}\n\n"
                f"What is the bull case for {company} ({ticker})? "
                f"Upcoming catalysts, competitive advantages the market is missing, "
                f"management actions that signal confidence. Be specific."
            ) if fact_anchor else (
                f"What is the bull case for {company} ({ticker})? "
                f"Upcoming catalysts, competitive advantages the market is missing, "
                f"management actions that signal confidence. Be specific."
            )

            bull_result = await _aio.wait_for(
                self.web_search.search(
                    query=bull_query,
                    context={"agent": "thesis", "ticker": ticker},
                ),
                timeout=90.0,
            )
            results["bull_case"] = bull_result.text
            results["bull_case_cost"] = bull_result.cost
            results["bull_case_summary"] = bull_result.text[:200] if bull_result.text else ""

            # Post-search grounding for bull_case
            try:
                bull_grounded = ground_web_research(
                    bull_result.text, data, ticker, company, fact_anchor,
                )

                # Re-search on low confidence
                if bull_grounded.confidence < 0.4:
                    log.info(f"Low confidence ({bull_grounded.confidence:.2f}) on bull_case for {ticker}, retrying with tighter query")
                    retry_query = (
                        f"{fact_anchor}\n\n"
                        f"What is the bull case for {ticker} {company}? "
                        f"Industry: {industry}. Sector: {sector}. "
                        f"Focus specifically on {company} ({ticker}) only. "
                        f"Catalysts, competitive moat, insider buying, share buybacks. Be specific."
                    ) if fact_anchor else (
                        f"What is the bull case for {ticker} {company}? "
                        f"Industry: {industry}. Sector: {sector}. "
                        f"Focus specifically on {company} ({ticker}) only. "
                        f"Catalysts, competitive moat, insider buying, share buybacks. Be specific."
                    )
                    retry_result = await _aio.wait_for(
                        self.web_search.search(
                            query=retry_query,
                            context={"agent": "thesis", "ticker": ticker},
                        ),
                        timeout=60.0,
                    )
                    retry_grounded = ground_web_research(
                        retry_result.text, data, ticker, company, fact_anchor,
                    )
                    if retry_grounded.confidence > bull_grounded.confidence:
                        log.info(f"Retry improved bull_case confidence: {bull_grounded.confidence:.2f} -> {retry_grounded.confidence:.2f}")
                        results["bull_case"] = retry_result.text
                        results["bull_case_cost"] = results.get("bull_case_cost", 0) + retry_result.cost
                        results["bull_case_summary"] = retry_result.text[:200] if retry_result.text else ""
                        bull_grounded = retry_grounded

                results["bull_case_grounding"] = {
                    "confidence": bull_grounded.confidence,
                    "recency_score": bull_grounded.recency_score,
                    "contradictions": bull_grounded.contradictions,
                    "warnings": bull_grounded.warnings,
                    "entity_confidence": bull_grounded.entity_check.confidence,
                    "claims_confirmed": sum(1 for c in bull_grounded.claims if c.status == "confirmed"),
                    "claims_contradicted": sum(1 for c in bull_grounded.claims if c.status == "contradicted"),
                }

                if not bull_grounded.grounded:
                    results["bull_case_warning"] = "LOW CONFIDENCE — web research may be unreliable"

            except Exception as e:
                log.warning(f"Grounding failed for bull_case ({ticker}): {e}")

        except Exception as e:
            log.warning(f"Web research failed for {ticker}: {e}")
            results["error"] = str(e)

        # Clean conversational artifacts from web research prose
        if results.get("why_cheap"):
            results["why_cheap"] = clean_prose(results["why_cheap"], THESIS_SPEC)
        if results.get("bull_case"):
            results["bull_case"] = clean_prose(results["bull_case"], THESIS_SPEC)

        return results

    def _calculate_valuation(self, ticker: str, data: dict) -> dict:
        """Simple valuation model. Thesis provides napkin-math fair value."""
        price = safe_float(data.get("price", 0))
        pe = safe_float(data.get("pe", 0))

        # Prefer actual EPS from screener (owner earnings), fall back to price/pe
        eps = safe_float(data.get("owner_eps", 0))
        if eps <= 0:
            eps = price / pe if pe > 0 else 0

        growth = safe_float(data.get("revenue_growth", 0))
        earnings_growth = safe_float(data.get("earnings_growth", 0))

        # Simple: fair PE based on growth
        if growth > 0.20:
            fair_pe = 30
        elif growth > 0.10:
            fair_pe = 22
        elif growth > 0.05:
            fair_pe = 17
        else:
            fair_pe = 14

        fair_value = eps * fair_pe if eps > 0 else price

        return {
            "fair_value_base": round(fair_value, 2),
            "method": "growth_adjusted_pe",
            "eps": round(eps, 2),
            "current_pe": round(pe, 1),
            "fair_pe": fair_pe,
            "growth_rate": round(growth * 100, 1),
            "earnings_growth": round(earnings_growth * 100, 1),
        }
