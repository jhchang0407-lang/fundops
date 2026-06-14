"""Portfolio ledger store (ADR-0035, ADR-0041). Holdings are a rebuildable
projection over lots and sales; corrections never count as outcomes."""

from __future__ import annotations

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso
from backend.domain.ledger import (
    LedgerError, Lot, Sale, holdings_view, match_sale_fifo, realized_pnl, replay_ledger,
)


class PortfolioStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    # --- ledger writes ---------------------------------------------------------
    def add_lot(
        self, ticker: str, shares: float, cost_basis: float, purchase_date: str,
        entity_id: str | None = None, import_source: str = "manual",
        position_type: str | None = None, note: str | None = None,
    ) -> str:
        if shares <= 0 or cost_basis < 0:
            raise LedgerError("purchase lot needs positive shares and non-negative cost basis")
        lid = new_id("lot")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO portfolio_lots (id, entity_id, ticker, shares, cost_basis, purchase_date, "
                "import_source, position_type, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (lid, entity_id, ticker.upper(), shares, cost_basis, purchase_date,
                 import_source, position_type, note, now_iso()),
            )
        self.rebuild_holdings()
        return lid

    def record_sale(
        self, ticker: str, shares: float, price: float, sale_date: str,
        entity_id: str | None = None, note: str | None = None,
    ) -> dict:
        """Record a Portfolio Sale Entry; FIFO-matches lots and computes realized P&L."""
        if shares <= 0:
            raise LedgerError("sale needs positive share count")
        ticker = ticker.upper()
        positions = self._replay()
        pos = positions.get(ticker)
        open_pairs = pos["open_lots"] if pos else []
        matches = match_sale_fifo(open_pairs, shares)
        pnl = realized_pnl(matches, price)
        sid = new_id("sale")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO portfolio_sales (id, entity_id, ticker, shares, price, sale_date, "
                "realized_pnl, lot_matches, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sid, entity_id, ticker, shares, price, sale_date, pnl,
                 dumps([m.to_dict() for m in matches]), note, now_iso()),
            )
        self.rebuild_holdings()
        return {"id": sid, "realized_pnl": pnl, "matches": [m.to_dict() for m in matches]}

    def correct_lot(self, lot_id: str, shares: float | None = None,
                    cost_basis: float | None = None, purchase_date: str | None = None) -> str:
        """Portfolio Entry Correction: supersede the bad lot with a fixed one.
        Corrections are not investment outcomes and never feed learning."""
        row = self.ws.query_one("SELECT * FROM portfolio_lots WHERE id = ?", (lot_id,))
        if not row:
            raise LedgerError(f"unknown lot {lot_id}")
        old = dict(row)
        new_shares = shares if shares is not None else old["shares"]
        new_cost = cost_basis if cost_basis is not None else old["cost_basis"]
        new_date = purchase_date or old["purchase_date"]
        if new_shares <= 0 or new_cost < 0:
            raise LedgerError("corrected lot needs positive shares and non-negative cost basis")
        new_lot_id = new_id("lot")
        # Replay the corrected ledger BEFORE committing: a correction that
        # shrinks a lot below its already-sold shares would otherwise make
        # every future holdings rebuild raise.
        self._dry_run_replay(
            replace={lot_id: Lot(new_lot_id, old["ticker"], new_shares, new_cost, new_date)})
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO portfolio_lots (id, entity_id, ticker, shares, cost_basis, purchase_date, "
                "import_source, position_type, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_lot_id, old["entity_id"], old["ticker"],
                 shares if shares is not None else old["shares"],
                 cost_basis if cost_basis is not None else old["cost_basis"],
                 purchase_date or old["purchase_date"], old["import_source"],
                 old["position_type"], "correction of " + lot_id, now_iso()),
            )
            conn.execute("UPDATE portfolio_lots SET corrected_by = ? WHERE id = ?", (new_lot_id, lot_id))
        self.rebuild_holdings()
        return new_lot_id

    def remove_lot_as_correction(self, lot_id: str) -> None:
        """Mark an erroneous lot as corrected-away (zero replacement)."""
        self._dry_run_replay(replace={lot_id: None})
        with self.ws.transaction() as conn:
            conn.execute("UPDATE portfolio_lots SET corrected_by = 'removed' WHERE id = ?", (lot_id,))
        self.rebuild_holdings()

    def _dry_run_replay(self, replace: dict[str, Lot | None]) -> None:
        """Replay the ledger with the proposed lot edits applied; raise before
        any write if recorded sales no longer match."""
        lots: list[Lot] = []
        for r in self.lots():
            if r["id"] in replace:
                if replace[r["id"]] is not None:
                    lots.append(replace[r["id"]])
            else:
                lots.append(Lot(r["id"], r["ticker"], r["shares"], r["cost_basis"],
                                r["purchase_date"]))
        sales = [Sale(r["id"], r["ticker"], r["shares"], r["price"], r["sale_date"])
                 for r in self.sales()]
        try:
            replay_ledger(lots, sales)
        except LedgerError as exc:
            raise LedgerError(f"correction conflicts with recorded sales: {exc}") from exc

    def set_position_type(self, ticker: str, position_type: str | None) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE portfolio_lots SET position_type = ? WHERE ticker = ? AND corrected_by IS NULL",
                (position_type, ticker.upper()),
            )
        self.rebuild_holdings()

    # --- ledger reads -------------------------------------------------------------
    def lots(self, ticker: str | None = None, include_corrected: bool = False) -> list[dict]:
        clauses, params = [], []
        if not include_corrected:
            clauses.append("corrected_by IS NULL")
        if ticker:
            clauses.append("ticker = ?")
            params.append(ticker.upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.ws.query(
            f"SELECT * FROM portfolio_lots {where} ORDER BY purchase_date, created_at", params
        )
        return [dict(r) for r in rows]

    def sales(self, ticker: str | None = None) -> list[dict]:
        sql = "SELECT * FROM portfolio_sales"
        params: tuple = ()
        if ticker:
            sql += " WHERE ticker = ?"
            params = (ticker.upper(),)
        rows = self.ws.query(sql + " ORDER BY sale_date, created_at", params)
        return [{**(d := dict(r)), "lot_matches": loads(d.get("lot_matches"), [])} for r in rows]

    def _replay(self) -> dict[str, dict]:
        lots = [
            Lot(r["id"], r["ticker"], r["shares"], r["cost_basis"], r["purchase_date"])
            for r in self.lots()
        ]
        sales = [
            Sale(r["id"], r["ticker"], r["shares"], r["price"], r["sale_date"])
            for r in self.sales()
        ]
        return replay_ledger(lots, sales)

    # --- prices ---------------------------------------------------------------------
    def mark_price(self, ticker: str, price: float) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO price_marks (ticker, price, as_of) VALUES (?,?,?)",
                (ticker.upper(), price, now_iso()),
            )

    def prices(self) -> dict[str, float]:
        return {r["ticker"]: r["price"] for r in self.ws.query("SELECT * FROM price_marks")
                if r["price"] is not None}

    # --- holdings projection (rebuildable) ----------------------------------------------
    def rebuild_holdings(self) -> list[dict]:
        positions = self._replay()
        prices = self.prices()
        rows = holdings_view(positions, prices)
        position_types = {
            r["ticker"]: r["position_type"]
            for r in self.ws.query(
                "SELECT ticker, position_type FROM portfolio_lots "
                "WHERE corrected_by IS NULL AND position_type IS NOT NULL"
            )
        }
        entity_ids = {
            r["ticker"]: r["entity_id"]
            for r in self.ws.query(
                "SELECT ticker, entity_id FROM portfolio_lots WHERE entity_id IS NOT NULL"
            )
        }
        existing_coverage = {
            r["ticker"]: (r["coverage_state"], r["coverage_memo_artifact_id"])
            for r in self.ws.query("SELECT ticker, coverage_state, coverage_memo_artifact_id FROM holdings")
        }
        with self.ws.transaction() as conn:
            conn.execute("DELETE FROM holdings")
            for r in rows:
                cov_state, cov_memo = existing_coverage.get(r["ticker"], ("none", None))
                conn.execute(
                    "INSERT INTO holdings (ticker, entity_id, shares, avg_cost, market_value, "
                    "unrealized_pnl, weight, position_type, coverage_state, coverage_memo_artifact_id, "
                    "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (r["ticker"], entity_ids.get(r["ticker"]), r["shares"], r["avg_cost"],
                     r["market_value"], r["unrealized_pnl"], r["weight"],
                     position_types.get(r["ticker"]), cov_state, cov_memo, now_iso()),
                )
        return rows

    def holdings(self) -> list[dict]:
        rows = self.ws.query("SELECT * FROM holdings ORDER BY market_value DESC NULLS LAST")
        return [dict(r) for r in rows]

    def holding(self, ticker: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM holdings WHERE ticker = ?", (ticker.upper(),))
        return dict(row) if row else None

    def set_coverage_state(self, ticker: str, state: str, memo_artifact_id: str | None = None) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE holdings SET coverage_state = ?, coverage_memo_artifact_id = "
                "COALESCE(?, coverage_memo_artifact_id), updated_at = ? WHERE ticker = ?",
                (state, memo_artifact_id, now_iso(), ticker.upper()),
            )

    def totals(self) -> dict:
        h = self.holdings()
        market_value = sum(r["market_value"] or 0 for r in h)
        cost = sum((r["avg_cost"] or 0) * r["shares"] for r in h)
        realized = sum(r["realized_pnl"] or 0 for r in self.sales())
        return {
            "market_value": market_value,
            "cost_basis": cost,
            "unrealized_pnl": market_value - cost if h else 0.0,
            "realized_pnl": realized,
            "positions": len(h),
        }
