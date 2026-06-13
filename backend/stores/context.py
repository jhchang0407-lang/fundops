"""Market-context store: company events, watchlists/themes, macro series,
filing-section cache (schema migration 4). The write path for everything the
Phase 2 market-context layer retains."""

from __future__ import annotations

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso


class ContextStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    # --- company events (earnings/dividend/split) --------------------------------
    def upsert_event(self, ticker: str, kind: str, event_date: str,
                     label: str | None = None, payload: dict | None = None,
                     source: str = "yfinance") -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO company_events (id, ticker, kind, event_date, label, payload, "
                "source, captured_at) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT (ticker, kind, event_date) DO UPDATE SET "
                "label = excluded.label, payload = excluded.payload, "
                "captured_at = excluded.captured_at",
                (new_id("evt"), ticker.upper(), kind, str(event_date)[:10], label,
                 dumps(payload), source, now_iso()),
            )

    def clear_future_events(self, ticker: str, kind: str, on_or_after: str) -> None:
        """Drop future-dated calendar rows before a fresh provider pull —
        earnings/dividend estimates move, and the unique key is the date, so
        a shifted estimate would otherwise leave a phantom upcoming event."""
        with self.ws.transaction() as conn:
            conn.execute(
                "DELETE FROM company_events WHERE ticker = ? AND kind = ? AND event_date >= ?",
                (ticker.upper(), kind, str(on_or_after)[:10]),
            )

    def events_for(self, ticker: str, limit: int = 50) -> list[dict]:
        rows = self.ws.query(
            "SELECT * FROM company_events WHERE ticker = ? ORDER BY event_date DESC LIMIT ?",
            (ticker.upper(), limit),
        )
        return [{**(d := dict(r)), "payload": loads(d.get("payload"))} for r in rows]

    def upcoming_events(self, on_or_after: str, tickers: list[str] | None = None,
                        before: str | None = None, limit: int = 30) -> list[dict]:
        sql = "SELECT * FROM company_events WHERE event_date >= ?"
        params: list = [str(on_or_after)[:10]]
        if before:
            sql += " AND event_date <= ?"
            params.append(str(before)[:10])
        if tickers:
            sql += f" AND ticker IN ({','.join('?' * len(tickers))})"
            params.extend(t.upper() for t in tickers)
        rows = self.ws.query(sql + " ORDER BY event_date LIMIT ?", (*params, limit))
        return [{**(d := dict(r)), "payload": loads(d.get("payload"))} for r in rows]

    # --- watchlists & themes --------------------------------------------------------
    def create_watchlist(self, name: str, kind: str = "watchlist",
                         note: str | None = None) -> dict:
        wid = new_id("wl")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO watchlists (id, name, kind, note, created_at) VALUES (?,?,?,?,?)",
                (wid, name.strip(), kind, note, now_iso()),
            )
        return self.get_watchlist(wid)

    def get_watchlist(self, watchlist_id: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,))
        if not row:
            return None
        d = dict(row)
        d["tickers"] = [r["ticker"] for r in self.ws.query(
            "SELECT ticker FROM watchlist_tickers WHERE watchlist_id = ? ORDER BY added_at",
            (watchlist_id,))]
        return d

    def watchlist_by_name(self, name: str) -> dict | None:
        row = self.ws.query_one(
            "SELECT id FROM watchlists WHERE name = ? COLLATE NOCASE", (name.strip(),))
        return self.get_watchlist(row["id"]) if row else None

    def list_watchlists(self, kind: str | None = None) -> list[dict]:
        sql, params = "SELECT id FROM watchlists", ()
        if kind:
            sql += " WHERE kind = ?"
            params = (kind,)
        rows = self.ws.query(sql + " ORDER BY created_at", params)
        return [self.get_watchlist(r["id"]) for r in rows]

    def delete_watchlist(self, watchlist_id: str) -> None:
        with self.ws.transaction() as conn:
            conn.execute("DELETE FROM watchlist_tickers WHERE watchlist_id = ?", (watchlist_id,))
            conn.execute("DELETE FROM watchlists WHERE id = ?", (watchlist_id,))

    def add_ticker(self, watchlist_id: str, ticker: str) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist_tickers (watchlist_id, ticker, added_at) "
                "VALUES (?,?,?)",
                (watchlist_id, ticker.upper(), now_iso()),
            )

    def remove_ticker(self, watchlist_id: str, ticker: str) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "DELETE FROM watchlist_tickers WHERE watchlist_id = ? AND ticker = ?",
                (watchlist_id, ticker.upper()),
            )

    # --- macro series cache ------------------------------------------------------------
    def upsert_macro(self, series: str, points: list[dict]) -> int:
        n = 0
        with self.ws.transaction() as conn:
            for p in points:
                if p.get("date") is None or p.get("value") is None:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO macro_series (series, date, value) VALUES (?,?,?)",
                    (series, str(p["date"])[:10], float(p["value"])),
                )
                n += 1
        return n

    def macro_points(self, series: str, start: str | None = None,
                     limit: int = 600) -> list[dict]:
        sql, params = "SELECT date, value FROM macro_series WHERE series = ?", [series]
        if start:
            sql += " AND date >= ?"
            params.append(start)
        rows = self.ws.query(sql + " ORDER BY date DESC LIMIT ?", (*params, limit))
        return [dict(r) for r in reversed(rows)]

    def macro_latest(self, series: str) -> dict | None:
        row = self.ws.query_one(
            "SELECT date, value FROM macro_series WHERE series = ? ORDER BY date DESC LIMIT 1",
            (series,),
        )
        return dict(row) if row else None

    # --- filing-section cache -------------------------------------------------------
    def upsert_filing_section(self, accession: str, section: str, content: str,
                              ticker: str | None = None, form: str | None = None,
                              filed_at: str | None = None) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO filing_sections (id, ticker, accession, form, filed_at, section, "
                "content, captured_at) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT (accession, section) DO UPDATE SET content = excluded.content, "
                "captured_at = excluded.captured_at",
                (new_id("fsec"), ticker.upper() if ticker else None, accession, form,
                 filed_at, section, content, now_iso()),
            )

    def filing_section(self, accession: str, section: str) -> dict | None:
        row = self.ws.query_one(
            "SELECT * FROM filing_sections WHERE accession = ? AND section = ?",
            (accession, section),
        )
        return dict(row) if row else None

    def filing_sections_for(self, ticker: str, section: str, limit: int = 6) -> list[dict]:
        rows = self.ws.query(
            "SELECT * FROM filing_sections WHERE ticker = ? AND section = ? "
            "ORDER BY filed_at DESC LIMIT ?",
            (ticker.upper(), section, limit),
        )
        return [dict(r) for r in rows]
