"""Market technicals computed locally from stored daily bars.

With 5 years of universe price history retained (opconfig
data.price_history_years), the OHLCV table can answer momentum, drawdown-
from-high, realized volatility, and liquidity questions without any provider
call. These land as Calculated Financial Observations (catalog metrics:
momentum_1m/3m/6m/12m, pct_below_52w_high, volatility_90d,
avg_dollar_volume_3m, avg_volume_3m) so the screener, chat analyst, and
Company Page treat them exactly like reported fundamentals.

Rolling snapshots supersede their prior observation (FinancialStore
.supersede_rolling) — history is fully derivable from price_history, so only
the latest value is kept live.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

log = logging.getLogger("fundops.ingest.price_metrics")

PERIOD_TYPE = "quarterly"   # point-in-time market data rides the quote path's cadence
LOOKBACK_DAYS = 380         # calendar days of bars needed for 12m windows
MOMENTUM_WINDOWS = {        # metric -> calendar days
    "momentum_1m": 30,
    "momentum_3m": 91,
    "momentum_6m": 183,
    "momentum_12m": 365,
}
VOL_TRADING_DAYS = 90
ADV_TRADING_DAYS = 63
TRADING_DAYS_PER_YEAR = 252
# A window is computable when the earliest retained bar is at least this
# fraction of the window back — guards short histories (recent IPOs, gaps).
WINDOW_COVERAGE = 0.8


def compute_price_metrics(bars: list[dict]) -> dict[str, float]:
    """Pure computation over ascending daily bars [{date, close, volume?}].
    Returns only the metrics whose window is actually covered by the data."""
    bars = [b for b in bars if b.get("close") is not None]
    if len(bars) < 2:
        return {}
    out: dict[str, float] = {}
    last = bars[-1]
    last_date = _date(last["date"])
    last_close = float(last["close"])
    first_date = _date(bars[0]["date"])

    for metric, days in MOMENTUM_WINDOWS.items():
        if (last_date - first_date).days < days * WINDOW_COVERAGE:
            continue
        base = _close_on_or_before(bars, last_date - timedelta(days=days))
        if base:
            out[metric] = last_close / base - 1.0

    year_bars = [b for b in bars if (last_date - _date(b["date"])).days <= 366]
    if year_bars and (last_date - first_date).days >= 366 * WINDOW_COVERAGE:
        # True intraday highs when retained; close-only histories fall back.
        high = max(float(b.get("high") or b["close"]) for b in year_bars)
        if high > 0:
            out["pct_below_52w_high"] = max(0.0, 1.0 - last_close / high)

    closes = [float(b["close"]) for b in bars[-(VOL_TRADING_DAYS + 1):]]
    if len(closes) >= 30:
        rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))
                if closes[i - 1] > 0]
        if len(rets) >= 20:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            out["volatility_90d"] = math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR)

    recent = bars[-ADV_TRADING_DAYS:]
    volumes = [(float(b["close"]), float(b["volume"])) for b in recent
               if b.get("volume") not in (None, 0)]
    # A hard floor: a 2-bar history must never pose as a 3-month ADV that
    # liquidity screens then gate on.
    if len(volumes) >= 20:
        out["avg_volume_3m"] = sum(v for _, v in volumes) / len(volumes)
        out["avg_dollar_volume_3m"] = sum(c * v for c, v in volumes) / len(volumes)

    return out


def refresh_price_metrics(stores, tickers: list[str]) -> int:
    """Recompute and store market technicals for tickers with retained bars.
    Returns the number of tickers updated. Pure local read -> observation
    writes; safe to run after every price sync."""
    start = (_utc_today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    updated = 0
    for ticker in dict.fromkeys(t.upper() for t in tickers):
        ent = stores.identity.resolve_ticker(ticker)
        if not ent:
            continue
        bars = stores.bulk.price_range(ticker, start=start)
        metrics = compute_price_metrics(bars)
        if not metrics:
            continue
        period_end = str(bars[-1]["date"])[:10]
        for metric, value in metrics.items():
            oid = stores.financial.add_observation(
                ent["id"], metric, period_end, PERIOD_TYPE, float(value),
                is_calculated=True,
                lineage={"source": "price_history", "method": "price_metrics",
                         "bars": len(bars)},
                refresh_latest=False,
            )
            stores.financial.supersede_rolling(ent["id"], metric, PERIOD_TYPE, oid)
        stores.financial.refresh_latest(ent["id"])
        updated += 1
    if updated:
        log.info("price metrics refreshed for %d tickers", updated)
    return updated


def _date(value) -> datetime:
    return datetime.fromisoformat(str(value)[:10])


def _close_on_or_before(bars: list[dict], target: datetime) -> float | None:
    best = None
    for b in bars:
        if _date(b["date"]) <= target:
            best = float(b["close"])
        else:
            break
    return best


def _utc_today():
    return datetime.now(timezone.utc).date()
