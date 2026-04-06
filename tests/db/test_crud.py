"""Test database CRUD operations for both v1 and v2 schemas."""

import json
import pytest
from datetime import datetime, timezone


class TestTickerCRUD:

    def test_upsert_ticker_create(self, db):
        db.upsert_ticker("AAPL", company_name="Apple Inc.", sector="Technology")
        row = db.conn.execute("SELECT * FROM tickers WHERE ticker = ?", ("AAPL",)).fetchone()
        assert row is not None
        assert row[1] == "Apple Inc."
        assert row[2] == "Technology"

    def test_upsert_ticker_update(self, db):
        db.upsert_ticker("AAPL", company_name="Apple", sector="Tech")
        db.upsert_ticker("AAPL", sector="Technology")
        row = db.conn.execute("SELECT company_name, sector FROM tickers WHERE ticker = ?", ("AAPL",)).fetchone()
        assert row[0] == "Apple"  # unchanged
        assert row[1] == "Technology"  # updated

    def test_upsert_ticker_with_metadata(self, db):
        db.upsert_ticker("AAPL", metadata={"exchange": "NASDAQ"})
        row = db.conn.execute("SELECT metadata FROM tickers WHERE ticker = ?", ("AAPL",)).fetchone()
        meta = json.loads(row[0])
        assert meta["exchange"] == "NASDAQ"


class TestAgentRunCRUD:

    def test_record_run(self, db):
        db.upsert_ticker("AAPL")
        db.record_run("screener", "AAPL", verdict="handoff", summary="Good candidate",
                       scores={"quality": 90}, full_output={"score": 85})
        rows = db.conn.execute("SELECT * FROM agent_runs WHERE ticker = ?", ("AAPL",)).fetchall()
        assert len(rows) == 1
        assert rows[0][3]  # run_at is not empty

    def test_record_run_with_fair_value(self, db):
        db.upsert_ticker("AAPL")
        db.record_run("thesis", "AAPL", fair_value=220.0, price_at_run=175.0,
                       verdict="bullish", summary="Undervalued")
        row = db.conn.execute(
            "SELECT fair_value, price_at_run, verdict FROM agent_runs WHERE ticker = ?",
            ("AAPL",)
        ).fetchone()
        assert row[0] == 220.0
        assert row[1] == 175.0
        assert row[2] == "bullish"

    def test_multiple_runs_same_ticker(self, db):
        db.upsert_ticker("AAPL")
        db.record_run("screener", "AAPL", verdict="handoff")
        db.record_run("thesis", "AAPL", verdict="bullish")
        db.record_run("ic_review", "AAPL", verdict="PASS")
        rows = db.conn.execute("SELECT agent FROM agent_runs WHERE ticker = ? ORDER BY id", ("AAPL",)).fetchall()
        assert [r[0] for r in rows] == ["screener", "thesis", "ic_review"]


class TestConstitutionCRUD:

    def test_create_constitution(self, v2db, sample_constitution):
        c = sample_constitution
        v2db.conn.execute("""
            INSERT INTO constitution (id, name, version, north_star, dimensions, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (c["id"], c["name"], c["version"], c["north_star"],
              json.dumps(c["dimensions"]), c["created_at"], c["updated_at"]))
        v2db.conn.commit()
        row = v2db.conn.execute("SELECT * FROM constitution WHERE id = ?", (c["id"],)).fetchone()
        assert row is not None

    def test_constitution_version_increment(self, v2db, sample_constitution):
        c = sample_constitution
        v2db.conn.execute("""
            INSERT INTO constitution (id, name, version, north_star, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (c["id"], c["name"], 1, c["north_star"], c["created_at"], c["updated_at"]))
        v2db.conn.commit()

        # Update version
        v2db.conn.execute(
            "UPDATE constitution SET version = version + 1 WHERE id = ?", (c["id"],)
        )
        v2db.conn.commit()
        row = v2db.conn.execute("SELECT version FROM constitution WHERE id = ?", (c["id"],)).fetchone()
        assert row[0] == 2


class TestJudgmentEventCRUD:

    def test_insert_event(self, v2db):
        now = datetime.now(timezone.utc).isoformat()
        v2db.conn.execute("""
            INSERT INTO judgment_events (event_type, ticker, agent, data, rationale, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("ic_passed", "AAPL", "ic_review",
              json.dumps({"verdict": "PASS", "conviction": 4}),
              "Strong business with margin of safety", now))
        v2db.conn.commit()
        row = v2db.conn.execute("SELECT * FROM judgment_events WHERE ticker = ?", ("AAPL",)).fetchone()
        assert row is not None
        assert row[1] == "ic_passed"

    def test_parent_child_linking(self, v2db):
        now = datetime.now(timezone.utc).isoformat()
        # Parent event
        v2db.conn.execute("""
            INSERT INTO judgment_events (event_type, ticker, agent, data, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ("thesis_generated", "AAPL", "thesis",
              json.dumps({"fair_value": 220}), now))
        parent_id = v2db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Child event
        v2db.conn.execute("""
            INSERT INTO judgment_events (event_type, ticker, agent, data, parent_event_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("ic_passed", "AAPL", "ic_review",
              json.dumps({"verdict": "PASS"}), parent_id, now))
        child_id = v2db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Verify chain
        child = v2db.conn.execute(
            "SELECT parent_event_id FROM judgment_events WHERE id = ?", (child_id,)
        ).fetchone()
        assert child[0] == parent_id


class TestLibraryEntryCRUD:

    def test_insert_library_entry(self, v2db):
        now = datetime.now(timezone.utc).isoformat()
        v2db.conn.execute("""
            INSERT INTO library_entries (ticker, entry_type, verdict, conviction,
                expected_return, sector, gross_margin, roic, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("AAPL", "thesis", "PASS", 4, 25.7, "Technology", 0.43, 0.28, now))
        v2db.conn.commit()
        rows = v2db.conn.execute("SELECT * FROM library_entries WHERE ticker = ?", ("AAPL",)).fetchall()
        assert len(rows) == 1

    def test_similarity_query_by_sector(self, v2db):
        now = datetime.now(timezone.utc).isoformat()
        for ticker, gm, roic in [("AAPL", 0.43, 0.28), ("MSFT", 0.69, 0.35), ("GOOGL", 0.48, 0.26)]:
            v2db.conn.execute("""
                INSERT INTO library_entries (ticker, entry_type, verdict, sector,
                    gross_margin, roic, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ticker, "thesis", "PASS", "Technology", gm, roic, now))
        v2db.conn.commit()

        # Find similar to AAPL (sector=Technology, GM within ±10pp, ROIC within ±5pp)
        rows = v2db.conn.execute("""
            SELECT ticker FROM library_entries
            WHERE sector = 'Technology'
              AND ABS(gross_margin - 0.43) <= 0.10
              AND ABS(roic - 0.28) <= 0.05
              AND ticker != 'AAPL'
        """).fetchall()
        similar = [r[0] for r in rows]
        assert "GOOGL" in similar  # GM 0.48 within 0.10 of 0.43, ROIC 0.26 within 0.05 of 0.28
