"""Library Agent — Research archive with similarity retrieval.

Ingests thesis, IC verdict, and memo outputs into a unified library.
Provides similarity search for other agents ("this resembles three
names you approved before, and here's how those played out").

The Library is a memory engine, not a filing cabinet.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from backend.agents import AgentPlugin, AgentResult

log = logging.getLogger("fundops.library")


class LibraryAgent(AgentPlugin):
    """Research archive with similarity retrieval."""

    name = "library"
    description = "Store and retrieve research with pattern matching"

    def __init__(self, config: dict = None, db=None, v2db=None):
        super().__init__(config)
        self.db = db
        self._v2db = v2db

    def _get_v2db(self):
        if self._v2db:
            return self._v2db
        from backend.core.db_v2 import ScreenerV2DB
        db_path = self.db.db_path if self.db else None
        return ScreenerV2DB(db_path=db_path)

    async def run(self, context: dict) -> AgentResult:
        """Ingest research artifacts into the library.

        Can be triggered by:
        - Thesis completion (auto-ingest thesis)
        - IC verdict (auto-ingest verdict)
        - Memo completion (auto-ingest memo)
        - Manual scan of output directories
        """
        t0 = time.time()
        v2db = self._get_v2db()
        ingested = 0
        errors = []
        constitution = context.get("constitution")

        # Mode 1: Ingest a specific artifact from context
        ticker = context.get("ticker", "")
        artifact_type = context.get("artifact_type", "")

        if ticker and artifact_type:
            try:
                ingested += self._ingest_artifact(v2db, ticker, artifact_type, context, constitution)
            except Exception as e:
                errors.append(f"{ticker}/{artifact_type}: {e}")
                log.warning(f"Library ingest failed for {ticker}/{artifact_type}: {e}")

        # Mode 2: Ingest from judgment events not yet in library
        if not ticker:
            try:
                ingested += self._ingest_from_events(v2db, constitution)
            except Exception as e:
                errors.append(f"Event ingest: {e}")
            try:
                ingested += self._ingest_from_agent_runs(v2db, constitution)
            except Exception as e:
                errors.append(f"Agent run ingest: {e}")

        # Mode 3: Scan output directories (legacy compat)
        config = self.config or {}
        memo_sources = config.get("memo_sources", [])
        for source_dir in memo_sources:
            try:
                ingested += self._scan_directory(v2db, source_dir, constitution)
            except Exception as e:
                errors.append(f"{source_dir}: {e}")

        if not self._v2db:
            v2db.close()

        log.info(f"Library: ingested {ingested} entries")

        return AgentResult(
            agent=self.name,
            status="complete",
            event_type="complete",
            data={
                "ingested": ingested,
                "errors": errors,
                "library_stats": v2db.get_library_stats() if self._v2db else {},
            },
            errors=errors,
            duration_s=time.time() - t0,
        )

    def _ingest_artifact(self, v2db, ticker: str, artifact_type: str,
                          context: dict, constitution: dict | None) -> int:
        """Ingest a single artifact (thesis, ic_verdict, memo) into library."""
        data = context.get("data", {})

        if artifact_type == "thesis":
            quality = data.get("quality", {})
            v2db.store_library_entry(
                ticker=ticker,
                entry_type="thesis",
                constitution_version=constitution.get("version") if constitution else None,
                expected_return=data.get("expected_return"),
                discount_pct=data.get("discount_pct"),
                sector=data.get("sector"),
                industry=data.get("industry"),
                gross_margin=quality.get("gross_margin"),
                roic=quality.get("roic"),
                revenue_growth=data.get("valuation", {}).get("growth_rate"),
                debt_equity=quality.get("debt_equity"),
                conviction={"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(data.get("conviction"), 0),
                data=data,
                judgment_event_id=context.get("judgment_event_id"),
            )
            return 1

        elif artifact_type == "ic_verdict":
            v2db.store_library_entry(
                ticker=ticker,
                entry_type="ic_verdict",
                constitution_version=constitution.get("version") if constitution else None,
                verdict=data.get("verdict"),
                conviction=data.get("conviction"),
                expected_return=data.get("base_return"),
                discount_pct=data.get("discount_pct"),
                sector=context.get("sector"),
                key_assumptions=data.get("key_assumptions"),
                data=data,
                judgment_event_id=context.get("judgment_event_id"),
            )
            return 1

        elif artifact_type == "memo":
            v2db.store_library_entry(
                ticker=ticker,
                entry_type="memo",
                constitution_version=constitution.get("version") if constitution else None,
                sector=data.get("sector"),
                data={"summary": data.get("summary", ""), "word_count": data.get("word_count", 0)},
                judgment_event_id=context.get("judgment_event_id"),
            )
            return 1

        return 0

    def _ingest_from_events(self, v2db, constitution: dict | None) -> int:
        """Ingest from recent judgment events not yet in library."""
        ingested = 0
        events = v2db.get_recent_events(limit=50)

        for event in events:
            if event["event_type"] not in ("thesis_generated", "ic_passed", "ic_failed"):
                continue

            # Check if already in library
            existing = v2db.get_library_by_ticker(event.get("ticker", ""))
            already_ingested = any(
                e.get("judgment_event_id") == event["id"] for e in existing
            )
            if already_ingested:
                continue

            data = event.get("data", {})
            entry_type = "thesis" if event["event_type"] == "thesis_generated" else "ic_verdict"

            v2db.store_library_entry(
                ticker=event.get("ticker", ""),
                entry_type=entry_type,
                constitution_version=event.get("constitution_version"),
                verdict=data.get("verdict"),
                conviction=data.get("conviction"),
                expected_return=data.get("expected_return") or data.get("base_return"),
                discount_pct=data.get("discount_pct"),
                key_assumptions=data.get("key_assumptions"),
                judgment_event_id=event["id"],
                data=data,
            )
            ingested += 1

        return ingested

    def _ingest_from_agent_runs(self, v2db, constitution: dict | None) -> int:
        """Ingest from recent agent_runs (thesis, IC review) not yet in library."""
        import json as _json
        if not self.db:
            return 0

        ingested = 0
        # Scan recent thesis and IC review runs
        for agent_type, entry_type in [("thesis", "thesis"), ("ic_review", "ic_verdict")]:
            runs = self.db.get_latest_runs(agent_type, limit=50)
            for run in runs:
                ticker = run.get("ticker", "")
                if not ticker or ticker in ("PIPELINE", "BATCH"):
                    continue

                # Check if already in library (by ticker + entry_type + run_at)
                existing = v2db.get_library_by_ticker(ticker)
                run_at = run.get("run_at", "")
                already_exists = any(
                    e.get("entry_type") == entry_type and
                    e.get("created_at", "")[:16] == run_at[:16]  # match to the minute
                    for e in existing
                )
                if already_exists:
                    continue

                # Parse full_output
                raw = run.get("full_output") or "{}"
                if isinstance(raw, str):
                    try:
                        raw = _json.loads(raw)
                    except Exception:
                        raw = {}
                if not raw:
                    continue

                quality = raw.get("quality", {}) if isinstance(raw, dict) else {}

                try:
                    v2db.store_library_entry(
                        ticker=ticker,
                        entry_type=entry_type,
                        constitution_version=constitution.get("version") if constitution else None,
                        verdict=raw.get("verdict") or run.get("verdict"),
                        conviction=raw.get("conviction"),
                        expected_return=raw.get("expected_return") or raw.get("base_return"),
                        discount_pct=raw.get("discount_pct"),
                        sector=raw.get("sector"),
                        industry=raw.get("industry"),
                        gross_margin=quality.get("gross_margin"),
                        roic=quality.get("roic"),
                        debt_equity=quality.get("debt_equity"),
                        key_assumptions=raw.get("key_assumptions"),
                        data=raw,
                    )
                    ingested += 1
                except Exception as e:
                    log.debug(f"Library ingest failed for {ticker}/{entry_type}: {e}")

        return ingested

    def _scan_directory(self, v2db, source_dir: str, constitution: dict | None) -> int:
        """Legacy: scan directory for JSON memo files."""
        source_path = Path(os.path.expandvars(source_dir))
        if not source_path.exists():
            return 0

        ingested = 0
        for memo_file in source_path.glob("*.json"):
            try:
                with open(memo_file) as f:
                    memo = json.load(f)
                ticker = memo.get("ticker", "")
                if not ticker:
                    continue

                v2db.store_library_entry(
                    ticker=ticker,
                    entry_type="memo_file",
                    constitution_version=constitution.get("version") if constitution else None,
                    sector=memo.get("sector"),
                    expected_return=memo.get("expected_return"),
                    data={"source": str(memo_file), "summary": memo.get("summary", "")},
                )

                # Also record in legacy DB
                if self.db:
                    self.db.record_run(
                        agent="memo", ticker=ticker,
                        run_type=memo.get("type", "research"),
                        fair_value=memo.get("fair_value"),
                        scores=memo.get("scores"),
                        summary=memo.get("summary", ""),
                        output_path=str(memo_file),
                    )
                ingested += 1
            except Exception as e:
                log.debug(f"Library scan: {memo_file.name}: {e}")

        return ingested

    async def find_similar(self, ticker: str, sector: str = None,
                           gross_margin: float = None, roic: float = None,
                           top_k: int = 5) -> list[dict]:
        """Find similar research entries for a ticker.

        Used by Thesis and IC Review agents to provide historical context.
        """
        v2db = self._get_v2db()
        results = v2db.find_similar(
            ticker=ticker, sector=sector,
            gross_margin=gross_margin, roic=roic,
            top_k=top_k,
        )
        if not self._v2db:
            v2db.close()
        return results
