"""Shared test fixtures for FundOps.

Provides:
- Legacy fixtures (tmp_db, config, mock_llm) for existing tests
- New fixtures (db, v2db, client, seeded_db, sample_constitution) for contract/flow tests
"""

import json
import os
import sys
import tempfile
import sqlite3
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("FMP_API_KEY", "test_key")
os.environ.setdefault("OPENAI_API_KEY", "test_key")
os.environ.setdefault("SEC_USER_AGENT", "FundOps/test")


# ──────────────────────────────────────��───────────────────
# Legacy fixtures (backward compat for existing tests)
# ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    """Create a temporary SQLite database (legacy — prefer `db` fixture)."""
    from backend.core.db import FundOpsDB
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = FundOpsDB(db_path)
    yield db
    db.close()
    os.unlink(db_path)


@pytest.fixture
def config():
    """Load config from project workflow.yaml."""
    from backend.core.config import FundOpsConfig
    project_root = os.path.join(os.path.dirname(__file__), "..")
    config_path = os.path.join(project_root, "config", "workflow.yaml")
    env_path = os.path.join(project_root, ".env")
    return FundOpsConfig(config_path=config_path, env_path=env_path)


@pytest.fixture
def mock_llm():
    """Mock LLM client that returns canned responses (legacy — prefer `structured_mock_llm`)."""
    from backend.core.llm import LLMClient, LLMResult

    class MockLLM(LLMClient):
        def __init__(self):
            super().__init__({"provider": "mock", "model": "mock", "api_key": "mock"})

        async def generate(self, prompt, agent="", **kwargs):
            return LLMResult(text="Mock LLM response. PASS.", tokens_in=100, tokens_out=50,
                           cost=0.001, duration_s=0.1, model="mock", agent=agent)

        async def generate_with_search(self, prompt, agent="", **kwargs):
            return LLMResult(text="Mock web search result.", tokens_in=200, tokens_out=100,
                           cost=0.002, duration_s=0.2, model="mock", agent=agent)

    return MockLLM()


# ──────────────────────────────────────────────────────────
# New fixtures for contract and integration tests
# ──────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """In-memory FundOpsDB with v1 schema."""
    from backend.core.db import FundOpsDB, SCHEMA_SQL
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    db_obj = FundOpsDB.__new__(FundOpsDB)
    db_obj.conn = conn
    db_obj.db_path = ":memory:"
    yield db_obj
    conn.close()


@pytest.fixture
def v2db(db):
    """In-memory ScreenerV2DB sharing connection with `db` fixture."""
    from backend.core.db_v2 import ScreenerV2DB
    v2 = ScreenerV2DB(conn=db.conn)
    yield v2
    # Connection owned by `db` fixture — don't close here


@pytest.fixture
def structured_mock_llm():
    """Mock LLM that returns structured JSON matching agent output formats.

    This is the critical improvement over the legacy mock_llm — agents parse
    JSON from LLM output, so the mock must return valid JSON.
    """
    from backend.core.llm import LLMClient, LLMResult

    # Canned responses keyed by agent name
    AGENT_RESPONSES = {
        "screener": json.dumps({
            "results": [
                {"ticker": "AAPL", "score": 85, "expected_return": 22.5,
                 "reason": "Quality compounder at discount", "quality": 90,
                 "cheapness": 75, "growth": 80, "lens": "compounder"},
            ],
            "universe_size": 200, "scored_count": 200,
        }),
        "thesis": json.dumps({
            "ticker": "AAPL", "company_name": "Apple Inc.",
            "fair_value": 220.0, "current_price": 175.0,
            "expected_return": 25.7, "discount_pct": 20.5,
            "conviction": "high",
            "return_sources": {"discount": 20.5, "growth": 3.0, "margin": 1.2, "dividends": 1.0},
            "thesis_summary": "Quality compounder trading below intrinsic value.",
            "key_assumptions": ["Revenue growth >8% for 3 years", "Gross margin >42%"],
            "anti_signals": [],
            "valuation_method": "DCF",
            "web_research": "Strong competitive moat confirmed by recent earnings.",
        }),
        "ic_review": json.dumps({
            "ticker": "AAPL", "verdict": "PASS", "conviction": 4,
            "base_return": 25.7, "bear_return": 16.2,
            "bear_fair_value": 195.0,
            "key_risks": ["China revenue concentration", "Regulatory risk"],
            "key_assumptions": ["Revenue growth >8%", "Gross margin >42%"],
            "scorecard": {"business_quality": 9, "compounder": 8, "trap_risk": 2, "valuation": 7, "clarity": 8},
            "rationale": "Strong business with adequate margin of safety even in bear case.",
        }),
        "memo": json.dumps({
            "ticker": "AAPL",
            "sections": {
                "executive_summary": "Apple is a quality compounder.",
                "business_analysis": "Leading consumer tech platform.",
                "financial_analysis": "Strong margins and FCF generation.",
                "valuation": "DCF suggests 20% upside.",
                "risks": "China exposure, regulatory headwinds.",
                "recommendation": "Initiate position at current levels.",
            },
        }),
        "allocator": json.dumps({
            "recommendations": [
                {"ticker": "AAPL", "action": "HOLD", "current_weight": 5.0,
                 "target_weight": 5.0, "reason": "On track with thesis."},
            ],
        }),
        "portfolio": json.dumps({
            "health_checks": [
                {"ticker": "AAPL", "health_score": 85, "alerts": [],
                 "assumptions_status": {"Revenue growth >8%": "ok"}},
            ],
        }),
        "strategy_conversation": json.dumps({
            "response": "I understand you want to focus on quality compounders.",
            "extracted_profile": {
                "north_star": "Quality compounders at a discount",
                "dimensions": {"quality": 40, "cheapness": 30, "growth": 30},
            },
        }),
        "codegen": json.dumps({
            "version_id": "v-test-001",
            "scoring_code": "def score(stock, labels):\n    return 50.0\n",
            "label_map": {"quality": {"label": "Quality", "unit": "%"}},
            "explanation": "Basic scoring function.",
        }),
    }

    class StructuredMockLLM(LLMClient):
        def __init__(self):
            super().__init__({"provider": "mock", "model": "mock", "api_key": "mock"})
            self.calls = []  # Track calls for assertions

        async def generate(self, prompt, agent="", **kwargs):
            self.calls.append({"prompt": prompt, "agent": agent, "kwargs": kwargs})
            text = AGENT_RESPONSES.get(agent, '{"status": "ok"}')
            return LLMResult(text=text, tokens_in=100, tokens_out=50,
                           cost=0.001, duration_s=0.1, model="mock", agent=agent)

        async def generate_with_search(self, prompt, agent="", **kwargs):
            self.calls.append({"prompt": prompt, "agent": agent, "kwargs": kwargs, "search": True})
            text = AGENT_RESPONSES.get(agent, '{"status": "ok"}')
            return LLMResult(text=text, tokens_in=200, tokens_out=100,
                           cost=0.002, duration_s=0.2, model="mock", agent=agent)

    return StructuredMockLLM()


@pytest.fixture
def sample_constitution():
    """A complete valid constitution dict with all required fields."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": "const-test-001",
        "name": "Test Strategy",
        "version": 1,
        "north_star": "Quality compounders at a discount",
        "north_star_summary": "Find high-quality businesses trading below intrinsic value",
        "style_identity": "quality_value",
        "time_horizon": "3-5 years",
        "must_have_signals": ["Gross margin >40%", "ROIC >15%", "Revenue growth >8%"],
        "anti_signals": ["Declining margins", "Excessive debt", "Accounting red flags"],
        "ic_hurdles": {
            "base_return_pct": 20,
            "bear_return_pct": 15,
            "haircut_pct": 70,
        },
        "disqualifiers": ["Fraud history", "Chronic value trap"],
        "position_sizing": {
            "max_position_pct": 10,
            "initial_position_pct": 3,
            "concentration_limit_pct": 25,
        },
        "concentration_rules": {"max_sector_pct": 30},
        "sell_discipline": {
            "max_loss_pct": -25,
            "thesis_breach_action": "review",
        },
        "dimensions": {
            "quality": {"weight": 40, "label": "Business Quality"},
            "cheapness": {"weight": 30, "label": "Valuation Discount"},
            "growth": {"weight": 30, "label": "Growth Durability"},
        },
        "sector_routing": None,
        "agent_profiles": {},
        "universe_type": "preset",
        "universe_name": "us_largecap_200",
        "universe_custom": None,
        "autonomy_mode": "suggest",
        "active_version_id": None,
        "created_at": now,
        "updated_at": now,
    }


@pytest.fixture
def seeded_db(db, v2db, sample_constitution):
    """DB pre-loaded with test data: 5 tickers, constitution, screener run, thesis, IC review."""
    now = datetime.now(timezone.utc).isoformat()

    # Insert tickers
    tickers = [
        ("AAPL", "Apple Inc.", "Technology", "Consumer Electronics"),
        ("MSFT", "Microsoft Corp.", "Technology", "Software"),
        ("GOOGL", "Alphabet Inc.", "Technology", "Internet"),
        ("JNJ", "Johnson & Johnson", "Healthcare", "Pharmaceuticals"),
        ("BRK.B", "Berkshire Hathaway", "Financials", "Insurance"),
    ]
    for t, name, sector, industry in tickers:
        db.upsert_ticker(t, company_name=name, sector=sector, industry=industry)

    # Insert constitution
    c = sample_constitution
    v2db.conn.execute("""
        INSERT INTO constitution (id, name, version, north_star, north_star_summary,
            style_identity, time_horizon, must_have_signals, anti_signals, ic_hurdles,
            disqualifiers, position_sizing, concentration_rules, sell_discipline,
            dimensions, sector_routing, agent_profiles, universe_type, universe_name,
            universe_custom, autonomy_mode, active_version_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        c["id"], c["name"], c["version"], c["north_star"], c["north_star_summary"],
        c["style_identity"], c["time_horizon"],
        json.dumps(c["must_have_signals"]), json.dumps(c["anti_signals"]),
        json.dumps(c["ic_hurdles"]), json.dumps(c["disqualifiers"]),
        json.dumps(c["position_sizing"]), json.dumps(c["concentration_rules"]),
        json.dumps(c["sell_discipline"]), json.dumps(c["dimensions"]),
        json.dumps(c["sector_routing"]), json.dumps(c["agent_profiles"]),
        c["universe_type"], c["universe_name"], json.dumps(c["universe_custom"]),
        c["autonomy_mode"], c["active_version_id"], c["created_at"], c["updated_at"],
    ))

    # Insert a screener run — must match the format that /screener/results expects
    # (needs all_scored and handoff_candidates arrays, not flat per-ticker data)
    screener_stocks = [
        {"ticker": "AAPL", "symbol": "AAPL", "companyName": "Apple Inc.", "sector": "Technology",
         "price": 175.0, "dislocation_score": 7.5, "compounder_score": 8.5,
         "quality_score": 9.0, "cheapness_score": 7.5, "health_score": 8.0,
         "expected_return": 22.5, "top_lens": "compounder",
         "grossProfitMargin": 0.43, "returnOnInvestedCapital": 0.28, "revenueGrowth": 0.08},
        {"ticker": "MSFT", "symbol": "MSFT", "companyName": "Microsoft Corp.", "sector": "Technology",
         "price": 380.0, "dislocation_score": 6.0, "compounder_score": 7.5,
         "quality_score": 8.5, "cheapness_score": 6.5, "health_score": 7.5,
         "expected_return": 18.0, "top_lens": "compounder",
         "grossProfitMargin": 0.69, "returnOnInvestedCapital": 0.35, "revenueGrowth": 0.12},
    ]
    db.conn.execute("""
        INSERT INTO agent_runs (ticker, agent, run_at, run_type, scores, verdict, summary, full_output)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ("AAPL", "screener", now, "dual_lens",
          json.dumps({"quality": 90, "cheapness": 75, "growth": 80}),
          "handoff", "Quality compounder at discount",
          json.dumps({"all_scored": screener_stocks, "handoff_candidates": screener_stocks,
                      "universe_size": 200})))

    # Insert a thesis
    db.conn.execute("""
        INSERT INTO agent_runs (ticker, agent, run_at, run_type, fair_value, price_at_run, verdict, summary, full_output)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("AAPL", "thesis", now, "full",
          220.0, 175.0, "bullish", "Quality compounder trading below intrinsic value.",
          json.dumps({
              "fair_value": 220.0, "expected_return": 25.7, "discount_pct": 20.5,
              "conviction": "high",
              "return_sources": {"discount": 20.5, "growth": 3.0, "margin": 1.2, "dividends": 1.0},
              "key_assumptions": ["Revenue growth >8% for 3 years", "Gross margin >42%"],
          })))

    # Insert an IC review
    db.conn.execute("""
        INSERT INTO agent_runs (ticker, agent, run_at, run_type, verdict, summary, full_output)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("AAPL", "ic_review", now, "stress_test",
          "PASS", "Adequate margin of safety in bear case.",
          json.dumps({
              "verdict": "PASS", "conviction": 4,
              "base_return": 25.7, "bear_return": 16.2,
              "key_risks": ["China revenue concentration"],
              "scorecard": {"business_quality": 9, "compounder": 8, "trap_risk": 2},
          })))

    # Insert a v2 screener run so /api/thesis doesn't fall back to production DB
    v2db.create_strategy("strat-test", "Test Strategy")
    v2db.create_version("ver-test", "strat-test", 1, "def score(s,l): return 50")
    screener_handoff = [
        {"ticker": "AAPL", "symbol": "AAPL", "score": 85, "expected_return": 22.5,
         "companyName": "Apple Inc.", "sector": "Technology"},
        {"ticker": "MSFT", "symbol": "MSFT", "score": 78, "expected_return": 18.0,
         "companyName": "Microsoft Corp.", "sector": "Technology"},
    ]
    v2db.record_screener_run(
        run_id="run-seed",
        strategy_version_id="ver-test",
        universe_size=200, scored_count=200,
        top_results=screener_handoff,
        all_results=screener_handoff,
    )

    # Insert a portfolio snapshot
    db.conn.execute("""
        INSERT INTO portfolio_snapshots (snapshot_date, total_value, cash, holdings, alerts, daily_pnl)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now[:10], 100000.0, 20000.0,
          json.dumps([
              {"ticker": "AAPL", "shares": 50, "cost_basis": 170.0, "current_price": 175.0,
               "market_value": 8750.0, "pnl_pct": 2.94, "weight": 8.75},
          ]),
          json.dumps([]), 250.0))

    db.conn.commit()
    v2db.conn.commit()

    return db, v2db


@pytest.fixture
def mock_yfinance():
    """Mock yfinance connector that returns canned price quotes."""
    from unittest.mock import AsyncMock
    from backend.connectors import ConnectorResult

    PRICES = {
        "AAPL": 175.0, "MSFT": 380.0, "GOOGL": 140.0,
        "JNJ": 155.0, "BRK.B": 410.0,
    }

    mock = MagicMock()
    async def _get_quotes(tickers):
        quotes = [{"symbol": t, "price": PRICES.get(t, 100.0)} for t in tickers]
        return ConnectorResult(connector="yfinance", capability="quotes", data=quotes)
    mock.get_quotes = _get_quotes
    mock.test_connection = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_fmp():
    """Mock FMP connector that returns canned data."""
    from unittest.mock import AsyncMock
    from backend.connectors import ConnectorResult

    mock = MagicMock()
    async def _get_quotes(tickers):
        return ConnectorResult(connector="fmp", capability="quotes", data=[])
    mock.get_quotes = _get_quotes
    mock.test_connection = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def client(db, v2db, structured_mock_llm, mock_yfinance, mock_fmp):
    """FastAPI TestClient with all deps overridden."""
    from tests.overrides import create_test_app, cleanup_test_app

    c, _, _ = create_test_app(
        mock_llm=structured_mock_llm,
        mock_yf=mock_yfinance,
        mock_fmp=mock_fmp,
        db=db,
        v2db=v2db,
    )
    yield c
    cleanup_test_app(c)


@pytest.fixture
def seeded_client(seeded_db, structured_mock_llm, mock_yfinance, mock_fmp):
    """FastAPI TestClient with pre-seeded test data."""
    from tests.overrides import create_test_app, cleanup_test_app

    db, v2db = seeded_db
    c, _, _ = create_test_app(
        mock_llm=structured_mock_llm,
        mock_yf=mock_yfinance,
        mock_fmp=mock_fmp,
        db=db,
        v2db=v2db,
    )
    yield c
    cleanup_test_app(c)
