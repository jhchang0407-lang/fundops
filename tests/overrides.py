"""Dependency override factory for FundOps API tests.

Creates a FastAPI TestClient with all external dependencies replaced by test doubles.

CRITICAL: Routes import deps at the top level (e.g., `from backend.api.deps import get_db`).
This binds get_db to the route module's namespace. Patching `backend.api.deps.get_db` alone
does NOT affect the already-bound name in the route module. We must patch the reference
in EVERY module that imports it.

Usage:
    client, db, v2db = create_test_app(mock_llm=my_mock_llm)
    resp = client.get("/api/dashboard")
"""

import sqlite3
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.core.db import FundOpsDB, SCHEMA_SQL
from backend.core.db_v2 import ScreenerV2DB, V2_SCHEMA_SQL
from backend.api.jobs import JobQueue


def create_in_memory_db() -> tuple[FundOpsDB, ScreenerV2DB]:
    """Create in-memory SQLite DB with both v1 and v2 schemas."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    db = FundOpsDB.__new__(FundOpsDB)
    db.conn = conn
    db.db_path = ":memory:"

    v2db = ScreenerV2DB(conn=conn)

    return db, v2db


# All modules that import deps at the top level and need patching
_ROUTE_MODULES = [
    'backend.api.deps',
    'backend.api.routes.agents',
    'backend.api.routes.dashboard',
    'backend.api.routes.pipeline',
    'backend.api.routes.portfolio_routes',
    'backend.api.routes.review',
    'backend.api.routes.config_routes',
    'backend.api.routes.screener_config',
    'backend.api.routes.memory',
    'backend.api.routes.strategy',
    'backend.api.routes.learning',
]


def create_test_app(
    mock_llm=None,
    mock_fmp=None,
    mock_yf=None,
    mock_sec=None,
    mock_web_search=None,
    db=None,
    v2db=None,
):
    """Create a FastAPI TestClient with all deps overridden."""
    if db is None or v2db is None:
        db, v2db = create_in_memory_db()

    job_queue = JobQueue(db=db)

    if mock_llm is None:
        mock_llm = MagicMock()
    if mock_fmp is None:
        mock_fmp = MagicMock()
    if mock_yf is None:
        mock_yf = MagicMock()
    if mock_sec is None:
        mock_sec = MagicMock()
    if mock_web_search is None:
        from backend.core.web_search import NoOpWebSearch
        mock_web_search = NoOpWebSearch()

    # Clear all lru_cache singletons
    from backend.api import deps
    for fn in [deps.get_config, deps.get_db, deps.get_llm, deps.get_yfinance,
               deps.get_sec, deps.get_job_queue, deps.get_memory]:
        if hasattr(fn, 'cache_clear'):
            fn.cache_clear()

    # Build the patch map: for each dep function, patch it in deps AND every route module
    _patchers = []

    # Map of function name → replacement
    dep_overrides = {
        'get_db': lambda: db,
        'get_v2db': lambda: v2db,
        'get_llm': lambda: mock_llm,
        'get_fmp': lambda: mock_fmp,
        'get_yfinance': lambda: mock_yf,
        'get_sec': lambda: mock_sec,
        'get_web_search': lambda: mock_web_search,
        'get_job_queue': lambda: job_queue,
        'get_library': lambda: MagicMock(),
        'get_outcome_checker': lambda: MagicMock(),
        'get_memory': lambda: MagicMock(),
    }

    # Patch each function in every module that imports it
    import importlib
    for module_path in _ROUTE_MODULES:
        try:
            mod = importlib.import_module(module_path)
        except ImportError:
            continue
        for fn_name, replacement in dep_overrides.items():
            if hasattr(mod, fn_name):
                p = patch(f'{module_path}.{fn_name}', new=replacement)
                _patchers.append(p)
                p.start()

    # Patch the local _get_db() in strategy.py and learning.py
    for mod_path in ['backend.api.routes.strategy', 'backend.api.routes.learning']:
        try:
            mod = importlib.import_module(mod_path)
            if hasattr(mod, '_get_db'):
                p = patch(f'{mod_path}._get_db', new=lambda: v2db)
                _patchers.append(p)
                p.start()
        except ImportError:
            pass

    # Patch ScreenerV2DB constructor to prevent fallback to production DB.
    # Routes do local imports like `from backend.core.db_v2 import ScreenerV2DB`
    # then call ScreenerV2DB(db_path=...) or ScreenerV2DB() internally.
    # We need to intercept at the source module level.
    _original_v2db_init = ScreenerV2DB.__init__

    def _patched_v2db_init(self, conn=None, db_path=None):
        """Redirect all ScreenerV2DB construction to use the test connection."""
        # Reuse the test v2db's connection instead of creating a new one
        self.conn = v2db.conn
        self._owns_conn = False

    p = patch.object(ScreenerV2DB, '__init__', _patched_v2db_init)
    _patchers.append(p)
    p.start()

    from backend.api import app
    client = TestClient(app, raise_server_exceptions=False)

    client._test_db = db
    client._test_v2db = v2db
    client._test_job_queue = job_queue
    client._test_patchers = _patchers

    return client, db, v2db


def cleanup_test_app(client):
    """Stop all monkeypatches."""
    for p in getattr(client, '_test_patchers', []):
        p.stop()
