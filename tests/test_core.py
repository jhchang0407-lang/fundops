"""Tests for core modules: DB, config, LLM, financial_data, orchestrator."""

import pytest
from backend.core.financial_data import FinancialData, CompanyProfile
from backend.core.llm import LLMClient, LLMResult, _estimate_cost
from backend.core.web_search import NoOpWebSearch
from backend.agents import AgentResult


# --- FinancialData ---

def test_financial_data_empty():
    profile = CompanyProfile(ticker="AAPL", name="Apple")
    fd = FinancialData(ticker="AAPL", profile=profile)
    assert not fd.is_complete
    assert fd.summary()["annual_periods"] == 0


def test_financial_data_complete():
    profile = CompanyProfile(ticker="AAPL", name="Apple", sector="Tech")
    fd = FinancialData(
        ticker="AAPL", profile=profile,
        financials_annual=[{"revenue": 100}],
        financials_quarterly=[{"revenue": 25}],
        ratios={"roe": 0.3},
    )
    assert fd.is_complete
    assert fd.summary()["annual_periods"] == 1


def test_financial_data_optional():
    profile = CompanyProfile(ticker="AAPL", name="Apple")
    fd = FinancialData(ticker="AAPL", profile=profile)
    assert not fd.has_filing_text
    assert not fd.has_estimates
    assert not fd.has_peers


# --- LLM ---

def test_llm_cost_estimation():
    cost = _estimate_cost("gpt-5-mini", 1000, 500)
    assert cost > 0
    assert cost < 0.01  # Should be fractions of a cent


def test_llm_client_init():
    client = LLMClient({"provider": "openai", "model": "gpt-5-mini", "api_key": "test"})
    assert client.model == "gpt-5-mini"
    assert client.max_retries == 2


def test_llm_cost_summary():
    client = LLMClient()
    client._cost_log = [
        {"agent": "thesis", "model": "gpt-5-mini", "tokens_in": 100, "tokens_out": 50, "cost": 0.001, "duration_s": 1.0, "timestamp": 0},
        {"agent": "ic_review", "model": "gpt-5-mini", "tokens_in": 200, "tokens_out": 100, "cost": 0.002, "duration_s": 2.0, "timestamp": 0},
    ]
    summary = client.get_cost_summary()
    assert summary["total_calls"] == 2
    assert summary["total_cost"] == 0.003
    assert "thesis" in summary["by_agent"]


# --- WebSearch ---

@pytest.mark.asyncio
async def test_noop_web_search():
    search = NoOpWebSearch()
    result = await search.search("test query")
    assert result.error == "Web search disabled"
    assert result.text == ""


# --- AgentResult ---

def test_agent_result_event_type():
    r = AgentResult(agent="screener", event_type="handoff")
    assert r.event_type == "handoff"
    assert r.ok


def test_agent_result_failed():
    r = AgentResult(agent="test", status="failed", errors=["boom"])
    assert not r.ok


# --- DB ---

def test_db_upsert_ticker(tmp_db):
    tmp_db.upsert_ticker("AAPL", company_name="Apple", sector="Tech")
    row = tmp_db.conn.execute("SELECT * FROM tickers WHERE ticker = ?", ("AAPL",)).fetchone()
    assert row is not None


def test_db_upsert_update(tmp_db):
    tmp_db.upsert_ticker("AAPL", company_name="Apple", sector="Tech")
    tmp_db.upsert_ticker("AAPL", sector="Technology")
    row = tmp_db.conn.execute("SELECT sector FROM tickers WHERE ticker = ?", ("AAPL",)).fetchone()
    assert row[0] == "Technology"


def test_db_record_run(tmp_db):
    tmp_db.upsert_ticker("AAPL")
    tmp_db.record_run(agent="screener", ticker="AAPL", verdict="handoff",
                      scores={"expected_return": 25.0})
    runs = tmp_db.conn.execute("SELECT * FROM agent_runs WHERE ticker = ?", ("AAPL",)).fetchall()
    assert len(runs) == 1


# --- Config ---

def test_config_loads(config):
    assert config.resolved.get("name") is not None
    agents = config.resolved.get("agents", {})
    assert "screener" in agents or "scout" in agents  # renamed from scout → screener


def test_config_validate(config):
    warnings = config.validate()
    # May have warnings about test keys, but shouldn't crash
    assert isinstance(warnings, list)


# --- Orchestrator ---

def test_orchestrator_trigger_matching():
    from backend.orchestrator import Orchestrator
    orch = Orchestrator()
    assert orch._matches_trigger("scout.handoff", "scout.handoff")
    assert not orch._matches_trigger("scout.handoff", "manual")
    assert not orch._matches_trigger("scout.handoff", "daily")
    assert orch._matches_trigger("scout.handoff", "scout.handoff OR val.complete")
    assert not orch._matches_trigger("judge.pass", "scout.handoff OR val.complete")


def test_orchestrator_max_depth():
    from backend.orchestrator import Orchestrator
    orch = Orchestrator(max_depth=3)
    assert orch.max_depth == 3
    assert orch._current_depth == 0
