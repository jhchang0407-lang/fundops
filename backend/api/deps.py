"""Shared dependencies for API routes.

Lazy-initialized singletons for DB, config, connectors, agents, orchestrator, and job queue.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from backend.core.config import FundOpsConfig
from backend.core.db import FundOpsDB
from backend.core.llm import LLMClient
from backend.core.web_search import OpenAIWebSearch, NoOpWebSearch
from backend.connectors.fmp import FMPConnector
from backend.connectors.sec_edgar import SECEdgarConnector
from backend.connectors.yfinance_connector import YFinanceConnector
from backend.api.jobs import JobQueue


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "workflow.yaml"
ENV_PATH = PROJECT_ROOT / ".env"
DB_DIR = Path.home() / ".fundops"
DB_PATH = DB_DIR / "fundops.db"


@lru_cache()
def get_config() -> FundOpsConfig:
    return FundOpsConfig(config_path=CONFIG_PATH, env_path=ENV_PATH)


@lru_cache()
def get_db() -> FundOpsDB:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return FundOpsDB(str(DB_PATH))


@lru_cache()
def get_llm() -> LLMClient:
    config = get_config()
    ai_config = config.resolved.get("connectors", {}).get("ai_model", {})
    return LLMClient(ai_config)


def get_web_search():
    config = get_config()
    ai_config = config.resolved.get("connectors", {}).get("ai_model", {})
    if ai_config.get("api_key"):
        return OpenAIWebSearch(get_llm())
    return NoOpWebSearch()


def get_fmp() -> FMPConnector | None:
    config = get_config()
    market_config = config.resolved.get("connectors", {}).get("market_data", {})
    if market_config.get("api_key"):
        return FMPConnector(market_config)
    return None


@lru_cache()
def get_yfinance() -> YFinanceConnector:
    return YFinanceConnector()


@lru_cache()
def get_sec() -> SECEdgarConnector:
    return SECEdgarConnector()


@lru_cache()
def get_job_queue() -> JobQueue:
    return JobQueue(db=get_db())


def get_v2db():
    """Get a ScreenerV2DB instance for learning/library operations.

    Uses the same DB path as get_db() so all data lives in one database.
    """
    from backend.core.db_v2 import ScreenerV2DB
    return ScreenerV2DB(db_path=str(DB_PATH))


def get_library():
    """Get a LibraryAgent instance for similarity lookups."""
    from backend.agents.library import LibraryAgent
    return LibraryAgent(db=get_db(), v2db=get_v2db())


def get_outcome_checker():
    """Get an OutcomeCheckerAgent instance."""
    from backend.agents.outcome_checker import OutcomeCheckerAgent
    return OutcomeCheckerAgent(
        db=get_v2db(),
        yfinance=get_yfinance(),
        sec=get_sec(),
        web_search=get_web_search(),
    )


@lru_cache()
def get_memory():
    """Get a MemoryStore instance for persistent memory."""
    from backend.core.memory import MemoryStore
    return MemoryStore()
