"""Forward-only SQLite migration runner.

Each migration is a (version, name, sql) tuple. The runner creates a
schema_migrations table to track applied versions and applies new ones in order.

Existing v1/v2 schemas use CREATE IF NOT EXISTS, so migrations 1 and 2 are
safe no-ops on existing databases. Future changes (new columns, tables, indexes)
are added as migrations 3, 4, etc.

Usage:
    run_migrations(conn)  # call in DB __init__
"""

import logging
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger("fundops.migrations")

# Each migration: (version, name, sql)
# SQL can contain multiple statements separated by ;
MIGRATIONS: list[tuple[int, str, str]] = [
    # Migration 1: Core audit trail tables (v1 schema)
    # These use IF NOT EXISTS so they're safe on existing databases.
    (1, "v1_core_tables", """
        CREATE TABLE IF NOT EXISTS tickers (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            sector TEXT,
            industry TEXT,
            first_seen_at TEXT,
            current_lifecycle TEXT,
            is_owned INTEGER DEFAULT 0,
            metadata JSON
        );
        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            agent TEXT NOT NULL,
            run_at TEXT NOT NULL,
            run_type TEXT,
            scores JSON,
            fair_value REAL,
            price_at_run REAL,
            verdict TEXT,
            summary TEXT,
            full_output JSON,
            output_path TEXT,
            FOREIGN KEY (ticker) REFERENCES tickers(ticker)
        );
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            total_value REAL,
            cash REAL,
            holdings JSON,
            alerts JSON,
            daily_pnl REAL,
            UNIQUE(snapshot_date)
        );
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            added_at TEXT NOT NULL,
            added_reason TEXT,
            entry_price REAL,
            target_price REAL,
            status TEXT DEFAULT 'active',
            removed_at TEXT,
            notes TEXT,
            FOREIGN KEY (ticker) REFERENCES tickers(ticker)
        );
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            action TEXT NOT NULL,
            acted_at TEXT NOT NULL,
            reason TEXT,
            context JSON,
            FOREIGN KEY (ticker) REFERENCES tickers(ticker)
        );
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            title TEXT,
            content TEXT,
            metadata JSON,
            FOREIGN KEY (ticker) REFERENCES tickers(ticker)
        );
        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            shares REAL,
            price REAL,
            date TEXT NOT NULL,
            source_agent TEXT,
            scout_lens TEXT,
            val_expected_return REAL,
            judge_verdict TEXT,
            notes TEXT,
            FOREIGN KEY (ticker) REFERENCES tickers(ticker)
        );
        CREATE INDEX IF NOT EXISTS idx_agent_runs_ticker ON agent_runs(ticker, agent, run_at);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent, run_at);
        CREATE INDEX IF NOT EXISTS idx_portfolio_date ON portfolio_snapshots(snapshot_date);
        CREATE INDEX IF NOT EXISTS idx_watchlist_status ON watchlist(status, ticker);
        CREATE INDEX IF NOT EXISTS idx_documents_ticker ON documents(ticker, doc_type);
        CREATE INDEX IF NOT EXISTS idx_outcomes_ticker ON outcomes(ticker, date);
    """),

    # Migration 2: Constitution, judgment events, strategy, learning (v2 schema)
    # Also uses IF NOT EXISTS for safety on existing databases.
    (2, "v2_constitution_and_learning", """
        CREATE TABLE IF NOT EXISTS constitution (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            north_star TEXT,
            north_star_summary TEXT,
            style_identity TEXT,
            time_horizon TEXT,
            must_have_signals JSON,
            anti_signals JSON,
            ic_hurdles JSON,
            disqualifiers JSON,
            position_sizing JSON,
            concentration_rules JSON,
            sell_discipline JSON,
            dimensions JSON,
            sector_routing JSON,
            agent_profiles JSON,
            universe_type TEXT DEFAULT 'preset',
            universe_name TEXT,
            universe_custom JSON,
            autonomy_mode TEXT DEFAULT 'suggest',
            active_version_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS constitution_changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            constitution_id TEXT NOT NULL,
            version_from INTEGER,
            version_to INTEGER NOT NULL,
            change_type TEXT,
            change_summary TEXT,
            changed_fields JSON,
            trigger TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (constitution_id) REFERENCES constitution(id)
        );
        CREATE TABLE IF NOT EXISTS judgment_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            ticker TEXT,
            constitution_version INTEGER,
            agent TEXT,
            data JSON,
            rationale TEXT,
            parent_event_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (parent_event_id) REFERENCES judgment_events(id)
        );
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            constitution_id TEXT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            extracted JSON,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS library_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            constitution_version INTEGER,
            verdict TEXT,
            conviction INTEGER,
            expected_return REAL,
            discount_pct REAL,
            sector TEXT,
            industry TEXT,
            gross_margin REAL,
            roic REAL,
            revenue_growth REAL,
            debt_equity REAL,
            key_assumptions JSON,
            judgment_event_id INTEGER,
            data JSON,
            created_at TEXT NOT NULL,
            FOREIGN KEY (judgment_event_id) REFERENCES judgment_events(id)
        );
        CREATE TABLE IF NOT EXISTS refinement_proposals (
            proposal_id TEXT PRIMARY KEY,
            constitution_id TEXT NOT NULL,
            pattern_type TEXT,
            pattern_tag TEXT,
            pattern_count INTEGER,
            pattern_tickers JSON,
            proposal TEXT,
            analysis TEXT,
            code_change TEXT,
            confidence REAL,
            risk TEXT,
            evidence_summary TEXT,
            status TEXT DEFAULT 'pending',
            user_response TEXT,
            applied_version_id INTEGER,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (constitution_id) REFERENCES constitution(id)
        );
        CREATE TABLE IF NOT EXISTS strategy_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            autonomy_mode TEXT DEFAULT 'suggest',
            north_star TEXT,
            dimensions JSON,
            sector_routing JSON,
            universe_type TEXT DEFAULT 'preset',
            universe_name TEXT,
            universe_custom JSON,
            active_version_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS strategy_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            scoring_code TEXT,
            label_map JSON,
            explanation TEXT,
            change_reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (strategy_id) REFERENCES strategy_profiles(id)
        );
        CREATE TABLE IF NOT EXISTS screener_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_version_id INTEGER,
            run_at TEXT NOT NULL,
            universe_size INTEGER,
            scored_count INTEGER,
            failed_count INTEGER,
            top_results JSON,
            all_results JSON,
            duration_s REAL,
            status TEXT,
            error_message TEXT,
            FOREIGN KEY (strategy_version_id) REFERENCES strategy_versions(id)
        );
        CREATE TABLE IF NOT EXISTS feedback_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            screener_run_id INTEGER,
            ticker TEXT NOT NULL,
            feedback TEXT NOT NULL,
            dismiss_reason TEXT,
            note TEXT,
            score_at_feedback REAL,
            rank_at_feedback INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS outcome_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            screener_run_id INTEGER,
            ticker TEXT NOT NULL,
            screened_at TEXT,
            check_at TEXT,
            days_elapsed INTEGER,
            price_at_screen REAL,
            price_at_check REAL,
            return_pct REAL,
            benchmark_return_pct REAL,
            alpha_pct REAL,
            thesis_integrity JSON,
            goal_alignment JSON,
            status TEXT,
            error_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_je_ticker ON judgment_events(ticker);
        CREATE INDEX IF NOT EXISTS idx_je_type ON judgment_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_je_parent ON judgment_events(parent_event_id);
        CREATE INDEX IF NOT EXISTS idx_je_const ON judgment_events(constitution_version);
        CREATE INDEX IF NOT EXISTS idx_lib_ticker ON library_entries(ticker);
        CREATE INDEX IF NOT EXISTS idx_lib_sector ON library_entries(sector);
        CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_history(constitution_id, session_id);
        CREATE INDEX IF NOT EXISTS idx_sr_version ON screener_runs(strategy_version_id);
        CREATE INDEX IF NOT EXISTS idx_fb_run ON feedback_records(screener_run_id);
        CREATE INDEX IF NOT EXISTS idx_os_run ON outcome_snapshots(screener_run_id);
        CREATE INDEX IF NOT EXISTS idx_os_ticker ON outcome_snapshots(ticker);
    """),

    # Migration 3: Workflow events for durable orchestration (Phase 2)
    # Added as part of the Investment OS upgrade plan.
    (3, "workflow_events_table", """
        CREATE TABLE IF NOT EXISTS workflow_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT,
            source TEXT NOT NULL,
            event TEXT NOT NULL,
            ticker TEXT,
            data JSON,
            status TEXT NOT NULL DEFAULT 'pending',
            idempotency_key TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS idx_we_run ON workflow_events(run_id);
        CREATE INDEX IF NOT EXISTS idx_we_status ON workflow_events(status);
    """),

    # Migration 4: Evidence artifacts for data lineage (Phase 2)
    (4, "evidence_artifacts_table", """
        CREATE TABLE IF NOT EXISTS evidence_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            judgment_event_id INTEGER,
            artifact_type TEXT NOT NULL,
            ticker TEXT,
            source TEXT,
            source_id TEXT,
            data_hash TEXT,
            data JSON,
            captured_at TEXT NOT NULL,
            FOREIGN KEY (judgment_event_id) REFERENCES judgment_events(id)
        );
        CREATE INDEX IF NOT EXISTS idx_ea_event ON evidence_artifacts(judgment_event_id);
        CREATE INDEX IF NOT EXISTS idx_ea_ticker ON evidence_artifacts(ticker);
    """),

    # Migration 5: Prompt versioning (Phase 2)
    (5, "prompt_versions_table", """
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            prompt_template TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(agent, prompt_hash)
        );
    """),

    # Migration 6: Pending approvals for pipeline gates (Phase 5)
    (6, "pending_approvals_table", """
        CREATE TABLE IF NOT EXISTS pending_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            ticker TEXT NOT NULL,
            agent_completed TEXT NOT NULL,
            next_agent TEXT NOT NULL,
            decision_data JSON,
            status TEXT NOT NULL DEFAULT 'pending',
            decided_by TEXT,
            decided_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pa_status ON pending_approvals(status);
        CREATE INDEX IF NOT EXISTS idx_pa_ticker ON pending_approvals(ticker);
    """),
]


def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply any pending migrations to the database.

    Creates the schema_migrations tracking table if needed, then applies
    all migrations with version > max applied version.

    Returns the number of migrations applied.
    """
    # Create tracking table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
    """)
    conn.commit()

    # Get max applied version
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    current_version = row[0] if row[0] is not None else 0

    applied = 0
    for version, name, sql in MIGRATIONS:
        if version <= current_version:
            continue
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (version, name, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            applied += 1
            log.info(f"Applied migration {version}: {name}")
        except Exception as e:
            log.error(f"Migration {version} ({name}) failed: {e}")
            raise

    if applied:
        log.info(f"Applied {applied} migration(s). Schema now at version {version}.")

    return applied
