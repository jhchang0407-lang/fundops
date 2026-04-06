"""Evidence artifacts and prompt versioning.

Captures immutable data snapshots tied to judgment events, enabling:
- Point-in-time data lineage: "what exact data drove this thesis?"
- Prompt versioning: "what prompt produced this output?"
- Reproducibility: hash-based deduplication of identical snapshots

Usage:
    evidence = EvidenceCapture(conn)
    artifact_id = evidence.capture(
        ticker="AAPL", artifact_type="sec_filing",
        source="sec_edgar", source_id="0000320193-24-000001",
        data={"revenue": 394328000000, ...}
    )
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("fundops.evidence")


class EvidenceCapture:
    """Captures and retrieves evidence artifacts tied to judgment events."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def capture(
        self,
        ticker: str,
        artifact_type: str,
        source: str,
        data: dict,
        source_id: str = "",
        judgment_event_id: int | None = None,
    ) -> int:
        """Capture an evidence artifact.

        Args:
            ticker: Stock ticker.
            artifact_type: "sec_filing", "price_quote", "web_research", "scoring_data"
            source: Data provider name ("sec_edgar", "fmp", "yfinance", "openai")
            data: The actual data snapshot (dict, will be JSON-serialized)
            source_id: Provider-specific ID (filing accession, quote timestamp)
            judgment_event_id: Optional FK to judgment_events table

        Returns:
            The inserted artifact ID.
        """
        data_json = json.dumps(data, default=str, sort_keys=True)
        data_hash = hashlib.sha256(data_json.encode()).hexdigest()[:16]

        cursor = self.conn.execute(
            """INSERT INTO evidence_artifacts
               (judgment_event_id, artifact_type, ticker, source, source_id,
                data_hash, data, captured_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                judgment_event_id,
                artifact_type,
                ticker,
                source,
                source_id,
                data_hash,
                data_json,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        artifact_id = cursor.lastrowid
        log.info(
            f"Captured {artifact_type} artifact for {ticker} "
            f"(hash={data_hash}, id={artifact_id})"
        )
        return artifact_id

    def get_artifacts(
        self,
        judgment_event_id: int | None = None,
        ticker: str | None = None,
    ) -> list[dict]:
        """Retrieve evidence artifacts by judgment event or ticker."""
        if judgment_event_id:
            rows = self.conn.execute(
                "SELECT * FROM evidence_artifacts WHERE judgment_event_id = ? ORDER BY captured_at",
                (judgment_event_id,),
            ).fetchall()
        elif ticker:
            rows = self.conn.execute(
                "SELECT * FROM evidence_artifacts WHERE ticker = ? ORDER BY captured_at DESC LIMIT 50",
                (ticker,),
            ).fetchall()
        else:
            return []

        cols = [d[0] for d in self.conn.execute(
            "SELECT * FROM evidence_artifacts LIMIT 0"
        ).description]
        return [dict(zip(cols, row)) for row in rows]


def version_prompt(
    conn: sqlite3.Connection,
    agent: str,
    prompt_text: str,
) -> str:
    """Version a prompt template by hashing its content.

    Inserts into prompt_versions if new (deduplicates by hash).
    Returns the prompt hash (first 16 chars of SHA256).
    """
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:16]

    try:
        conn.execute(
            """INSERT OR IGNORE INTO prompt_versions
               (agent, prompt_hash, prompt_template, created_at)
               VALUES (?, ?, ?, ?)""",
            (agent, prompt_hash, prompt_text, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except Exception as e:
        log.debug(f"Prompt versioning failed (non-critical): {e}")

    return prompt_hash
