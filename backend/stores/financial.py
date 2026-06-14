"""Financial data store: reported facts, calculated observations, latest
projection (ADR-0042..0047)."""

from __future__ import annotations

from datetime import datetime

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso
from backend.domain.metric_catalog import (
    CATALOG_VERSION,
    MAPPING_VERSION,
    PERIOD_SCALED_METRICS,
    is_market_metric,
)

# A latest-projection value whose period trails the company's freshest reported
# period by more than this is flagged stale (not restated by recent filings).
STALE_PROJECTION_DAYS = 540


def _latest_rank(row) -> tuple[int, str, int]:
    """Ordering key for the latest-financials projection: period-scaled
    metrics rank annual/TTM above quarterly, then newest period_end; ties
    between cadences at the same period_end resolve to the full-period row."""
    full_period = 0 if row["period_type"] == "quarterly" else 1
    scaled = row["metric"] in PERIOD_SCALED_METRICS
    return (full_period if scaled else 1, row["period_end"], full_period)


class FinancialStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    # --- reported facts ---------------------------------------------------------
    def add_fact(
        self, entity_id: str, concept: str, period_end: str, period_type: str,
        value: float | None, unit: str | None = None, taxonomy: str | None = None,
        source_id: str | None = None, accession: str | None = None,
        filed_at: str | None = None, mapped_concept: str | None = None,
        field_label: str | None = None, mapping_status: str | None = None,
    ) -> str:
        fid = new_id("fact")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO reported_financial_facts (id, entity_id, concept, taxonomy, period_end, "
                "period_type, value, unit, source_id, accession, filed_at, mapped_concept, "
                "field_label, mapping_status, captured_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fid, entity_id, concept, taxonomy, period_end, period_type, value, unit,
                 source_id, accession, filed_at, mapped_concept, field_label, mapping_status,
                 now_iso()),
            )
        return fid

    # --- governed AI mapping corpus (ADR-0015) -----------------------------------
    def unmapped_facts(self, entity_id: str, limit: int = 200) -> list[dict]:
        """Retained XBRL facts awaiting a mapping decision — the AI mapper's
        input. Newest period first; a tag may appear once per retained period
        (the mapper accepts a per-period observation for an accepted mapping)."""
        rows = self.ws.query(
            "SELECT * FROM reported_financial_facts WHERE entity_id = ? "
            "AND mapping_status = 'unmapped' AND superseded_by IS NULL "
            "ORDER BY period_end DESC LIMIT ?",
            (entity_id, limit),
        )
        return [dict(r) for r in rows]

    def set_mapping(self, fact_id: str, status: str, mapped_concept: str | None,
                    confidence: float | None, reason: str, mapping_version: str) -> None:
        """Record a mapping decision on an unmapped fact (ADR-0015): accepted
        (mapped_concept set) or rejected/candidate (reason retained as evidence)."""
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE reported_financial_facts SET mapping_status = ?, mapped_concept = ?, "
                "mapping_confidence = ?, mapping_reason = ?, mapping_version = ? WHERE id = ?",
                (status, mapped_concept, confidence, reason, mapping_version, fact_id),
            )

    # --- observations ------------------------------------------------------------
    def add_observation(
        self, entity_id: str, metric: str, period_end: str, period_type: str,
        value: float | None, unit: str | None = None, is_calculated: bool = False,
        lineage: dict | None = None, quality: str = "accepted",
        refresh_latest: bool = True,
    ) -> str:
        oid = new_id("obs")
        with self.ws.transaction() as conn:
            # Supersede a prior observation for the same (metric, period).
            prior = conn.execute(
                "SELECT id FROM financial_observations WHERE entity_id = ? AND metric = ? "
                "AND period_end = ? AND period_type = ? AND superseded_by IS NULL",
                (entity_id, metric, period_end, period_type),
            ).fetchone()
            conn.execute(
                "INSERT INTO financial_observations (id, entity_id, metric, period_end, period_type, "
                "value, unit, is_calculated, lineage, catalog_version, mapping_version, quality, captured_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid, entity_id, metric, period_end, period_type, value, unit,
                 1 if is_calculated else 0, dumps(lineage), CATALOG_VERSION, MAPPING_VERSION,
                 quality, now_iso()),
            )
            if prior:
                conn.execute(
                    "UPDATE financial_observations SET superseded_by = ? WHERE id = ?",
                    (oid, prior["id"]),
                )
        if refresh_latest:
            self.refresh_latest(entity_id, metric)
        return oid

    def observations(
        self, entity_id: str, metric: str | None = None,
        period_type: str | None = None, limit: int = 60,
    ) -> list[dict]:
        clauses, params = ["entity_id = ?", "superseded_by IS NULL"], [entity_id]
        if metric:
            clauses.append("metric = ?")
            params.append(metric)
        if period_type:
            clauses.append("period_type = ?")
            params.append(period_type)
        rows = self.ws.query(
            f"SELECT * FROM financial_observations WHERE {' AND '.join(clauses)} "
            f"ORDER BY period_end DESC LIMIT ?",
            (*params, limit),
        )
        return [{**(d := dict(r)), "lineage": loads(d.get("lineage"))} for r in rows]

    def supersede_rolling(self, entity_id: str, metric: str, period_type: str,
                          keep_id: str) -> None:
        """Rolling point-in-time metrics (momentum, volatility, dollar volume)
        are recomputed every price sync with a new period_end; older snapshots
        are derivable from price history, so they supersede instead of piling
        up one row per metric per day."""
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE financial_observations SET superseded_by = ? "
                "WHERE entity_id = ? AND metric = ? AND period_type = ? "
                "AND superseded_by IS NULL AND id != ?",
                (keep_id, entity_id, metric, period_type, keep_id),
            )

    def periods(self, entity_id: str, period_type: str, limit: int = 600) -> list[dict]:
        """Observations grouped per period: [{period_end, metrics}], newest
        first. Shared read for the Company Page financials and chat tools.

        Excludes market technicals (momentum, volatility, dollar volume, price,
        market cap): they are point-in-time price data tagged with the quote
        cadence, not statement facts (ADR-0043), and would otherwise pose as the
        newest 'quarterly' statement column. They remain available to the
        screener via latest_financials / observations().

        Drops cover-page share-count snapshots: SEC tags the current
        shares-outstanding fact (dei:EntityCommonStockSharesOutstanding) with
        the filing cover date, which is off the fiscal-year-end cycle and
        carries no statement data. Left in, those land as duplicate-year
        columns of all-blank cells; the real fiscal period already retains its
        own share count, so nothing is lost by excluding them."""
        grouped: dict[str, dict] = {}
        for obs in self.observations(entity_id, period_type=period_type, limit=limit):
            if is_market_metric(obs["metric"]):
                continue
            grouped.setdefault(obs["period_end"], {})[obs["metric"]] = obs["value"]
        return [{"period_end": pe, "metrics": grouped[pe]}
                for pe in sorted(grouped, reverse=True)
                if set(grouped[pe]) != {"shares_outstanding"}]

    # --- latest projection (rebuildable) -------------------------------------------
    def refresh_latest(self, entity_id: str, metric: str | None = None) -> None:
        """Eager recalculation of the latest-financials projection (ADR-0047).

        Newest period wins per metric — except PERIOD_SCALED_METRICS (flows
        like eps/revenue/FCF and flow-over-stock returns like ROE), where the
        newest annual/TTM observation wins and a quarterly value is only the
        fallback when no full-period basis is retained: a single quarter's EPS
        must never become the headline EPS that annual-basis arithmetic
        (justified-PE anchors, constitution thresholds) multiplies against."""
        params: list = [entity_id]
        metric_clause = ""
        if metric:
            metric_clause = "AND metric = ?"
            params.append(metric)
        rows = self.ws.query(
            f"SELECT metric, value, period_end, period_type FROM financial_observations "
            f"WHERE entity_id = ? {metric_clause} AND superseded_by IS NULL "
            "AND quality = 'accepted'",
            params,
        )
        best: dict[str, dict] = {}
        for r in rows:
            cur = best.get(r["metric"])
            if cur is None or _latest_rank(r) > _latest_rank(cur):
                best[r["metric"]] = r
        with self.ws.transaction() as conn:
            for r in best.values():
                conn.execute(
                    "INSERT OR REPLACE INTO latest_financials (entity_id, metric, value, period_end, "
                    "period_type, updated_at) VALUES (?,?,?,?,?,?)",
                    (entity_id, r["metric"], r["value"], r["period_end"], r["period_type"], now_iso()),
                )

    def latest(self, entity_id: str) -> dict[str, float | None]:
        rows = self.ws.query(
            "SELECT metric, value FROM latest_financials WHERE entity_id = ?", (entity_id,)
        )
        return {r["metric"]: r["value"] for r in rows}

    def latest_basis(self, entity_id: str) -> dict[str, dict]:
        """Per-metric reporting basis behind the latest projection: {metric ->
        {period_end, period_type, stale}}. Lets the snapshot KPI strip label which
        period each value came from instead of silently mixing bases (ISSUE-018),
        and flags a metric whose newest observation trails the company's freshest
        reported period by more than ~18 months — a value not restated by recent
        filings that would otherwise read as current (e.g. a 2-year-old debt/equity)."""
        rows = self.ws.query(
            "SELECT metric, period_end, period_type FROM latest_financials WHERE entity_id = ?",
            (entity_id,),
        )
        period_ends = [r["period_end"] for r in rows if r["period_end"]]
        newest = max(period_ends) if period_ends else None

        def _stale(pe: str | None) -> bool:
            if not pe or not newest:
                return False
            try:
                gap = (datetime.fromisoformat(newest[:10])
                       - datetime.fromisoformat(pe[:10])).days
            except ValueError:
                return False
            return gap > STALE_PROJECTION_DAYS

        return {r["metric"]: {"period_end": r["period_end"],
                              "period_type": r["period_type"],
                              "stale": _stale(r["period_end"])} for r in rows}

    def source_drilldown(
        self, entity_id: str, metric: str, period_end: str | None = None,
        period_type: str | None = None,
    ) -> dict | None:
        """Trace a metric value back to its accepted observation and retained
        reported fact(s), when the lineage has enough SEC basis.

        This is a read-side projection only. Derived observations expose their
        formula/input lineage and attach any retained input facts for the same
        period; read-time derived values (market_cap, P/E, growth) are handled by
        the company fact-sheet builder because they do not have observation rows.
        """
        obs = self._source_observation(entity_id, metric, period_end, period_type)
        if not obs:
            return None
        d = dict(obs)
        lineage = loads(d.get("lineage"), {})
        facts = self._facts_for_observation(entity_id, d, lineage)
        source_ids = sorted({f.get("source_id") for f in facts if f.get("source_id")})
        sources = self._source_rows(source_ids)
        return {
            "metric": d["metric"],
            "observation_id": d["id"],
            "value": d["value"],
            "unit": d["unit"],
            "period_end": d["period_end"],
            "period_type": d["period_type"],
            "quality": d["quality"],
            "is_calculated": bool(d["is_calculated"]),
            "catalog_version": d["catalog_version"],
            "mapping_version": d["mapping_version"],
            "lineage": lineage,
            "facts": facts,
            "sources": sources,
        }

    def latest_source_drilldowns(self, entity_id: str, metrics: list[str] | tuple[str, ...]) -> dict:
        return {
            metric: drilldown
            for metric in metrics
            if (drilldown := self.source_drilldown(entity_id, metric)) is not None
        }

    def mapping_gap_summary(self, entity_id: str, limit: int = 8) -> dict:
        """Compact data-quality read for retained unmapped/rejected tags."""
        counts = {
            r["mapping_status"] or "unknown": r["n"]
            for r in self.ws.query(
                "SELECT COALESCE(mapping_status, 'unknown') AS mapping_status, COUNT(*) AS n "
                "FROM reported_financial_facts WHERE entity_id = ? AND superseded_by IS NULL "
                "AND mapping_status IS NOT NULL GROUP BY mapping_status",
                (entity_id,),
            )
        }
        rows = self.ws.query(
            "SELECT concept, field_label, unit, mapping_status, COUNT(*) AS count, "
            "MAX(period_end) AS latest_period, MAX(filed_at) AS latest_filed "
            "FROM reported_financial_facts WHERE entity_id = ? AND superseded_by IS NULL "
            "AND mapping_status IN ('unmapped', 'rejected', 'candidate') "
            "GROUP BY concept, field_label, unit, mapping_status "
            "ORDER BY count DESC, latest_period DESC LIMIT ?",
            (entity_id, limit),
        )
        return {"counts": counts, "tags": [dict(r) for r in rows]}

    def _source_observation(
        self, entity_id: str, metric: str, period_end: str | None,
        period_type: str | None,
    ):
        clauses = [
            "entity_id = ?", "metric = ?", "superseded_by IS NULL",
            "quality = 'accepted'",
        ]
        params: list = [entity_id, metric]
        if period_end:
            clauses.append("period_end = ?")
            params.append(period_end)
        if period_type:
            clauses.append("period_type = ?")
            params.append(period_type)
        if not period_end and not period_type:
            latest = self.ws.query_one(
                "SELECT period_end, period_type FROM latest_financials "
                "WHERE entity_id = ? AND metric = ?",
                (entity_id, metric),
            )
            if latest:
                clauses.append("period_end = ?")
                clauses.append("period_type = ?")
                params.extend([latest["period_end"], latest["period_type"]])
        return self.ws.query_one(
            f"SELECT * FROM financial_observations WHERE {' AND '.join(clauses)} "
            "ORDER BY captured_at DESC LIMIT 1",
            params,
        )

    def _facts_for_observation(self, entity_id: str, obs: dict, lineage: dict) -> list[dict]:
        facts: list[dict] = []
        seen: set[str] = set()

        def add_rows(rows, input_metric: str | None = None) -> None:
            for row in rows:
                d = dict(row)
                if d["id"] in seen:
                    continue
                seen.add(d["id"])
                if input_metric:
                    d["input_metric"] = input_metric
                facts.append(d)

        tag = lineage.get("tag") or lineage.get("concept")
        if tag:
            clauses = ["entity_id = ?", "concept = ?", "period_end = ?", "period_type = ?",
                       "superseded_by IS NULL"]
            params: list = [entity_id, tag, obs["period_end"], obs["period_type"]]
            if lineage.get("accession"):
                clauses.append("accession = ?")
                params.append(lineage["accession"])
            add_rows(self.ws.query(
                f"SELECT * FROM reported_financial_facts WHERE {' AND '.join(clauses)} "
                "ORDER BY filed_at DESC, captured_at DESC LIMIT 5",
                params,
            ))

        # Direct mapped observations may not carry a tag in older rows. Fall
        # back to mapped_concept for the same metric/period.
        add_rows(self.ws.query(
            "SELECT * FROM reported_financial_facts WHERE entity_id = ? "
            "AND mapped_concept = ? AND period_end = ? AND period_type = ? "
            "AND superseded_by IS NULL ORDER BY filed_at DESC, captured_at DESC LIMIT 5",
            (entity_id, obs["metric"], obs["period_end"], obs["period_type"]),
        ))

        inputs = lineage.get("inputs") if isinstance(lineage, dict) else None
        if isinstance(inputs, dict):
            for input_metric in inputs:
                add_rows(self.ws.query(
                    "SELECT * FROM reported_financial_facts WHERE entity_id = ? "
                    "AND mapped_concept = ? AND period_end = ? AND period_type = ? "
                    "AND superseded_by IS NULL ORDER BY filed_at DESC, captured_at DESC LIMIT 5",
                    (entity_id, input_metric, obs["period_end"], obs["period_type"]),
                ), input_metric=input_metric)
        return facts

    def _source_rows(self, source_ids: list[str]) -> list[dict]:
        if not source_ids:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        rows = self.ws.query(
            f"SELECT id, kind, locator, title, publisher, content_hash, retention_tier, "
            f"fetched_at FROM evidence_sources WHERE id IN ({placeholders})",
            source_ids,
        )
        return [dict(r) for r in rows]

    def latest_value(self, entity_id: str, metric: str) -> float | None:
        row = self.ws.query_one(
            "SELECT value FROM latest_financials WHERE entity_id = ? AND metric = ?",
            (entity_id, metric),
        )
        return row["value"] if row else None

    def store_metrics_snapshot(
        self, entity_id: str, metrics: dict[str, float | None],
        period_end: str, period_type: str = "annual", lineage: dict | None = None,
    ) -> None:
        """Bulk-store calculated metric values for one period (provider fetch)."""
        for metric, value in metrics.items():
            if value is None or isinstance(value, str):
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            self.add_observation(
                entity_id, metric, period_end, period_type, v,
                is_calculated=True, lineage=lineage, refresh_latest=False,
            )
        self.refresh_latest(entity_id)
