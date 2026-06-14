"""Read-time derivation of price-dependent financial metrics (ADR-0017).

market_cap, fcf_yield, earnings_yield and pe are deliberately NOT stored — they
move with price — so every read surface (Company snapshot, peers grid, portfolio
factor tilts, screener) must derive them the SAME way from the latest stored
fundamentals plus a current price. This is the single shared implementation, so
those surfaces can never disagree or silently omit a derivable metric (the QA
'2 of 4 factor tilts are dead' / 'snapshot blank' class of bug).

Pure: a latest-metrics dict + a price in, the same dict mutated (gaps filled
only, never overwriting a stored value) out. Yields are decimals (0.05 = 5%),
matching to_flat_metrics.
"""

from __future__ import annotations


def derive_price_metrics(latest: dict, price: float | None) -> dict:
    """Fill market_cap, fcf_yield, earnings_yield, pe in-place from price + the
    stored fundamentals already in `latest`. Returns the same dict for chaining.
    Does not need history (revenue_growth, which does, stays in enriched_snapshot)."""
    def _f(key):
        v = latest.get(key)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    # Free cash flow from its components when the provider tagged operating cash
    # flow and capex but not FCF itself (common outside large-cap industrials) —
    # capex is stored as a negative outflow, so FCF = OCF − |capex|.
    if latest.get("free_cash_flow") is None:
        ocf, capex = _f("operating_cash_flow"), _f("capex")
        if ocf is not None and capex is not None:
            latest["free_cash_flow"] = ocf - abs(capex)

    shares, fcf = _f("shares_outstanding"), _f("free_cash_flow")
    net_income, eps = _f("net_income"), _f("eps")

    market_cap = _f("market_cap")
    if not market_cap and price and shares and shares > 0:
        market_cap = price * shares
        latest["market_cap"] = market_cap

    if latest.get("fcf_yield") is None and fcf is not None and market_cap:
        latest["fcf_yield"] = fcf / market_cap
    if latest.get("earnings_yield") is None and net_income is not None and market_cap:
        latest["earnings_yield"] = net_income / market_cap
    if latest.get("pe") is None and eps and eps > 0 and price:
        latest["pe"] = price / eps
    return latest
