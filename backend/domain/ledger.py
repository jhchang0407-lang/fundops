"""Portfolio ledger math (ADR-0035).

Pure functions: lots + sales in, holdings/realized P&L out. FIFO matching by
default. Corrections are not outcomes; exits are history. The holdings table
is a rebuildable projection over these calculations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Lot:
    id: str
    ticker: str
    shares: float
    cost_basis: float       # per-share cost
    purchase_date: str


@dataclass
class Sale:
    id: str
    ticker: str
    shares: float
    price: float
    sale_date: str


@dataclass
class LotMatch:
    lot_id: str
    shares: float
    cost_basis: float

    def to_dict(self) -> dict:
        return {"lot_id": self.lot_id, "shares": self.shares, "cost_basis": self.cost_basis}


class LedgerError(ValueError):
    pass


def match_sale_fifo(lots_remaining: list[tuple[Lot, float]], shares_to_sell: float) -> list[LotMatch]:
    """Match a sale against open lot remainders (FIFO by purchase date).

    `lots_remaining` is [(lot, remaining_shares)] sorted oldest first.
    Raises LedgerError when selling more shares than held — the UI should
    route that to a Portfolio Entry Correction instead.
    """
    available = sum(r for _, r in lots_remaining)
    if shares_to_sell - available > 1e-9:
        raise LedgerError(
            f"cannot sell {shares_to_sell} shares; only {available} held"
        )
    matches: list[LotMatch] = []
    left = shares_to_sell
    for lot, remaining in lots_remaining:
        if left <= 1e-12:
            break
        take = min(remaining, left)
        if take > 0:
            matches.append(LotMatch(lot.id, take, lot.cost_basis))
            left -= take
    return matches


def realized_pnl(matches: list[LotMatch], sale_price: float) -> float:
    return sum(m.shares * (sale_price - m.cost_basis) for m in matches)


def replay_ledger(lots: list[Lot], sales: list[Sale]) -> dict[str, dict]:
    """Rebuild per-ticker position state from the full ledger.

    Returns {ticker: {shares, avg_cost, cost_total, realized_pnl,
                      open_lots: [(lot, remaining)]}}.
    Sales are applied in date order against FIFO lot remainders.
    """
    by_ticker: dict[str, dict] = {}
    for lot in sorted(lots, key=lambda l: (l.purchase_date, l.id)):
        s = by_ticker.setdefault(lot.ticker, {"open_lots": [], "realized_pnl": 0.0})
        s["open_lots"].append([lot, lot.shares])
    for sale in sorted(sales, key=lambda s: (s.sale_date, s.id)):
        s = by_ticker.setdefault(sale.ticker, {"open_lots": [], "realized_pnl": 0.0})
        remaining_pairs = [(lot, rem) for lot, rem in s["open_lots"] if rem > 1e-12]
        matches = match_sale_fifo(remaining_pairs, sale.shares)
        s["realized_pnl"] += realized_pnl(matches, sale.price)
        matched = {m.lot_id: m.shares for m in matches}
        for pair in s["open_lots"]:
            lot, rem = pair
            if lot.id in matched:
                pair[1] = rem - matched[lot.id]
    out: dict[str, dict] = {}
    for ticker, s in by_ticker.items():
        open_pairs = [(lot, rem) for lot, rem in s["open_lots"] if rem > 1e-12]
        shares = sum(rem for _, rem in open_pairs)
        cost_total = sum(rem * lot.cost_basis for lot, rem in open_pairs)
        out[ticker] = {
            "shares": shares,
            "cost_total": cost_total,
            "avg_cost": (cost_total / shares) if shares > 1e-12 else None,
            "realized_pnl": s["realized_pnl"],
            "open_lots": open_pairs,
        }
    return out


def holdings_view(positions: dict[str, dict], prices: dict[str, float]) -> list[dict]:
    """Project current holdings with market values and weights."""
    rows = []
    total_value = 0.0
    for ticker, p in positions.items():
        if p["shares"] <= 1e-12:
            continue
        price = prices.get(ticker)
        mv = p["shares"] * price if price is not None else None
        if mv:
            total_value += mv
        rows.append({
            "ticker": ticker,
            "shares": p["shares"],
            "avg_cost": p["avg_cost"],
            "price": price,
            "market_value": mv,
            "unrealized_pnl": (mv - p["cost_total"]) if mv is not None else None,
            "realized_pnl": p["realized_pnl"],
        })
    for r in rows:
        r["weight"] = (r["market_value"] / total_value) if (r["market_value"] and total_value > 0) else None
    rows.sort(key=lambda r: -(r["market_value"] or 0))
    return rows
