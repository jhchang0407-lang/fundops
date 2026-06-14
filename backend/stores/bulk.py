"""Bulk data store (ADR-0059): price history, the filings index, ownership
records, and sync bookkeeping.

These tables are fed by bulk ingestion (companyfacts, daily index files,
batched price downloads, quarterly ownership data sets) and read by the
workflows that previously made live provider calls. Raw bulk dumps stay in
the cache directory — only universe-scoped, decision-relevant rows land here.
"""

from __future__ import annotations

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso


class BulkStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    # --- price history -----------------------------------------------------------
    def upsert_prices(self, rows: list[dict]) -> int:
        """rows: [{ticker, date, open?, high?, low?, close, volume?, source?}]"""
        n = 0
        with self.ws.transaction() as conn:
            for r in rows:
                if not r.get("ticker") or not r.get("date") or r.get("close") is None:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, "
                    "volume, source) VALUES (?,?,?,?,?,?,?,?)",
                    (r["ticker"].upper(), str(r["date"])[:10], r.get("open"), r.get("high"),
                     r.get("low"), r["close"], r.get("volume"), r.get("source", "yfinance")),
                )
                n += 1
        return n

    def price_range(self, ticker: str, start: str | None = None, end: str | None = None) -> list[dict]:
        clauses, params = ["ticker = ?"], [ticker.upper()]
        if start:
            clauses.append("date >= ?")
            params.append(start)
        if end:
            clauses.append("date <= ?")
            params.append(end)
        rows = self.ws.query(
            f"SELECT date, open, high, low, close, volume FROM price_history "
            f"WHERE {' AND '.join(clauses)} ORDER BY date",
            params,
        )
        return [dict(r) for r in rows]

    def latest_close(self, ticker: str) -> dict | None:
        row = self.ws.query_one(
            "SELECT date, close FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker.upper(),),
        )
        return dict(row) if row else None

    def latest_closes(self) -> dict[str, float]:
        """Most-recent close per ticker in one pass — for universe-wide reads
        (factor distributions, batch market-cap) that would otherwise issue one
        latest_close() query per name."""
        rows = self.ws.query(
            "SELECT ph.ticker AS ticker, ph.close AS close FROM price_history ph "
            "JOIN (SELECT ticker, MAX(date) AS d FROM price_history GROUP BY ticker) m "
            "ON ph.ticker = m.ticker AND ph.date = m.d"
        )
        return {r["ticker"].upper(): r["close"] for r in rows if r["close"] is not None}

    def close_on_or_before(self, ticker: str, date: str) -> float | None:
        """Price at a historical point — deterministic outcome-window evidence."""
        row = self.ws.query_one(
            "SELECT close FROM price_history WHERE ticker = ? AND date <= ? "
            "ORDER BY date DESC LIMIT 1",
            (ticker.upper(), date),
        )
        return row["close"] if row else None

    def price_coverage(self) -> dict:
        row = self.ws.query_one(
            "SELECT COUNT(DISTINCT ticker) AS tickers, COUNT(*) AS rows_, "
            "MIN(date) AS first, MAX(date) AS last FROM price_history"
        )
        return dict(row) if row else {}

    # --- filings index -----------------------------------------------------------
    def add_filing(
        self, form: str, filed_at: str, accession: str | None = None,
        cik: str | None = None, ticker: str | None = None, entity_id: str | None = None,
        title: str | None = None, source: str = "daily_index",
    ) -> str | None:
        """Idempotent on accession; returns id or None when already known."""
        if accession:
            existing = self.ws.query_one("SELECT id FROM filings WHERE accession = ?", (accession,))
            if existing:
                return None
        fid = new_id("fil")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO filings (id, cik, ticker, entity_id, form, filed_at, "
                "accession, title, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (fid, cik, ticker.upper() if ticker else None, entity_id, form,
                 filed_at, accession, title, source, now_iso()),
            )
        return fid

    def filings_for(
        self, ticker: str | None = None, forms: list[str] | None = None,
        since: str | None = None, limit: int = 100,
    ) -> list[dict]:
        clauses, params = [], []
        if ticker:
            clauses.append("ticker = ?")
            params.append(ticker.upper())
        if forms:
            clauses.append(f"form IN ({','.join('?' * len(forms))})")
            params.extend(forms)
        if since:
            clauses.append("filed_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.ws.query(
            f"SELECT * FROM filings {where} ORDER BY filed_at DESC LIMIT ?", (*params, limit)
        )
        return [dict(r) for r in rows]

    def unprocessed_filings(self, forms: list[str] | None = None, limit: int = 500) -> list[dict]:
        clauses, params = ["processed = 0"], []
        if forms:
            clauses.append(f"form IN ({','.join('?' * len(forms))})")
            params.extend(forms)
        rows = self.ws.query(
            f"SELECT * FROM filings WHERE {' AND '.join(clauses)} ORDER BY filed_at LIMIT ?",
            (*params, limit),
        )
        return [dict(r) for r in rows]

    def mark_filings_processed(self, filing_ids: list[str]) -> None:
        with self.ws.transaction() as conn:
            for fid in filing_ids:
                conn.execute("UPDATE filings SET processed = 1 WHERE id = ?", (fid,))

    # --- ownership ------------------------------------------------------------------
    def add_ownership(
        self, ticker: str, kind: str, as_of: str, owner_name: str,
        shares: float | None = None, value: float | None = None,
        owner_role: str | None = None, txn_type: str | None = None,
        entity_id: str | None = None, payload: dict | None = None,
        source_id: str | None = None,
    ) -> str:
        oid = new_id("own")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO ownership_records (id, entity_id, ticker, kind, as_of, owner_name, "
                "owner_role, shares, value, txn_type, payload, source_id, captured_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid, entity_id, ticker.upper(), kind, as_of, owner_name, owner_role,
                 shares, value, txn_type, dumps(payload), source_id, now_iso()),
            )
        return oid

    def ownership_for(self, ticker: str, kind: str | None = None, limit: int = 200) -> list[dict]:
        clauses, params = ["ticker = ?"], [ticker.upper()]
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        rows = self.ws.query(
            f"SELECT * FROM ownership_records WHERE {' AND '.join(clauses)} "
            f"ORDER BY as_of DESC LIMIT ?",
            (*params, limit),
        )
        return [{**(d := dict(r)), "payload": loads(d.get("payload"))} for r in rows]

    # --- sync bookkeeping ---------------------------------------------------------------
    def get_state(self, key: str, default: str | None = None) -> str | None:
        row = self.ws.query_one("SELECT value FROM sync_state WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_state(self, key: str, value: str) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES (?,?,?)",
                (key, value, now_iso()),
            )

    def state_snapshot(self) -> dict:
        return {r["key"]: r["value"] for r in self.ws.query("SELECT key, value FROM sync_state")}
