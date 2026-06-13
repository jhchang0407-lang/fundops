"""Local FundOps Workspace database.

One SQLite file owns the Workspace Owner's retained state (ADR-0018, ADR-0052).
This is the new clean baseline (ADR-0029); migrations are forward-only from here
(ADR-0030). All writes flow through platform stores (ADR-0031) — application code
must not hand-roll SQL against this connection.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 4

DEFAULT_DB_DIR = Path.home() / ".fundops"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "workspace.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(text: str | None, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


# --- Baseline schema -------------------------------------------------------
# Normalized records for identity, relationships, queryable state, provenance,
# and projections; JSON payloads for artifact bodies and source-shaped records
# (ADR-0019).

BASELINE_DDL = """
CREATE TABLE IF NOT EXISTS workspace_meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

-- Stable investment identity beyond tickers (ADR-0023)
CREATE TABLE IF NOT EXISTS investment_entities (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  cik TEXT,
  sector TEXT,
  industry TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ticker_aliases (
  ticker TEXT NOT NULL,
  entity_id TEXT NOT NULL REFERENCES investment_entities(id),
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  source TEXT,
  PRIMARY KEY (ticker, valid_from)
);
CREATE INDEX IF NOT EXISTS idx_ticker_aliases_entity ON ticker_aliases(entity_id);

-- Constitution: immutable versions, typed criteria (ADR-0003, ADR-0006)
CREATE TABLE IF NOT EXISTS constitution_versions (
  id TEXT PRIMARY KEY,
  version_number INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','superseded')),
  north_star TEXT,
  style_blend TEXT,
  narrative TEXT,
  version_rationale TEXT NOT NULL,
  source_proposal_id TEXT,
  created_at TEXT NOT NULL,
  activated_at TEXT
);
CREATE TABLE IF NOT EXISTS strategy_criteria (
  id TEXT PRIMARY KEY,
  version_id TEXT NOT NULL REFERENCES constitution_versions(id),
  criterion_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('screen','rank','research_review','ic_hurdle','preference')),
  metric TEXT,
  operator TEXT,
  value TEXT,
  weight REAL,
  data_support_level TEXT NOT NULL,
  rule_rationale TEXT NOT NULL,
  rule_source TEXT NOT NULL,
  interpretation TEXT
);
CREATE INDEX IF NOT EXISTS idx_criteria_version ON strategy_criteria(version_id);

-- Strategy proposals: reviewable envelopes (ADR-0007, ADR-0009)
CREATE TABLE IF NOT EXISTS strategy_proposals (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('pending','accepted','rejected','cancelled')),
  kind TEXT NOT NULL DEFAULT 'strategy',
  payload TEXT NOT NULL,
  validation TEXT,
  rationale TEXT,
  chat_session_id TEXT,
  created_at TEXT NOT NULL,
  decided_at TEXT,
  resulting_version_id TEXT
);

-- Deterministic per-capability projection of the Constitution (ADR-0002)
CREATE TABLE IF NOT EXISTS settings_projections (
  version_id TEXT NOT NULL,
  capability TEXT NOT NULL,
  settings TEXT NOT NULL,
  summary_text TEXT NOT NULL,
  review_items TEXT,
  generated_at TEXT NOT NULL,
  PRIMARY KEY (version_id, capability)
);

CREATE TABLE IF NOT EXISTS universe_versions (
  id TEXT PRIMARY KEY,
  constitution_version_id TEXT,
  name TEXT NOT NULL,
  tickers TEXT NOT NULL,
  exclusions TEXT,
  source TEXT,
  created_at TEXT NOT NULL
);

-- Structured strategy memory; raw chat is evidence only (ADR-0011)
CREATE TABLE IF NOT EXISTS strategy_memory (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  content TEXT NOT NULL,
  source TEXT,
  created_at TEXT NOT NULL,
  superseded_by TEXT
);
CREATE TABLE IF NOT EXISTS chat_sessions (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  server_session_id TEXT,
  summary TEXT
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES chat_sessions(id),
  role TEXT NOT NULL,
  mode TEXT,
  content TEXT NOT NULL,
  refs TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);

-- Canonical evidence (ADR-0021, ADR-0025, ADR-0027)
CREATE TABLE IF NOT EXISTS evidence_sources (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('filing','provider','web','user','model')),
  locator TEXT,
  title TEXT,
  publisher TEXT,
  content_hash TEXT,
  retention_tier TEXT NOT NULL DEFAULT 'identity'
    CHECK (retention_tier IN ('identity','excerpt','normalized','snapshot')),
  excerpt TEXT,
  snapshot TEXT,
  fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_records (
  id TEXT PRIMARY KEY,
  family TEXT NOT NULL CHECK (family IN (
    'financial_metric','filing_citation','market_data','research_claim',
    'model_finding','user_response','workflow_judgment','portfolio_event')),
  entity_id TEXT,
  ticker TEXT,
  as_of TEXT,
  captured_at TEXT NOT NULL,
  payload TEXT NOT NULL,
  source_id TEXT REFERENCES evidence_sources(id),
  quality TEXT,
  superseded_by TEXT,
  created_by_run_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence_records(entity_id, family);
CREATE TABLE IF NOT EXISTS evidence_bundles (
  id TEXT PRIMARY KEY,
  manifest TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- Financial data: reported facts vs calculated observations (ADR-0042..0047)
CREATE TABLE IF NOT EXISTS reported_financial_facts (
  id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL,
  concept TEXT NOT NULL,
  taxonomy TEXT,
  period_end TEXT NOT NULL,
  period_type TEXT NOT NULL CHECK (period_type IN ('annual','quarterly','instant')),
  value REAL,
  unit TEXT,
  source_id TEXT,
  accession TEXT,
  filed_at TEXT,
  mapped_concept TEXT,
  superseded_by TEXT,
  captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_entity ON reported_financial_facts(entity_id, concept, period_end);
CREATE TABLE IF NOT EXISTS financial_observations (
  id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  period_end TEXT NOT NULL,
  period_type TEXT NOT NULL CHECK (period_type IN ('annual','quarterly','ttm')),
  value REAL,
  unit TEXT,
  is_calculated INTEGER NOT NULL DEFAULT 0,
  lineage TEXT,
  catalog_version TEXT NOT NULL,
  mapping_version TEXT,
  quality TEXT NOT NULL DEFAULT 'accepted',
  superseded_by TEXT,
  captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_entity ON financial_observations(entity_id, metric, period_end);
CREATE TABLE IF NOT EXISTS latest_financials (
  entity_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  value REAL,
  period_end TEXT,
  period_type TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (entity_id, metric)
);

-- Durable workflow runs own execution state (ADR-0036)
CREATE TABLE IF NOT EXISTS workflow_runs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running','completed','failed','cancelled')),
  trigger TEXT NOT NULL,
  constitution_version_id TEXT,
  universe_version_id TEXT,
  server_session_id TEXT,
  stats TEXT,
  error TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_kind ON workflow_runs(kind, started_at);
CREATE TABLE IF NOT EXISTS workflow_steps (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES workflow_runs(id),
  name TEXT NOT NULL,
  item_ref TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending','running','completed','retrying','failed','skipped')),
  attempt INTEGER NOT NULL DEFAULT 1,
  detail TEXT,
  error TEXT,
  started_at TEXT,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_steps_run ON workflow_steps(run_id);

-- Shared completed-artifact identity (ADR-0020, ADR-0037)
CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN (
    'screener_snapshot','thesis','ic_verdict','investment_memo',
    'thesis_health_check','portfolio_review','learning_card')),
  entity_id TEXT,
  ticker TEXT,
  run_id TEXT,
  schema_version TEXT NOT NULL,
  payload TEXT NOT NULL,
  rendered_md TEXT,
  evidence_bundle_id TEXT,
  constitution_version_id TEXT,
  created_at TEXT NOT NULL,
  superseded_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_artifacts_ticker ON artifacts(ticker, kind, created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);

CREATE TABLE IF NOT EXISTS screener_results (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  entity_id TEXT,
  ticker TEXT NOT NULL,
  passed INTEGER NOT NULL,
  rank INTEGER,
  score REAL,
  ranking_components TEXT,
  pass_evidence TEXT,
  fail_reasons TEXT,
  selected INTEGER NOT NULL DEFAULT 0,
  selection_order INTEGER,
  snapshot_artifact_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_screener_results_run ON screener_results(run_id);

CREATE TABLE IF NOT EXISTS selection_events (
  id TEXT PRIMARY KEY,
  capability TEXT NOT NULL,
  run_id TEXT,
  ticker TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('promote','dismiss')),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workbench_state (
  server_session_id TEXT NOT NULL,
  capability TEXT NOT NULL,
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (server_session_id, capability)
);

CREATE TABLE IF NOT EXISTS ic_verdicts (
  id TEXT PRIMARY KEY,
  run_id TEXT,
  ticker TEXT NOT NULL,
  entity_id TEXT,
  thesis_artifact_id TEXT,
  verdict TEXT NOT NULL CHECK (verdict IN ('pass','fail')),
  conviction REAL,
  constitution_fit REAL,
  data_quality REAL,
  gate_score REAL,
  blend TEXT,
  cutoff REAL,
  components TEXT,
  hurdle_findings TEXT,
  rationale TEXT,
  is_override INTEGER NOT NULL DEFAULT 0,
  prior_verdict TEXT,
  constitution_version_id TEXT,
  artifact_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ic_verdicts_run ON ic_verdicts(run_id);

-- Memo-backed thesis health (ADR-0014)
CREATE TABLE IF NOT EXISTS thesis_health_plans (
  id TEXT PRIMARY KEY,
  memo_artifact_id TEXT NOT NULL,
  entity_id TEXT,
  ticker TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  raw_plan TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS thesis_watch_items (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL REFERENCES thesis_health_plans(id),
  item_type TEXT NOT NULL CHECK (item_type IN ('assumption','return_driver','risk','kill_criterion')),
  title TEXT NOT NULL,
  tracking_mode TEXT NOT NULL CHECK (tracking_mode IN ('quantitative','qualitative','unsupported')),
  metric TEXT,
  comparator TEXT,
  threshold REAL,
  cadence TEXT,
  lookback TEXT,
  confirmation_periods INTEGER NOT NULL DEFAULT 2,
  immediate_kill INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (status IN ('intact','watch','broken','unknown','data_gap')),
  current_value REAL,
  consecutive_breaches INTEGER NOT NULL DEFAULT 0,
  data_gap_count INTEGER NOT NULL DEFAULT 0,
  last_checked_at TEXT,
  why_matters TEXT
);
CREATE INDEX IF NOT EXISTS idx_watch_items_plan ON thesis_watch_items(plan_id);
CREATE TABLE IF NOT EXISTS thesis_health_checks (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES thesis_watch_items(id),
  refresh_id TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('baseline','refresh')),
  observed TEXT,
  status TEXT NOT NULL,
  data_gap INTEGER NOT NULL DEFAULT 0,
  checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS thesis_health_refreshes (
  id TEXT PRIMARY KEY,
  entity_id TEXT,
  ticker TEXT NOT NULL,
  trigger TEXT NOT NULL,
  metadata_only INTEGER NOT NULL DEFAULT 0,
  filing_check TEXT,
  ran_at TEXT NOT NULL
);

-- Portfolio is ledger-first (ADR-0035, ADR-0041)
CREATE TABLE IF NOT EXISTS portfolio_lots (
  id TEXT PRIMARY KEY,
  entity_id TEXT,
  ticker TEXT NOT NULL,
  shares REAL NOT NULL,
  cost_basis REAL NOT NULL,
  purchase_date TEXT NOT NULL,
  import_source TEXT NOT NULL DEFAULT 'manual',
  position_type TEXT,
  note TEXT,
  corrected_by TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS portfolio_sales (
  id TEXT PRIMARY KEY,
  entity_id TEXT,
  ticker TEXT NOT NULL,
  shares REAL NOT NULL,
  price REAL NOT NULL,
  sale_date TEXT NOT NULL,
  realized_pnl REAL,
  lot_matches TEXT,
  note TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_marks (
  ticker TEXT PRIMARY KEY,
  price REAL,
  as_of TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS holdings (
  ticker TEXT PRIMARY KEY,
  entity_id TEXT,
  shares REAL NOT NULL,
  avg_cost REAL,
  market_value REAL,
  unrealized_pnl REAL,
  weight REAL,
  position_type TEXT,
  coverage_state TEXT NOT NULL DEFAULT 'none',
  coverage_memo_artifact_id TEXT,
  updated_at TEXT NOT NULL
);

-- Dashboard items project from sources; responses retained
CREATE TABLE IF NOT EXISTS dashboard_items (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('decision','attention')),
  section TEXT NOT NULL CHECK (section IN ('needs_decision','portfolio_review','needs_attention')),
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_version TEXT NOT NULL,
  ticker TEXT,
  title TEXT NOT NULL,
  body TEXT,
  severity TEXT NOT NULL DEFAULT 'normal',
  rank_source TEXT,
  evidence_refs TEXT,
  response_set TEXT,
  status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open','resolved','dismissed','snoozed')),
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dashboard_status ON dashboard_items(status, section);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dashboard_source
  ON dashboard_items(source_type, source_id, source_version);
CREATE TABLE IF NOT EXISTS dashboard_responses (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES dashboard_items(id),
  response TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('hygiene','feedback','both')),
  payload TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approval_records (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  target_version TEXT,
  action TEXT NOT NULL CHECK (action IN ('accept','reject')),
  effect TEXT,
  created_at TEXT NOT NULL
);

-- Learning/Evals: append-only records with lineage
CREATE TABLE IF NOT EXISTS learning_records (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN (
    'outcome_evaluation','thesis_health_finding','pattern','recommendation',
    'response','recommendation_outcome','feedback_signal')),
  entity_id TEXT,
  ticker TEXT,
  window_months INTEGER,
  payload TEXT NOT NULL,
  confidence_label TEXT,
  lineage TEXT,
  superseded_by TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learning_kind ON learning_records(kind, created_at);
CREATE TABLE IF NOT EXISTS decision_register (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  rationale TEXT,
  alternatives TEXT,
  evidence_refs TEXT,
  links TEXT,
  created_at TEXT NOT NULL
);

-- Durable local work queue (ADR-0048)
CREATE TABLE IF NOT EXISTS work_queue (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 5,
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued','running','completed','failed','cancelled')),
  payload TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  run_after TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_work_queue_status ON work_queue(status, priority);

-- First-class execution provenance (ADR-0034)
CREATE TABLE IF NOT EXISTS execution_provenance (
  id TEXT PRIMARY KEY,
  run_id TEXT,
  step TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('model','tool','parser','validation','render')),
  model TEXT,
  prompt_version TEXT,
  inputs_ref TEXT,
  outputs_ref TEXT,
  validation TEXT,
  usage TEXT,
  rejected_output TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_usage (
  id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  capability TEXT NOT NULL,
  model TEXT NOT NULL,
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  est_cost REAL,
  run_id TEXT
);
"""

# Migration 2: bulk-first data layer (ADR-0059). Daily price history, the
# filings index that drives thesis-health checks, ownership evidence, and
# sync bookkeeping. Raw bulk dumps live in the cache directory, never here.
BULK_DATA_DDL = """
CREATE TABLE IF NOT EXISTS price_history (
  ticker TEXT NOT NULL,
  date TEXT NOT NULL,
  open REAL, high REAL, low REAL, close REAL,
  volume REAL,
  source TEXT NOT NULL DEFAULT 'yfinance',
  PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS filings (
  id TEXT PRIMARY KEY,
  cik TEXT,
  ticker TEXT,
  entity_id TEXT,
  form TEXT NOT NULL,
  filed_at TEXT NOT NULL,
  accession TEXT UNIQUE,
  title TEXT,
  source TEXT NOT NULL DEFAULT 'daily_index',
  processed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_filings_ticker ON filings(ticker, form, filed_at);
CREATE INDEX IF NOT EXISTS idx_filings_unprocessed ON filings(processed, filed_at);
CREATE TABLE IF NOT EXISTS ownership_records (
  id TEXT PRIMARY KEY,
  entity_id TEXT,
  ticker TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('insider_transaction','institutional_holding','beneficial_ownership')),
  as_of TEXT NOT NULL,
  owner_name TEXT NOT NULL,
  owner_role TEXT,
  shares REAL,
  value REAL,
  txn_type TEXT,
  payload TEXT,
  source_id TEXT,
  captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ownership_ticker ON ownership_records(ticker, kind, as_of);
CREATE TABLE IF NOT EXISTS sync_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TEXT NOT NULL
);
"""

# One-time rebuild of the latest-financials projection: period-scaled metrics
# (flows / flow-over-stock returns) prefer their newest annual/TTM observation
# over a newer quarterly one, matching FinancialStore.refresh_latest. Existing
# workspaces had quarterly EPS/revenue/FCF as headline values, which valuation
# anchors multiplied against annual-basis arithmetic. The metric list is a
# frozen snapshot of PERIOD_SCALED_METRICS at migration time (forward-only).
LATEST_PROJECTION_REBUILD_DML = """
DELETE FROM latest_financials;
INSERT INTO latest_financials (entity_id, metric, value, period_end, period_type, updated_at)
SELECT entity_id, metric, value, period_end, period_type,
       strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')
FROM (
  SELECT entity_id, metric, value, period_end, period_type,
         ROW_NUMBER() OVER (
           PARTITION BY entity_id, metric
           ORDER BY
             CASE WHEN period_type != 'quarterly' OR metric NOT IN (
               'revenue','cost_of_revenue','gross_profit','operating_income',
               'pretax_income','income_tax','net_income','ebitda','eps',
               'operating_cash_flow','capex','free_cash_flow','owner_earnings',
               'maintenance_capex','growth_capex','sbc','roe','roa','roic'
             ) THEN 1 ELSE 0 END DESC,
             period_end DESC,
             CASE WHEN period_type != 'quarterly' THEN 1 ELSE 0 END DESC
         ) AS rn
  FROM financial_observations
  WHERE superseded_by IS NULL AND quality = 'accepted'
)
WHERE rn = 1;
"""

# Market-context layer: company events (earnings/dividends), watchlists and
# research themes, macro series cache, filing-section cache for the research
# harness — plus new artifact kinds (filing_note, industry_note), which in
# SQLite means rebuilding the artifacts table to widen its CHECK constraint
# (no FK references artifacts, so a copy-rename is safe).
MARKET_CONTEXT_DDL = """
CREATE TABLE IF NOT EXISTS company_events (
  id TEXT PRIMARY KEY,
  ticker TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('earnings','dividend','split')),
  event_date TEXT NOT NULL,
  label TEXT,
  payload TEXT,
  source TEXT NOT NULL DEFAULT 'yfinance',
  captured_at TEXT NOT NULL,
  UNIQUE (ticker, kind, event_date)
);
CREATE INDEX IF NOT EXISTS idx_company_events_date ON company_events(event_date, kind);
CREATE INDEX IF NOT EXISTS idx_company_events_ticker ON company_events(ticker, event_date);

CREATE TABLE IF NOT EXISTS watchlists (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'watchlist' CHECK (kind IN ('watchlist','theme')),
  note TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watchlist_tickers (
  watchlist_id TEXT NOT NULL REFERENCES watchlists(id),
  ticker TEXT NOT NULL,
  added_at TEXT NOT NULL,
  PRIMARY KEY (watchlist_id, ticker)
);

CREATE TABLE IF NOT EXISTS macro_series (
  series TEXT NOT NULL,
  date TEXT NOT NULL,
  value REAL,
  PRIMARY KEY (series, date)
);

CREATE TABLE IF NOT EXISTS filing_sections (
  id TEXT PRIMARY KEY,
  ticker TEXT,
  accession TEXT NOT NULL,
  form TEXT,
  filed_at TEXT,
  section TEXT NOT NULL,
  content TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  UNIQUE (accession, section)
);
CREATE INDEX IF NOT EXISTS idx_filing_sections_ticker
  ON filing_sections(ticker, section, filed_at);

CREATE TABLE artifacts_v4 (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN (
    'screener_snapshot','thesis','ic_verdict','investment_memo',
    'thesis_health_check','portfolio_review','learning_card',
    'filing_note','industry_note')),
  entity_id TEXT,
  ticker TEXT,
  run_id TEXT,
  schema_version TEXT NOT NULL,
  payload TEXT NOT NULL,
  rendered_md TEXT,
  evidence_bundle_id TEXT,
  constitution_version_id TEXT,
  created_at TEXT NOT NULL,
  superseded_by TEXT
);
INSERT INTO artifacts_v4 SELECT * FROM artifacts;
DROP TABLE artifacts;
ALTER TABLE artifacts_v4 RENAME TO artifacts;
CREATE INDEX IF NOT EXISTS idx_artifacts_ticker ON artifacts(ticker, kind, created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);
"""

# Peer grouping widens by SIC code tiers (exact industry → 3-digit → 2-digit
# group) before falling back to the broad sector division, so the code itself
# is identity data (zero-padded to 4 digits).
ENTITY_SIC_DDL = """
ALTER TABLE investment_entities ADD COLUMN sic TEXT;
"""

MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "baseline", BASELINE_DDL),
    (2, "bulk_data_layer", BULK_DATA_DDL),
    (3, "latest_projection_full_period_flows", LATEST_PROJECTION_REBUILD_DML),
    (4, "market_context_layer", MARKET_CONTEXT_DDL),
    (5, "entity_sic_code", ENTITY_SIC_DDL),
]


class Workspace:
    """Owns the SQLite connection and migration state for one local workspace."""

    def __init__(self, db_path: str | os.PathLike | None = None):
        env_path = os.environ.get("FUNDOPS_DB")
        path = Path(db_path or env_path or DEFAULT_DB_PATH)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(path)
        self._local = threading.local()
        self.server_session_id = new_id("sess")
        self.migrate()

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")
            self._local.conn = conn
        return conn

    def migrate(self) -> None:
        conn = self.conn
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        if 4 not in applied:
            self._repair_partial_artifacts_rebuild(conn)
        for version, name, ddl in MIGRATIONS:
            if version in applied:
                continue
            # executescript() autocommits per statement, so an explicit BEGIN
            # (without COMMIT) in the script is what makes the whole migration
            # — DDL plus its schema_migrations row — one atomic unit. A crash
            # mid-migration rolls back cleanly instead of wedging the workspace.
            try:
                conn.executescript("BEGIN;\n" + ddl)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?,?,?)",
                    (version, name, now_iso()),
                )
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO workspace_meta (key, value) VALUES ('workspace_id', ?)",
                (new_id("ws"),),
            )
            conn.execute(
                "INSERT OR REPLACE INTO workspace_meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def _repair_partial_artifacts_rebuild(conn: sqlite3.Connection) -> None:
        """Finish or undo migration 4's artifacts copy-rename if a pre-atomic
        build was killed partway through, leaving artifacts_v4 behind."""
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "artifacts_v4" not in tables:
            return
        with conn:
            if "artifacts" in tables:
                # Copy was interrupted; the original table is still authoritative.
                conn.execute("DROP TABLE artifacts_v4")
            else:
                # Copy and drop completed; only the rename was lost.
                conn.execute("ALTER TABLE artifacts_v4 RENAME TO artifacts")

    # Convenience helpers used by stores only.
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, tuple(params))

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, tuple(params)).fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, tuple(params)).fetchone()

    def transaction(self):
        return self.conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


_workspace: Workspace | None = None
_workspace_lock = threading.Lock()


def get_workspace() -> Workspace:
    global _workspace
    if _workspace is None:
        with _workspace_lock:
            if _workspace is None:
                _workspace = Workspace()
    return _workspace


def set_workspace(ws: Workspace | None) -> None:
    """Test/bootstrap hook to swap the process workspace."""
    global _workspace
    _workspace = ws
