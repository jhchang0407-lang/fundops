"""Screener Agent — Two-phase discovery via dual lens scoring.

Phase 1: Quick filter using yfinance prices + market data.
  Filters on: market cap, price, basic PE. Fast (~30s for 500 tickers).

Phase 2: SEC EDGAR deep enrichment on survivors (~top 200).
  Pulls: 5yr financials, computes margins, ROIC, FCF, growth, owner earnings,
  backward DCF (implied growth), sector medians for relative comparison.

All fundamentals are computed from raw SEC XBRL data. Never uses
precomputed ratios from yfinance or FMP (they over-standardize and have
date mismatch issues between statements).

Dual lens scoring:
  - Dislocation: stocks cheap vs sector peers
  - Compounder: quality businesses at reasonable discount

Emits event_type="handoff" with handoff_candidates in result.data.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.agents import AgentPlugin, AgentResult
from backend.core.utils import safe_float

log = logging.getLogger("fundops.screener")


class ScreenerAgent(AgentPlugin):
    """Screen universe for undervalued opportunities."""

    name = "screener"
    description = "Discover opportunities via dual lens scoring"

    def __init__(self, config: dict = None, fmp=None, yfinance=None, sec=None, db=None):
        super().__init__(config)
        self.fmp = fmp
        self.yfinance = yfinance
        self.sec = sec
        self.db = db

    async def run(self, context: dict) -> AgentResult:
        """Run the full screening cycle.

        Phase 1: yfinance quick screen (prices, market cap, sector)
        Phase 2: SEC deep enrichment (fundamentals from XBRL)
        Phase 3: Score with dual lens + sector medians
        Phase 4: Build analyst handoff
        """
        t0 = time.time()
        progress = context.get("_update_progress", lambda msg: None)
        config = self.config or {}
        hurdle_pct = config.get("hurdle_pct", 15)
        handoff_config = config.get("handoff", {})
        max_candidates = handoff_config.get("max_candidates", 20)
        min_return = handoff_config.get("min_expected_return_pct", 20)
        min_gm = handoff_config.get("min_gross_margin_pct", 30)
        max_de = handoff_config.get("max_debt_equity", 3.0)
        lenses_raw = config.get("lenses", [])
        lenses = list(lenses_raw) if isinstance(lenses_raw, list) else []

        # Apply constitution scoring_weights to lens weights if present
        scoring_weights = config.get("scoring_weights") or {}
        if scoring_weights and isinstance(scoring_weights, dict):
            # Map constitution weight keys → compounder/dislocation lens weights
            # Accepted keys: cheapness/valuation → cheapness, quality/moat/roic → quality,
            #                 growth/momentum/growth_durability → growth_durability
            comp_w = {}
            disl_w = {}
            for k, v in scoring_weights.items():
                if not isinstance(v, (int, float)) or v <= 0:
                    continue
                k_lower = k.lower()
                if k_lower in ("cheapness", "valuation", "discount"):
                    comp_w["cheapness"] = comp_w.get("cheapness", 0) + v
                    disl_w["cheapness"] = disl_w.get("cheapness", 0) + v * 1.5
                elif k_lower in ("quality", "moat", "roic", "profitability"):
                    comp_w["quality"] = comp_w.get("quality", 0) + v
                    disl_w["quality"] = disl_w.get("quality", 0) + v
                elif k_lower in ("growth", "growth_durability", "momentum", "revenue_growth"):
                    comp_w["growth_durability"] = comp_w.get("growth_durability", 0) + v
                    disl_w["growth"] = disl_w.get("growth", 0) + v
                elif k_lower in ("health", "balance_sheet", "safety"):
                    disl_w["health"] = disl_w.get("health", 0) + v
            # Normalize and apply to lenses
            def _normalize(d):
                t = sum(d.values())
                return {k: round(v / t, 3) for k, v in d.items()} if t > 0 else d
            if comp_w:
                comp_w_norm = _normalize(comp_w)
                found = False
                for lens in lenses:
                    if lens.get("name") == "compounder":
                        lens["weights"] = {**lens.get("weights", {}), **comp_w_norm}
                        found = True
                if not found:
                    lenses.append({"name": "compounder", "weights": comp_w_norm})
            if disl_w:
                disl_w_norm = _normalize(disl_w)
                found = False
                for lens in lenses:
                    if lens.get("name") == "dislocation":
                        lens["weights"] = {**lens.get("weights", {}), **disl_w_norm}
                        found = True
                if not found:
                    lenses.append({"name": "dislocation", "weights": disl_w_norm})
            log.info(f"Constitution scoring_weights applied: {scoring_weights}")

        # How many stocks to deep-enrich with SEC data
        sec_enrichment_limit = config.get("sec_enrichment_limit", 200)

        log.info("=== SCREENER: Phase 1 — Quick filter via yfinance ===")
        progress("Phase 1: Fetching universe...")

        # PHASE 1: Quick screen (yfinance = prices + market data only)
        universe = await self._fetch_universe()
        if not universe:
            return AgentResult(
                agent=self.name,
                status="failed",
                event_type="complete",
                errors=["Failed to fetch stock universe"],
                duration_s=time.time() - t0,
            )

        log.info(f"Universe: {len(universe)} stocks from yfinance")

        # Quick filter: remove obviously unscreenable stocks
        # (no price, no PE, micro cap, etc.)
        quick_filtered = self._quick_filter(universe, config)
        log.info(f"After quick filter: {len(quick_filtered)} stocks survive")
        progress(f"Phase 1 complete: {len(quick_filtered)} stocks. Computing RS momentum...")

        # PHASE 1.5: Compute RS percentiles from yfinance price history (free momentum data)
        # Computed across the FULL universe so percentile ranks are meaningful.
        # No paid API needed — yfinance historical prices are sufficient.
        log.info("=== SCREENER: Phase 1.5 — Computing RS percentiles from price history ===")
        universe = await self._add_rs_percentiles(universe)
        # Build a lookup from ticker → RS values so we can merge into enriched stocks later
        rs_lookup = {
            s.get("symbol", ""): {
                "rs_3m": s.get("rs_3m"),
                "rs_3m_percentile": s.get("rs_3m_percentile"),
                "rs_6m": s.get("rs_6m"),
                "rs_6m_percentile": s.get("rs_6m_percentile"),
            }
            for s in universe if s.get("symbol")
        }

        # PHASE 2: SEC deep enrichment on survivors
        log.info(f"=== SCREENER: Phase 2 — SEC enrichment (top {sec_enrichment_limit}) ===")
        progress(f"Phase 2: SEC enrichment on {min(len(quick_filtered), sec_enrichment_limit)} stocks...")
        enriched = await self._sec_enrich(quick_filtered[:sec_enrichment_limit])
        log.info(f"SEC enriched: {len(enriched)} stocks with computed fundamentals")

        # Persist SEC financial data to ticker_financials for downstream agents
        self._persist_financials(enriched)
        # Clean up raw SEC data from stock dicts (already persisted to DB)
        for stock in enriched:
            stock.pop("_sec_raw", None)

        # PHASE 2.5: Merge RS data + normalize key names for scoring code compatibility
        # RS data was computed on the full universe; now merge into SEC-enriched stocks.
        for stock in enriched:
            ticker = stock.get("symbol", "")
            if ticker in rs_lookup:
                stock.update({k: v for k, v in rs_lookup[ticker].items() if v is not None})
            self._normalize_stock_keys(stock)

        # Apply comprehensive filters (margins, growth, cash flow, quality, etc.)
        filtered = self._apply_sec_filters(enriched, config)
        log.info(f"After SEC filters: {len(filtered)} stocks survive (from {len(enriched)})")

        # Compute sector medians from SEC data for relative comparison
        sector_medians = self._compute_sector_medians(filtered)

        # PHASE 3: Score each stock with dual lens
        log.info("=== SCREENER: Phase 3 — Dual lens scoring ===")
        progress(f"Phase 3: Scoring {len(filtered)} stocks with dual lens...")
        scored = []
        for stock in filtered:
            try:
                stock["_sector_medians"] = sector_medians.get(stock.get("sector", "Unknown"), {})
                result = self._score_stock(stock, lenses)
                if result and result.get("expected_return", 0) >= hurdle_pct:
                    scored.append(result)
            except Exception as e:
                log.debug(f"Scoring failed for {stock.get('symbol', '?')}: {e}")
                continue

        log.info(f"Passed hurdle ({hurdle_pct}%): {len(scored)} stocks")

        # Sort by expected return
        scored.sort(key=lambda x: x.get("expected_return", 0), reverse=True)

        progress(f"Phase 3 complete: {len(scored)} passed hurdle. Building handoff...")

        # PHASE 4: Filter for handoff quality
        handoff = []
        for s in scored:
            gm = safe_float(s.get("grossProfitMargin", 0))
            de = safe_float(s.get("debtEquity", 0))
            if gm * 100 >= min_gm and de <= max_de and s.get("expected_return", 0) >= min_return:
                handoff.append(s)
            if len(handoff) >= max_candidates:
                break

        log.info(f"Handoff candidates: {len(handoff)}")

        # Cross-reference with DB for prior research
        if self.db:
            for h in handoff:
                ticker = h.get("symbol", "")
                try:
                    pipeline = self.db.get_pipeline_status(ticker)
                    h["prior_research"] = bool(pipeline)
                except Exception:
                    h["prior_research"] = False

        # Record judgment events for handoff candidates
        constitution = context.get("constitution")
        try:
            from backend.core.db_v2 import ScreenerV2DB
            db_path = self.db.db_path if self.db else None
            v2db = ScreenerV2DB(db_path=db_path)
            for h in handoff:
                v2db.record_judgment_event(
                    event_type="screened",
                    ticker=h.get("symbol", ""),
                    constitution_version=constitution.get("version") if constitution else None,
                    agent=self.name,
                    data={
                        "expected_return": h.get("expected_return"),
                        "top_lens": h.get("top_lens"),
                        "dislocation_score": h.get("dislocation_score"),
                        "compounder_score": h.get("compounder_score"),
                        "quality_score": h.get("quality_score"),
                    },
                    rationale=f"Screened via {h.get('top_lens', 'unknown')} lens, {h.get('expected_return', 0):.0f}% expected return",
                )
            v2db.close()
        except Exception as e:
            log.debug(f"Judgment events write failed: {e}")

        # Build result
        dislocation_results = [s for s in scored if s.get("top_lens") == "dislocation"]
        compounder_results = [s for s in scored if s.get("top_lens") == "compounder"]
        progress(f"Done — {len(handoff)} handoff candidates ({len(dislocation_results)} dislocation, {len(compounder_results)} compounder)")

        return AgentResult(
            agent=self.name,
            status="complete",
            event_type="handoff" if handoff else "complete",
            data={
                "universe_size": len(universe),
                "quick_filter_passed": len(quick_filtered),
                "sec_enriched": len(enriched),
                "passed_hurdle": len(scored),
                "handoff_candidates": handoff,
                "dislocation_count": len(dislocation_results),
                "compounder_count": len(compounder_results),
                "all_scored": scored[:50],
                "rs_status": (scored[0].get("rs_status") if scored else
                              universe[0].get("rs_status") if universe else "failed"),
            },
            duration_s=time.time() - t0,
        )

    async def _add_rs_percentiles(self, stocks: list[dict]) -> list[dict]:
        """Compute relative strength percentiles from price history.

        Uses FMP historical prices when available (more reliable), falls back
        to yfinance (free but less reliable for large batches).

        RS percentile = how this stock's 3m / 6m price return ranks vs all stocks
        in the universe. 100 = best performer, 0 = worst.

        Adds keys: rs_3m (0-100), rs_6m (0-100) to each stock dict.
        """
        if not stocks:
            return stocks

        tickers = [s.get("symbol", "") for s in stocks if s.get("symbol")]
        if not tickers:
            return stocks

        rs_status = "failed"
        returns_3m: dict[str, float] = {}
        returns_6m: dict[str, float] = {}

        # Try FMP first (more reliable for batch price history)
        if self.fmp and hasattr(self.fmp, 'get_historical_prices_batch'):
            log.info(f"RS: using FMP for {len(tickers)} tickers...")
            try:
                # Process in batches of 30 (FMP limit)
                all_prices = {}
                for i in range(0, len(tickers), 30):
                    batch = tickers[i:i + 30]
                    result = await self.fmp.get_historical_prices_batch(batch)
                    if result.ok and isinstance(result.data, dict):
                        all_prices.update(result.data)
                    await asyncio.sleep(0.5)  # Rate limit

                for ticker in tickers:
                    prices = all_prices.get(ticker, [])
                    if not prices or len(prices) < 10:
                        continue
                    # FMP returns newest first, reverse for chronological
                    prices = list(reversed(prices))
                    now_price = prices[-1].get("close", 0)
                    if now_price <= 0:
                        continue

                    # 3-month return (~63 trading days)
                    idx_3m = max(0, len(prices) - 63)
                    price_3m = prices[idx_3m].get("close", 0)
                    if price_3m > 0:
                        returns_3m[ticker] = (now_price - price_3m) / price_3m

                    # 6-month return
                    price_6m = prices[0].get("close", 0)
                    if price_6m > 0:
                        returns_6m[ticker] = (now_price - price_6m) / price_6m

                if returns_3m:
                    rs_status = "complete" if len(returns_3m) / len(tickers) >= 0.8 else "partial"
                    log.info(f"RS (FMP): {len(returns_3m)} stocks computed")

            except Exception as e:
                log.warning(f"RS (FMP) failed: {e}, falling back to yfinance")

        # Fallback to yfinance if FMP didn't work
        if not returns_3m:
            try:
                import yfinance as yf
                log.info(f"RS: using yfinance for {len(tickers)} tickers...")

                hist = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: yf.download(
                            tickers, period="6mo", interval="1d",
                            auto_adjust=True, progress=False,
                            group_by="ticker",
                        )
                    ),
                    timeout=120.0,
                )

                if hist is not None and not hist.empty:
                    for ticker in tickers:
                        try:
                            if len(tickers) == 1:
                                prices = hist["Close"]
                            else:
                                if ("Close", ticker) in hist.columns:
                                    prices = hist["Close"][ticker]
                                elif ticker in hist.columns.get_level_values(1):
                                    prices = hist["Close"][ticker]
                                else:
                                    continue
                            prices = prices.dropna()
                            if len(prices) < 10:
                                continue
                            now_price = float(prices.iloc[-1])
                            idx_3m = max(0, len(prices) - 63)
                            price_3m = float(prices.iloc[idx_3m])
                            if price_3m > 0:
                                returns_3m[ticker] = (now_price - price_3m) / price_3m
                            price_6m = float(prices.iloc[0])
                            if price_6m > 0:
                                returns_6m[ticker] = (now_price - price_6m) / price_6m
                        except Exception:
                            continue

                    if returns_3m:
                        coverage = len(returns_3m) / len(tickers)
                        rs_status = "complete" if coverage >= 0.8 else "partial"
                        log.info(f"RS (yfinance): {len(returns_3m)} stocks computed")

            except asyncio.TimeoutError:
                log.warning("RS (yfinance): timed out")
            except Exception as e:
                log.warning(f"RS (yfinance) failed: {e}")

        if not returns_3m and not returns_6m:
            log.warning("RS: no data from any source")
            for stock in stocks:
                stock["rs_status"] = "failed"
            return stocks

        # Rank returns → percentiles (0-100)
        def to_percentile(ret_dict: dict[str, float]) -> dict[str, float]:
            if not ret_dict:
                return {}
            sorted_tickers = sorted(ret_dict, key=lambda t: ret_dict[t])
            n = len(sorted_tickers)
            return {t: round((i / (n - 1)) * 100) if n > 1 else 50
                    for i, t in enumerate(sorted_tickers)}

        pct_3m = to_percentile(returns_3m)
        pct_6m = to_percentile(returns_6m)

        for stock in stocks:
            t = stock.get("symbol", "")
            if t in pct_3m:
                stock["rs_3m"] = pct_3m[t]
                stock["rs_3m_percentile"] = pct_3m[t]
            if t in pct_6m:
                stock["rs_6m"] = pct_6m[t]
                stock["rs_6m_percentile"] = pct_6m[t]
            stock["rs_status"] = rs_status

        log.info(f"RS percentiles: {len(pct_3m)} (3m), {len(pct_6m)} (6m) — {rs_status}")
        return stocks

    def _persist_financials(self, enriched: list[dict]) -> None:
        """Persist SEC-enriched financial data to ticker_financials table.

        Builds FinancialData objects from the raw SEC data stored during
        enrichment and batch-writes them to the DB for downstream agents.
        """
        try:
            from backend.core.db_v2 import ScreenerV2DB
            from backend.core.financial_data import FinancialData, CompanyProfile

            db_path = self.db.db_path if self.db else None
            v2db = ScreenerV2DB(db_path=db_path)

            items = []
            for stock in enriched:
                if not stock.get("_sec_enriched") or not stock.get("_sec_raw"):
                    continue

                ticker = stock.get("symbol", "")
                if not ticker:
                    continue

                raw = stock["_sec_raw"]
                prof = raw.get("profile", {})

                fd = FinancialData(
                    ticker=ticker,
                    profile=CompanyProfile(
                        ticker=ticker,
                        name=prof.get("name", stock.get("companyName", "")),
                        sector=prof.get("sector", ""),
                        industry=prof.get("industry", ""),
                        is_bank=prof.get("is_bank", False),
                        is_insurance=prof.get("is_insurance", False),
                        is_reit=prof.get("is_reit", False),
                    ),
                    financials_annual=raw.get("income_statement", []),
                    financials_quarterly=[],
                    ratios=raw.get("ratios", []),
                    market_data={
                        "price": stock.get("price", 0),
                        "marketCap": stock.get("marketCap", 0),
                    },
                    growth=raw.get("growth", []),
                    key_metrics=raw.get("key_metrics", []),
                    source="sec+yfinance",
                )

                items.append({
                    "ticker": ticker,
                    "financial_data": fd.to_dict(),
                    "source": "sec+yfinance",
                })

            if items:
                count = v2db.upsert_ticker_financials_batch(items)
                log.info(f"Persisted {count} ticker financial snapshots to DB")

            v2db.close()
        except Exception as e:
            log.warning(f"Failed to persist ticker financials: {e}")

    def _normalize_stock_keys(self, stock: dict) -> None:
        """Add canonical key aliases so AI scoring code can find the data it needs.

        The screener outputs camelCase keys (SEC XBRL standard).
        AI-generated scoring code often uses different key names.
        This adds aliases for the most common mismatches without changing the originals.

        Also computes derived metrics that scoring code expects but screener doesn't output.
        """
        # ── ROIC ──────────────────────────────────────────────────────────────
        # Scoring code: safe_get(stock, 'roic', ...) — screener outputs returnOnInvestedCapital
        if "roic" not in stock or not stock["roic"]:
            stock["roic"] = stock.get("returnOnInvestedCapital", 0) or 0

        # ── Revenue growth aliases ─────────────────────────────────────────────
        # Scoring code: revenueGrowth3Y — screener outputs revenueGrowth3y (lowercase y)
        if "revenueGrowth3Y" not in stock or not stock["revenueGrowth3Y"]:
            stock["revenueGrowth3Y"] = stock.get("revenueGrowth3y", 0) or 0
        # Common alias: revenue_growth_3y (underscore)
        stock["revenue_growth_3y"] = stock.get("revenueGrowth3Y", 0)
        stock["revenueGrowth3yr"] = stock.get("revenueGrowth3Y", 0)

        # ── Growth consistency ─────────────────────────────────────────────────
        # Scoring code: growthConsistency — screener outputs revenueGrowthConsistency
        if "growthConsistency" not in stock or not stock["growthConsistency"]:
            stock["growthConsistency"] = stock.get("revenueGrowthConsistency", 0) or 0
        stock["growth_consistency"] = stock.get("growthConsistency", 0)

        # ── Earnings yield ─────────────────────────────────────────────────────
        # Scoring code: earnings_yield — screener outputs earningsYield
        # earningsYield is now consistently 0-1 decimal (eps/price), no conversion needed
        if "earnings_yield" not in stock or not stock["earnings_yield"]:
            stock["earnings_yield"] = stock.get("earningsYield", 0) or 0
        stock["earningsYieldDecimal"] = stock.get("earnings_yield", 0)

        # ── Growth gap (implied growth vs actual) ──────────────────────────────
        # Scoring code: growth_gap — "how much faster is real growth vs market expectation"
        # impliedGrowth is the growth % baked into the current stock price (DCF-derived)
        # revenueGrowth is what the company actually grew
        # growth_gap > 0 means company is growing faster than price implies → cheap for growth
        implied = safe_float(stock.get("impliedGrowth", 0)) / 100  # was stored as %
        actual_growth = safe_float(stock.get("revenueGrowth", 0))
        if "growth_gap" not in stock or not stock["growth_gap"]:
            stock["growth_gap"] = actual_growth - implied  # positive = cheap for growth
        # Common alias
        stock["growthGap"] = stock.get("growth_gap", 0)

        # ── Operating margin previous year ─────────────────────────────────────
        # We compute opm_change: stock has current opm but not prev year opm explicitly.
        # Use the operatingMargin field — if we have revenueGrowth1y, we can approximate.
        # If already set, leave it; otherwise derive from opm_change hint in reason string
        if "operatingMarginPrevYear" not in stock or not stock["operatingMarginPrevYear"]:
            opm = safe_float(stock.get("operatingMargin", 0))
            opm_change = safe_float(stock.get("operatingMarginChange", 0))
            # Store prev year so scoring code can compute opm_change = opm - opm_prev
            stock["operatingMarginPrevYear"] = (opm - opm_change) if opm_change else (opm - 0.005)

        # ── FCF yield ─────────────────────────────────────────────────────────
        # fcfYield may be stored as ratio (fcf/mktcap) OR as %; normalize both:
        fcy = safe_float(stock.get("fcfYield", 0))
        stock["fcf_yield"] = fcy
        stock["fcfYieldDecimal"] = fcy / 100 if fcy > 1 else fcy

        # ── Momentum aliases (RS data if computed) ─────────────────────────────
        rs3 = stock.get("rs_3m") or stock.get("rs_3m_percentile")
        rs6 = stock.get("rs_6m") or stock.get("rs_6m_percentile")
        if rs3 is not None:
            stock["relativeStrength3m"] = rs3
            stock["rs3m"] = rs3
            stock["momentum_3m"] = rs3
        if rs6 is not None:
            stock["relativeStrength6m"] = rs6
            stock["rs6m"] = rs6
            stock["momentum_6m"] = rs6

        # ── Piotroski aliases ──────────────────────────────────────────────────
        # If piotroski is None (quality score calculation failed), default to 5 (neutral)
        if stock.get("piotroski") is None:
            stock["piotroski"] = 5
        stock["piotroski_score"] = stock.get("piotroski", 5)
        stock["f_score"] = stock.get("piotroski", 5)

        # ── Additional common aliases ──────────────────────────────────────────
        stock["gross_margin"] = stock.get("grossProfitMargin", 0)
        stock["operating_margin"] = stock.get("operatingMargin", 0)
        stock["net_margin"] = stock.get("netProfitMargin", 0)
        stock["revenue_growth"] = stock.get("revenueGrowth", 0)
        stock["revenue_growth_1y"] = stock.get("revenueGrowth1y", 0) or stock.get("revenueGrowth", 0)
        stock["debt_to_equity"] = stock.get("debtEquity", 0)
        stock["fcf_conversion"] = stock.get("fcfConversion", 0)
        stock["pe_ratio"] = stock.get("pe", 0)
        stock["market_cap"] = stock.get("marketCap", 0)

    async def _fetch_universe(self) -> list[dict]:
        """Fetch stock universe — yfinance for prices only."""
        from backend.data.universes import load_preset_async, load_custom

        universe_preset = self.config.get("universe", "us_largecap_200")
        custom_tickers = self.config.get("custom_tickers", "")

        if custom_tickers:
            tickers = load_custom(custom_tickers)
            log.info(f"Using custom universe: {len(tickers)} tickers")
        else:
            tickers = await load_preset_async(universe_preset)
            log.info(f"Using preset '{universe_preset}': {len(tickers)} tickers")

        if not tickers:
            log.error("No tickers in universe")
            return []

        # yfinance = prices + market data ONLY
        if self.yfinance:
            log.info(f"Fetching {len(tickers)} tickers via yfinance...")
            result = await self.yfinance.get_quotes(tickers)
            if result.ok and result.data:
                log.info(f"yfinance returned {len(result.data)} quotes")
                return result.data

        return []

    def _quick_filter(self, universe: list[dict], config: dict) -> list[dict]:
        """Phase 1 filter using yfinance market data only.

        Removes stocks that obviously won't pass:
        - No price or very low price (<$1 penny stocks)
        - Market cap below minimum (default $500M)
        - No PE (can't compute earnings yield)
        - Negative PE (unprofitable — unless config allows)
        """
        min_price = config.get("min_price", 1.0)
        min_market_cap = config.get("min_market_cap", 500_000_000)
        max_market_cap = config.get("max_market_cap", 0)  # 0 = no cap
        allow_negative_pe = config.get("allow_negative_pe", False)
        excluded_raw = config.get("excluded_sectors", [])
        if isinstance(excluded_raw, str):
            excluded_sectors = set(s.strip() for s in excluded_raw.split(",") if s.strip())
        elif isinstance(excluded_raw, list):
            excluded_sectors = set(excluded_raw)
        else:
            excluded_sectors = set()

        filtered = []
        for stock in universe:
            price = safe_float(stock.get("price", 0))
            mktcap = safe_float(stock.get("marketCap", 0))
            pe = safe_float(stock.get("pe", 0))
            sector = stock.get("sector", "")

            if price < min_price:
                continue
            if mktcap < min_market_cap:
                continue
            if max_market_cap > 0 and mktcap > max_market_cap:
                continue
            if sector in excluded_sectors:
                continue
            if pe <= 0 and not allow_negative_pe:
                continue

            filtered.append(stock)

        # Sort by PE (cheapest first) to prioritize SEC enrichment
        filtered.sort(key=lambda x: safe_float(x.get("pe", 999)))
        return filtered

    async def _sec_enrich(self, stocks: list[dict]) -> list[dict]:
        """Phase 2: Pull SEC EDGAR fundamentals for each stock.

        Computes ALL metrics from raw XBRL:
        - Margins (gross, operating, net, EBITDA, FCF)
        - Returns (ROE, ROA, ROIC, ROCE)
        - Growth (revenue, earnings, FCF)
        - Leverage (D/E, net debt/EBITDA, interest coverage)
        - Cash flow quality (FCF conversion, income quality)
        - Owner earnings (Buffett-style)
        - Backward DCF (implied growth rate priced in)

        Rate limited to SEC's 10 req/sec. Cached 12-24hr.
        Runs concurrently (up to 8 at a time) to respect SEC rate limits.
        """
        if not self.sec:
            log.warning("No SEC connector — falling back to yfinance data (less accurate)")
            return stocks

        from backend.core.sec import statements, ratios, profile
        from backend.core.quality_scores import compute_quality_scores

        total = len(stocks)
        # SEC allows ~10 req/sec; each stock pulls ~3-5 requests, so cap at 8 concurrent
        sec_semaphore = asyncio.Semaphore(8)

        async def enrich_one(stock: dict) -> dict:
            ticker = stock.get("symbol", "")
            if not ticker:
                return stock

            async with sec_semaphore:
                try:
                    # Pull 5 years of annual statements from SEC XBRL
                    stmts = await asyncio.wait_for(
                        asyncio.to_thread(statements.get_annual_statements, ticker, years=5),
                        timeout=30.0,
                    )

                    if not stmts or not stmts.get("income_statement"):
                        log.debug(f"{ticker}: no SEC data, skipping")
                        stock["_sec_enriched"] = False
                        return stock

                    inc = stmts["income_statement"]
                    bs = stmts["balance_sheet"]
                    cf = stmts["cash_flow"]

                    # Compute ratios from raw XBRL
                    computed_ratios = ratios.calculate_ratios(inc, bs, cf)
                    computed_growth = ratios.calculate_growth(inc, cf)
                    computed_metrics = ratios.calculate_key_metrics(inc, bs, cf)
                    computed_owner = ratios.calculate_owner_earnings(inc, cf)

                    # Get most recent year's data
                    latest_ratios = computed_ratios[0] if computed_ratios else {}
                    latest_growth = computed_growth[0] if computed_growth else {}
                    latest_metrics = computed_metrics[0] if computed_metrics else {}
                    latest_owner = computed_owner[0] if computed_owner else {}
                    latest_inc = inc[0] if inc else {}
                    latest_bs = bs[0] if bs else {}
                    latest_cf = cf[0] if cf else {}

                    # Get profile for sector classification
                    try:
                        prof = await asyncio.to_thread(profile.get_profile, ticker)
                        stock["sector"] = prof.get("sector", stock.get("sector", ""))
                        stock["industry"] = prof.get("industry", stock.get("industry", ""))
                        stock["subsector"] = prof.get("subsector", "")
                        stock["isBank"] = prof.get("isBank", False)
                        stock["isInsurance"] = prof.get("isInsurance", False)
                        stock["isReit"] = prof.get("isReit", False)
                    except Exception:
                        pass

                    # --- Merge SEC computed data into stock dict ---

                    # Margins (from ratios, 0-1 scale)
                    stock["grossProfitMargin"] = latest_ratios.get("grossProfitMargin", 0) or 0
                    stock["operatingMargin"] = latest_ratios.get("operatingProfitMargin", 0) or 0
                    stock["netProfitMargin"] = latest_ratios.get("netProfitMargin", 0) or 0
                    stock["ebitdaMargin"] = latest_ratios.get("ebitdaMargin", 0) or 0
                    stock["fcfMargin"] = latest_ratios.get("freeCashFlowMargin", 0) or 0

                    # Returns
                    stock["returnOnEquity"] = latest_ratios.get("returnOnEquity", 0) or 0
                    stock["returnOnAssets"] = latest_ratios.get("returnOnAssets", 0) or 0
                    stock["returnOnInvestedCapital"] = latest_ratios.get("returnOnInvestedCapital", 0) or 0

                    # Growth (from growth calc, -1 to +N scale)
                    stock["revenueGrowth"] = latest_growth.get("revenueGrowth", 0) or 0
                    stock["earningsGrowth"] = latest_growth.get("netIncomeGrowth", 0) or 0
                    stock["fcfGrowth"] = latest_growth.get("freeCashFlowGrowth", 0) or 0

                    # Leverage
                    stock["debtEquity"] = latest_ratios.get("debtToEquity", 0) or 0
                    stock["netDebtToEbitda"] = latest_ratios.get("netDebtToEBITDA", 0) or 0
                    stock["interestCoverage"] = latest_ratios.get("interestCoverage", 0) or 0
                    stock["currentRatio"] = latest_ratios.get("currentRatio", 0) or 0

                    # Cash flow quality
                    stock["fcfConversion"] = latest_ratios.get("freeCashFlowConversion", 0) or 0
                    stock["incomeQuality"] = latest_ratios.get("incomeQuality", 0) or 0
                    stock["capexToRevenue"] = latest_ratios.get("capitalExpenditureToRevenue", 0) or 0

                    # Owner earnings
                    stock["ownerEarnings"] = latest_owner.get("ownerEarnings", 0) or 0
                    stock["ownerEarningsPerShare"] = latest_owner.get("ownersEarningsPerShare", 0) or 0
                    stock["maintenanceCapex"] = latest_owner.get("maintenanceCapex", 0) or 0

                    # Per-share metrics
                    stock["fcfPerShare"] = latest_metrics.get("freeCashFlowPerShare", 0) or 0
                    stock["bookValuePerShare"] = latest_metrics.get("bookValuePerShare", 0) or 0
                    stock["tangibleBookPerShare"] = latest_metrics.get("tangibleBookValuePerShare", 0) or 0

                    # Raw financials for backward DCF
                    stock["revenue"] = safe_float(latest_inc.get("revenue", 0))
                    stock["netIncome"] = safe_float(latest_inc.get("netIncome", 0))
                    stock["freeCashFlow"] = safe_float(latest_cf.get("freeCashFlow", 0))
                    stock["totalEquity"] = safe_float(latest_bs.get("totalStockholdersEquity", 0))
                    stock["shares"] = safe_float(latest_inc.get("weightedAverageShsOutDil", 0))

                    # Backward DCF: what growth rate is priced into current price?
                    stock["impliedGrowth"] = self._compute_implied_growth(stock)

                    # FCF yield
                    price = safe_float(stock.get("price", 0))
                    mktcap = safe_float(stock.get("marketCap", 0))
                    fcf = safe_float(stock.get("freeCashFlow", 0))
                    stock["fcfYield"] = (fcf / mktcap) if mktcap > 0 else 0

                    # Earnings yield (from actual SEC EPS, not yfinance)
                    # Stored as 0-1 decimal like all other ratios (0.05 = 5%)
                    eps = safe_float(latest_inc.get("epsDiluted", 0))
                    stock["earningsYield"] = (eps / price) if price > 0 and eps > 0 else 0

                    # Quality scores (Piotroski, Altman Z, composite)
                    try:
                        quality = compute_quality_scores(inc, bs, cf)
                        stock["piotroski"] = quality.get("piotroski")
                        stock["altman_z"] = quality.get("altman_z")
                        stock["quality_composite"] = quality.get("quality_composite")
                    except Exception:
                        pass

                    # Multi-year growth CAGRs
                    if len(inc) >= 2:
                        rev_list = [safe_float(s.get("revenue", 0)) for s in inc]
                        eps_list = [safe_float(s.get("epsDiluted", 0)) for s in inc]
                        fcf_list = [safe_float(s.get("freeCashFlow", 0)) for s in cf] if cf else []

                        stock["revenueGrowth1y"] = self._yoy_growth(rev_list, 0, 1)
                        stock["revenueGrowth3y"] = self._cagr(rev_list, 0, 3)
                        stock["revenueGrowth5y"] = self._cagr(rev_list, 0, 5)
                        stock["epsGrowth1y"] = self._yoy_growth(eps_list, 0, 1)
                        stock["epsGrowth3y"] = self._cagr(eps_list, 0, 3)
                        stock["fcfGrowth1y"] = self._yoy_growth(fcf_list, 0, 1) if fcf_list else None

                    # Growth consistency (% of years with positive revenue growth)
                    if len(computed_growth) >= 2:
                        rev_growths = [safe_float(g.get("revenueGrowth", 0)) for g in computed_growth[:5]]
                        stock["revenueGrowthConsistency"] = (
                            sum(1 for g in rev_growths if g > 0) / len(rev_growths)
                            if rev_growths else 0
                        )

                    # --- Data quality clamps ---
                    # Clamp obviously wrong values to prevent 293% revenue growth, 880% FCF yield, etc.
                    # Margins: must be in [-1.0, 1.0] (±100%)
                    for margin_key in ("grossProfitMargin", "operatingMargin", "netProfitMargin",
                                       "ebitdaMargin", "fcfMargin"):
                        v = stock.get(margin_key, 0)
                        if v is not None and abs(v) > 1.0:
                            log.debug(f"{ticker}: clamped {margin_key}={v:.4f} to [-1, 1]")
                            stock[margin_key] = max(-1.0, min(1.0, v))

                    # Growth rates: clamp to [-5.0, 5.0] (±500%)
                    for growth_key in ("revenueGrowth", "earningsGrowth", "fcfGrowth",
                                       "revenueGrowth1y", "revenueGrowth3y", "revenueGrowth5y",
                                       "epsGrowth1y", "epsGrowth3y", "fcfGrowth1y"):
                        v = stock.get(growth_key, 0)
                        if v is not None and abs(v) > 5.0:
                            log.debug(f"{ticker}: clamped {growth_key}={v:.4f} to [-5, 5]")
                            stock[growth_key] = max(-5.0, min(5.0, v))

                    # Yields: clamp to [-1.0, 1.0]
                    for yield_key in ("fcfYield", "earningsYield"):
                        v = stock.get(yield_key, 0)
                        if v is not None and abs(v) > 1.0:
                            log.debug(f"{ticker}: clamped {yield_key}={v:.4f} to [-1, 1]")
                            stock[yield_key] = max(-1.0, min(1.0, v))

                    stock["_sec_enriched"] = True

                    # Store raw SEC data for persistence to ticker_financials
                    stock["_sec_raw"] = {
                        "income_statement": inc,
                        "balance_sheet": bs,
                        "cash_flow": cf,
                        "ratios": computed_ratios,
                        "growth": computed_growth,
                        "key_metrics": computed_metrics,
                        "owner_earnings": computed_owner,
                        "profile": {
                            "name": stock.get("companyName", ""),
                            "sector": stock.get("sector", ""),
                            "industry": stock.get("industry", ""),
                            "is_bank": stock.get("isBank", False),
                            "is_insurance": stock.get("isInsurance", False),
                            "is_reit": stock.get("isReit", False),
                        },
                    }

                except asyncio.TimeoutError:
                    log.debug(f"{ticker}: SEC enrichment timed out (30s)")
                    stock["_sec_enriched"] = False
                except Exception as e:
                    log.debug(f"{ticker}: SEC enrichment failed: {e}")
                    stock["_sec_enriched"] = False

            return stock

        log.info(f"SEC enrichment: processing {total} stocks concurrently (8 at a time)...")
        results = await asyncio.gather(*[enrich_one(s) for s in stocks])
        enriched = [r for r in results if r is not None]
        log.info(f"SEC enrichment complete: {len(enriched)}/{total} stocks processed")
        return enriched

    def _apply_sec_filters(self, stocks: list[dict], config: dict) -> list[dict]:
        """Apply all SEC-data-based filters after enrichment.

        Checks every configurable filter from screener_filters.py.
        Each filter is optional: only applied if set in config (non-None).
        """
        # constitution_filters (from active strategy) take priority over base config filters
        filters = config.get("constitution_filters") or config.get("filters", {})
        if not filters:
            return stocks

        def passes(stock: dict) -> bool:
            # --- Profitability ---
            if "min_gross_margin" in filters and filters["min_gross_margin"] is not None:
                if safe_float(stock.get("grossProfitMargin", 0)) * 100 < filters["min_gross_margin"]:
                    return False
            if "min_operating_margin" in filters and filters["min_operating_margin"] is not None:
                if safe_float(stock.get("operatingMargin", 0)) * 100 < filters["min_operating_margin"]:
                    return False
            if "min_net_margin" in filters and filters["min_net_margin"] is not None:
                if safe_float(stock.get("netProfitMargin", 0)) * 100 < filters["min_net_margin"]:
                    return False
            if "min_ebitda_margin" in filters and filters["min_ebitda_margin"] is not None:
                if safe_float(stock.get("ebitdaMargin", 0)) * 100 < filters["min_ebitda_margin"]:
                    return False
            if "min_fcf_margin" in filters and filters["min_fcf_margin"] is not None:
                if safe_float(stock.get("fcfMargin", 0)) * 100 < filters["min_fcf_margin"]:
                    return False
            if "min_roe" in filters and filters["min_roe"] is not None:
                if safe_float(stock.get("returnOnEquity", 0)) * 100 < filters["min_roe"]:
                    return False
            if "min_roa" in filters and filters["min_roa"] is not None:
                if safe_float(stock.get("returnOnAssets", 0)) * 100 < filters["min_roa"]:
                    return False
            if "min_roic" in filters and filters["min_roic"] is not None:
                if safe_float(stock.get("returnOnInvestedCapital", 0)) * 100 < filters["min_roic"]:
                    return False
            if not filters.get("allow_negative_earnings", False):
                if safe_float(stock.get("netIncome", 0)) <= 0:
                    return False

            # --- Growth ---
            if "min_revenue_growth_1y" in filters and filters["min_revenue_growth_1y"] is not None:
                g = stock.get("revenueGrowth1y") or stock.get("revenueGrowth", 0)
                if safe_float(g) * 100 < filters["min_revenue_growth_1y"]:
                    return False
            if "min_revenue_growth_3y" in filters and filters["min_revenue_growth_3y"] is not None:
                g = stock.get("revenueGrowth3y")
                if g is None or safe_float(g) * 100 < filters["min_revenue_growth_3y"]:
                    return False
            if "min_revenue_growth_5y" in filters and filters["min_revenue_growth_5y"] is not None:
                g = stock.get("revenueGrowth5y")
                if g is None or safe_float(g) * 100 < filters["min_revenue_growth_5y"]:
                    return False
            if "min_eps_growth_1y" in filters and filters["min_eps_growth_1y"] is not None:
                g = stock.get("epsGrowth1y")
                if g is None or safe_float(g) * 100 < filters["min_eps_growth_1y"]:
                    return False
            if "min_growth_consistency" in filters and filters["min_growth_consistency"] is not None:
                gc = safe_float(stock.get("revenueGrowthConsistency", 0)) * 100
                if gc < filters["min_growth_consistency"]:
                    return False

            # --- Cash Flow ---
            if filters.get("positive_fcf_required", False):
                if safe_float(stock.get("freeCashFlow", 0)) <= 0:
                    return False
            if "min_fcf_yield_pct" in filters and filters["min_fcf_yield_pct"] is not None:
                if safe_float(stock.get("fcfYield", 0)) * 100 < filters["min_fcf_yield_pct"]:
                    return False
            if "min_fcf_conversion" in filters and filters["min_fcf_conversion"] is not None:
                if safe_float(stock.get("fcfConversion", 0)) * 100 < filters["min_fcf_conversion"]:
                    return False
            if "min_income_quality" in filters and filters["min_income_quality"] is not None:
                if safe_float(stock.get("incomeQuality", 0)) < filters["min_income_quality"]:
                    return False
            if "max_capex_to_revenue" in filters and filters["max_capex_to_revenue"] is not None:
                if safe_float(stock.get("capexToRevenue", 0)) * 100 > filters["max_capex_to_revenue"]:
                    return False

            # --- Balance Sheet ---
            if "max_debt_equity" in filters and filters["max_debt_equity"] is not None:
                if safe_float(stock.get("debtEquity", 0)) > filters["max_debt_equity"]:
                    return False
            if "max_net_debt_ebitda" in filters and filters["max_net_debt_ebitda"] is not None:
                nde = safe_float(stock.get("netDebtToEbitda", 0))
                if nde > filters["max_net_debt_ebitda"]:
                    return False
            if "min_interest_coverage" in filters and filters["min_interest_coverage"] is not None:
                ic = safe_float(stock.get("interestCoverage", 0))
                if ic > 0 and ic < filters["min_interest_coverage"]:
                    return False
            if "min_current_ratio" in filters and filters["min_current_ratio"] is not None:
                if safe_float(stock.get("currentRatio", 0)) < filters["min_current_ratio"]:
                    return False

            # --- Valuation ---
            if "max_pe" in filters and filters["max_pe"] is not None:
                pe = safe_float(stock.get("pe", 0))
                if pe > 0 and pe > filters["max_pe"]:
                    return False
            if "min_earnings_yield" in filters and filters["min_earnings_yield"] is not None:
                if safe_float(stock.get("earningsYield", 0)) * 100 < filters["min_earnings_yield"]:
                    return False
            if "min_revenue" in filters and filters["min_revenue"] is not None:
                if safe_float(stock.get("revenue", 0)) < filters["min_revenue"]:
                    return False

            # --- Backward DCF ---
            if "max_implied_growth" in filters and filters["max_implied_growth"] is not None:
                ig = stock.get("impliedGrowth")
                if ig is not None and ig * 100 > filters["max_implied_growth"]:
                    return False
            if "min_growth_gap" in filters and filters["min_growth_gap"] is not None:
                ig = stock.get("impliedGrowth")
                actual = safe_float(stock.get("revenueGrowth", 0))
                if ig is not None:
                    gap = (actual - ig) * 100
                    if gap < filters["min_growth_gap"]:
                        return False

            # --- Quality Scores ---
            if "min_piotroski" in filters and filters["min_piotroski"] is not None:
                p = stock.get("piotroski")
                if p is not None and p < filters["min_piotroski"]:
                    return False
            if "min_altman_z" in filters and filters["min_altman_z"] is not None:
                z = stock.get("altman_z")
                if z is not None and z < filters["min_altman_z"]:
                    return False
            if "min_quality_score" in filters and filters["min_quality_score"] is not None:
                q = stock.get("quality_composite")
                if q is not None and q < filters["min_quality_score"]:
                    return False

            # --- Size (SEC-computed) ---
            if "min_revenue" in filters and filters["min_revenue"] is not None:
                if safe_float(stock.get("revenue", 0)) < filters["min_revenue"]:
                    return False

            return True

        return [s for s in stocks if passes(s)]

    @staticmethod
    def _yoy_growth(values: list[float], current_idx: int, prior_idx: int) -> float | None:
        """Year-over-year growth rate. values[0] = most recent."""
        if prior_idx >= len(values) or current_idx >= len(values):
            return None
        current = values[current_idx]
        prior = values[prior_idx]
        if prior == 0 or prior is None:
            return None
        return round((current - prior) / abs(prior), 4)

    @staticmethod
    def _cagr(values: list[float], start_idx: int, years: int) -> float | None:
        """Compound annual growth rate. values[0] = most recent."""
        end_idx = start_idx + years
        if end_idx >= len(values):
            end_idx = len(values) - 1
        if end_idx <= start_idx:
            return None
        current = values[start_idx]
        past = values[end_idx]
        n = end_idx - start_idx
        if past <= 0 or current <= 0:
            return None
        return round((current / past) ** (1 / n) - 1, 4)

    def _compute_implied_growth(self, stock: dict) -> float | None:
        """Backward DCF: what growth rate is the market pricing in?

        Uses Gordon Growth Model variant:
            Price = FCF_per_share / (r - g)
            Solve for g: g = r - (FCF_per_share / Price)

        Where r = cost of equity (CAPM-based, using beta).
        If implied growth is very low vs actual growth → stock may be cheap.
        If implied growth is very high vs actual growth → stock may be expensive.
        """
        price = safe_float(stock.get("price", 0))
        fcf_ps = safe_float(stock.get("fcfPerShare", 0))
        beta = safe_float(stock.get("beta", 1.0))

        if price <= 0 or fcf_ps <= 0:
            return None

        # CAPM cost of equity: r = risk_free + beta * equity_risk_premium
        risk_free = 0.045  # ~4.5% 10yr treasury
        erp = 0.055  # ~5.5% equity risk premium
        cost_of_equity = risk_free + beta * erp

        # g = r - FCF_yield
        fcf_yield = fcf_ps / price
        implied_g = cost_of_equity - fcf_yield

        # Clamp to reasonable range (-20% to +30%)
        implied_g = max(-0.20, min(0.30, implied_g))
        return round(implied_g, 4)

    def _compute_sector_medians(self, stocks: list[dict]) -> dict[str, dict]:
        """Compute sector medians from SEC-enriched data for relative comparison."""
        sector_data: dict[str, list[dict]] = {}
        for stock in stocks:
            if not stock.get("_sec_enriched"):
                continue
            s = stock.get("sector", "Unknown")
            sector_data.setdefault(s, []).append(stock)

        sector_medians: dict[str, dict] = {}
        for sector, sector_stocks in sector_data.items():
            def median_of(key):
                vals = [safe_float(s.get(key, 0)) for s in sector_stocks if s.get(key)]
                vals = [v for v in vals if v != 0]  # Exclude zeros
                vals.sort()
                if not vals:
                    return 0
                mid = len(vals) // 2
                return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2

            sector_medians[sector] = {
                "grossProfitMargin": median_of("grossProfitMargin"),
                "operatingMargin": median_of("operatingMargin"),
                "netProfitMargin": median_of("netProfitMargin"),
                "returnOnEquity": median_of("returnOnEquity"),
                "returnOnInvestedCapital": median_of("returnOnInvestedCapital"),
                "fcfYield": median_of("fcfYield"),
                "fcfConversion": median_of("fcfConversion"),
                "debtEquity": median_of("debtEquity"),
                "revenueGrowth": median_of("revenueGrowth"),
                "earningsYield": median_of("earningsYield"),
                "pe": median_of("pe"),
                "count": len(sector_stocks),
            }

        return sector_medians

    def _score_stock(self, stock: dict, lenses: list[dict]) -> dict | None:
        """Score a single stock with dual lens using SEC-computed fundamentals."""
        symbol = stock.get("symbol", "")
        if not symbol:
            return None

        price = safe_float(stock.get("price", 0))
        mktcap = safe_float(stock.get("marketCap", 0))
        if price <= 0 or mktcap <= 0:
            return None

        # --- Pull SEC-computed metrics ---
        gm = safe_float(stock.get("grossProfitMargin", 0))
        om = safe_float(stock.get("operatingMargin", 0))
        nm = safe_float(stock.get("netProfitMargin", 0))
        roe = safe_float(stock.get("returnOnEquity", 0))
        roic = safe_float(stock.get("returnOnInvestedCapital", 0))
        de = safe_float(stock.get("debtEquity", 0))
        rev_growth = safe_float(stock.get("revenueGrowth", 0))
        fcf_yield = safe_float(stock.get("fcfYield", 0))
        fcf_conv = safe_float(stock.get("fcfConversion", 0))
        earnings_yield = safe_float(stock.get("earningsYield", 0))
        implied_growth = stock.get("impliedGrowth")
        income_quality = safe_float(stock.get("incomeQuality", 0))
        interest_coverage = safe_float(stock.get("interestCoverage", 0))
        growth_consistency = safe_float(stock.get("revenueGrowthConsistency", 0))
        sector = stock.get("sector", "")
        medians = stock.get("_sector_medians", {})

        # --- Expected return (napkin math) ---
        # All inputs are 0-1 decimals; convert to percentage for the return calc
        earnings_yield_pct = earnings_yield * 100
        growth_contribution = min(rev_growth * 100, 25)  # Cap at 25%

        # Margin expansion potential: if below sector median, there's upside
        sector_median_om = medians.get("operatingMargin", 0)
        margin_expansion = 0
        if sector_median_om > 0 and om > 0 and om < sector_median_om:
            margin_expansion = min((sector_median_om - om) * 100, 10)

        expected_return = earnings_yield_pct + growth_contribution + margin_expansion

        # --- Dislocation score (cheap vs peers) ---
        # Cheapness: how cheap is this vs sector median?
        sector_median_ey = medians.get("earningsYield", 0)
        sector_median_ey_pct = sector_median_ey * 100
        if sector_median_ey_pct > 0 and earnings_yield_pct > 0:
            cheapness = min(earnings_yield_pct / max(sector_median_ey_pct, 1) * 5, 10)
        else:
            cheapness = min(earnings_yield_pct / 10, 10)

        # Quality: margin quality + return on capital + cash flow quality
        quality = min(
            (gm * 10)  # Gross margin (0-1 → 0-10)
            + (roic * 10 if roic > 0 else roe * 5)  # ROIC preferred over ROE
            + (fcf_conv * 2 if fcf_conv > 0 else 0),  # FCF conversion bonus
            10,
        )

        # Health: balance sheet strength
        health_score = 10
        if de > 3:
            health_score -= 4
        elif de > 1.5:
            health_score -= 2
        if interest_coverage > 0 and interest_coverage < 3:
            health_score -= 2
        if income_quality < 0.5:
            health_score -= 2
        health_score = max(0, health_score)

        # --- Compounder score (quality at reasonable discount) ---
        # Growth durability: consistent revenue growth + high margins
        growth_dur = min(
            (gm * 5)
            + (rev_growth * 50)
            + (growth_consistency * 3),  # Bonus for consistent growers
            10,
        )

        # Default lens weights
        disl_weights = {"cheapness": 0.70, "quality": 0.15, "health": 0.10, "growth": 0.05}
        comp_weights = {"quality": 0.50, "cheapness": 0.30, "growth_durability": 0.20}

        # Override from config
        for lens in lenses:
            if lens.get("name") == "dislocation":
                disl_weights = lens.get("weights", disl_weights)
            elif lens.get("name") == "compounder":
                comp_weights = lens.get("weights", comp_weights)

        dislocation_score = (
            cheapness * disl_weights.get("cheapness", 0.7)
            + quality * disl_weights.get("quality", 0.15)
            + health_score * disl_weights.get("health", 0.1)
            + growth_contribution / 3 * disl_weights.get("growth", 0.05)
        )

        compounder_score = (
            quality * comp_weights.get("quality", 0.5)
            + cheapness * comp_weights.get("cheapness", 0.3)
            + growth_dur * comp_weights.get("growth_durability", 0.2)
        )

        top_lens = "dislocation" if dislocation_score >= compounder_score else "compounder"

        return {
            "symbol": symbol,
            "companyName": stock.get("companyName") or stock.get("name", ""),
            "sector": sector,
            "industry": stock.get("industry", ""),
            "price": price,
            "marketCap": mktcap,
            "pe": safe_float(stock.get("pe", 0)),
            # SEC-computed fundamentals
            "grossProfitMargin": gm,
            "operatingMargin": om,
            "netProfitMargin": nm,
            "returnOnEquity": roe,
            "returnOnInvestedCapital": roic,
            "debtEquity": de,
            "revenueGrowth": rev_growth,
            "earningsGrowth": safe_float(stock.get("earningsGrowth", 0)),
            "earningsYield": round(earnings_yield, 4),
            "fcfYield": round(fcf_yield, 4),
            "fcfConversion": round(fcf_conv, 2),
            "incomeQuality": round(income_quality, 2),
            "ownerEarningsPerShare": safe_float(stock.get("ownerEarningsPerShare", 0)),
            "impliedGrowth": round(implied_growth, 4) if implied_growth is not None else None,
            # Additional margins & growth (computed but previously not output)
            "ebitdaMargin": safe_float(stock.get("ebitdaMargin", 0)),
            "fcfMargin": safe_float(stock.get("fcfMargin", 0)),
            "revenueGrowth1y": safe_float(stock.get("revenueGrowth1y")),
            "revenueGrowth3y": safe_float(stock.get("revenueGrowth3y")),
            "revenueGrowth5y": safe_float(stock.get("revenueGrowth5y")),
            "debtToEbitda": safe_float(stock.get("debtToEbitda", 0)),
            "interestCoverage": round(interest_coverage, 2),
            # Scores
            "expected_return": round(expected_return, 1),
            "dislocation_score": round(dislocation_score, 2),
            "compounder_score": round(compounder_score, 2),
            "top_lens": top_lens,
            "quality_score": round(quality, 1),
            "cheapness_score": round(cheapness, 1),
            "health_score": round(health_score, 1),
            # Return decomposition (percentages for display)
            "return_sources": {
                "discount": round(earnings_yield_pct, 1),
                "growth": round(growth_contribution, 1),
                "margin": round(margin_expansion, 1),
                "dividends": 0,  # Refined by Thesis agent
            },
            # Sector comparison
            "vs_sector": {
                "gm_vs_median": round(gm - medians.get("grossProfitMargin", 0), 4) if medians.get("grossProfitMargin") else None,
                "roe_vs_median": round(roe - medians.get("returnOnEquity", 0), 4) if medians.get("returnOnEquity") else None,
                "ey_vs_median": round(earnings_yield - medians.get("earningsYield", 0), 4) if medians.get("earningsYield") else None,
                "sector_count": medians.get("count", 0),
            },
            "_sec_enriched": stock.get("_sec_enriched", False),
        }
