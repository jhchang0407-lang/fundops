"""Investment identity store (ADR-0023): entities + ticker aliases."""

from __future__ import annotations

from backend.core.workspace import Workspace, new_id, now_iso


class IdentityStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    def resolve_ticker(self, ticker: str) -> dict | None:
        """Resolve a ticker symbol to its current entity."""
        row = self.ws.query_one(
            "SELECT e.* FROM ticker_aliases a JOIN investment_entities e ON e.id = a.entity_id "
            "WHERE a.ticker = ? AND a.valid_to IS NULL ORDER BY a.valid_from DESC LIMIT 1",
            (ticker.upper(),),
        )
        return dict(row) if row else None

    def ensure_entity(
        self, ticker: str, name: str | None = None,
        cik: str | None = None, sector: str | None = None, industry: str | None = None,
        sic: str | None = None,
    ) -> dict:
        """Get or create the entity behind a ticker; updates light metadata."""
        ticker = ticker.upper()
        existing = self.resolve_ticker(ticker)
        if existing:
            updates, params = [], []
            for col, val in (("name", name), ("cik", cik), ("sector", sector),
                             ("industry", industry), ("sic", sic)):
                if val and not existing.get(col):
                    updates.append(f"{col} = ?")
                    params.append(val)
            if updates:
                with self.ws.transaction() as conn:
                    conn.execute(
                        f"UPDATE investment_entities SET {', '.join(updates)} WHERE id = ?",
                        (*params, existing["id"]),
                    )
                existing = self.resolve_ticker(ticker)
            return existing
        eid = new_id("ent")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO investment_entities (id, name, cik, sector, industry, sic, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (eid, name or ticker, cik, sector, industry, sic, now_iso()),
            )
            conn.execute(
                "INSERT INTO ticker_aliases (ticker, entity_id, valid_from, source) VALUES (?,?,?,?)",
                (ticker, eid, now_iso(), "fundops"),
            )
        return self.resolve_ticker(ticker)

    def current_ticker(self, entity_id: str) -> str | None:
        row = self.ws.query_one(
            "SELECT ticker FROM ticker_aliases WHERE entity_id = ? AND valid_to IS NULL "
            "ORDER BY valid_from DESC LIMIT 1",
            (entity_id,),
        )
        return row["ticker"] if row else None

    def industry_tree(self) -> list[dict]:
        """Sectors -> industries with constituent counts, from entity identity
        data. Drives the Research Hub browser. Read-only."""
        rows = self.ws.query(
            """
            SELECT e.sector, e.industry, COUNT(DISTINCT a.ticker) AS n
            FROM investment_entities e
            JOIN ticker_aliases a ON a.entity_id = e.id AND a.valid_to IS NULL
            WHERE e.sector IS NOT NULL
            GROUP BY e.sector, e.industry
            ORDER BY e.sector, n DESC
            """
        )
        tree: dict[str, dict] = {}
        for r in rows:
            sector = tree.setdefault(r["sector"], {"sector": r["sector"], "count": 0,
                                                   "industries": []})
            sector["count"] += r["n"]
            if r["industry"]:
                sector["industries"].append({"industry": r["industry"], "count": r["n"]})
        return list(tree.values())

    def entities_in_group(self, sector: str | None = None,
                          industry: str | None = None, limit: int = 500) -> list[dict]:
        """Entities (with current ticker) in one sector/industry group."""
        clauses, params = [], []
        if industry:
            clauses.append("e.industry = ?")
            params.append(industry)
        if sector:
            clauses.append("e.sector = ?")
            params.append(sector)
        if not clauses:
            return []
        rows = self.ws.query(
            f"""
            SELECT e.*, a.ticker FROM investment_entities e
            JOIN ticker_aliases a ON a.entity_id = e.id AND a.valid_to IS NULL
            WHERE {' AND '.join(clauses)} ORDER BY a.ticker LIMIT ?
            """,
            (*params, limit),
        )
        return [dict(r) for r in rows]

    def entities_with_sic_prefix(self, prefix: str, limit: int = 500) -> list[dict]:
        """Entities whose (zero-padded) SIC code starts with `prefix` — the
        middle peer-grouping tiers between exact industry and broad sector."""
        if not prefix:
            return []
        rows = self.ws.query(
            """
            SELECT e.*, a.ticker FROM investment_entities e
            JOIN ticker_aliases a ON a.entity_id = e.id AND a.valid_to IS NULL
            WHERE e.sic LIKE ? ORDER BY a.ticker LIMIT ?
            """,
            (prefix + "%", limit),
        )
        return [dict(r) for r in rows]

    def all_tickers(self) -> list[str]:
        """Every ticker with a current entity — the data-bearing set (chat
        analyst lookups), broader than Library history (known_tickers)."""
        rows = self.ws.query(
            "SELECT DISTINCT ticker FROM ticker_aliases WHERE valid_to IS NULL ORDER BY ticker"
        )
        return [r["ticker"] for r in rows]

    def known_tickers(self) -> list[str]:
        """Known Library Tickers: any ticker with retained artifacts, portfolio
        history, or saved screener work."""
        rows = self.ws.query(
            """
            SELECT DISTINCT t.ticker FROM (
              SELECT ticker FROM artifacts WHERE ticker IS NOT NULL
              UNION SELECT ticker FROM portfolio_lots
              UNION SELECT ticker FROM portfolio_sales
              UNION SELECT ticker FROM screener_results WHERE passed = 1
            ) t ORDER BY t.ticker
            """
        )
        return [r["ticker"] for r in rows]
