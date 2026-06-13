"""Market technicals from stored daily bars — pure math + ingestion behavior.

Pins: momentum windows, 52w-high distance, volatility annualization, dollar
volume; short histories omit uncoverable windows; refresh writes catalog
observations that supersede their prior rolling snapshot and surface through
latest_financials (so screener and chat can gate on them).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.domain import metric_catalog
from backend.services.ingest.price_metrics import (
    compute_price_metrics,
    refresh_price_metrics,
)


def _bars(days: int, start_price: float = 100.0, daily_gain: float = 0.0,
          volume: float = 1_000_000, end: date | None = None,
          ticker: str | None = None) -> list[dict]:
    """Synthetic ascending daily bars ending today (weekends included — the
    math only cares about dates and closes)."""
    end = end or date(2026, 6, 12)
    out = []
    price = start_price
    for d in range(days, 0, -1):
        row = {"date": (end - timedelta(days=d)).isoformat(),
               "close": round(price, 6), "volume": volume}
        if ticker:
            row["ticker"] = ticker
        out.append(row)
        price *= 1 + daily_gain
    return out


def test_momentum_windows_and_52w_high():
    # Flat for a year then +1%/day for the last 30 days.
    flat = _bars(400, 100.0, 0.0)[: 400 - 30]
    rising = _bars(30, 100.0, 0.01)
    bars = flat + rising
    m = compute_price_metrics(bars)
    assert m["momentum_1m"] == pytest.approx(rising[-1]["close"] / 100.0 - 1, rel=1e-6)
    assert m["momentum_12m"] == pytest.approx(rising[-1]["close"] / 100.0 - 1, rel=1e-6)
    # Last close IS the 52w high -> 0% below it.
    assert m["pct_below_52w_high"] == pytest.approx(0.0, abs=1e-9)
    assert m["avg_volume_3m"] == pytest.approx(1_000_000)


def test_drawdown_from_high_is_positive_when_below():
    bars = _bars(400, 200.0, -0.001)  # steady decline: last close below the high
    m = compute_price_metrics(bars)
    assert m["pct_below_52w_high"] > 0.05
    assert m["momentum_6m"] < 0


def test_constant_series_has_zero_volatility():
    m = compute_price_metrics(_bars(400, 50.0, 0.0))
    assert m["volatility_90d"] == pytest.approx(0.0, abs=1e-12)


def test_dollar_volume():
    m = compute_price_metrics(_bars(400, 10.0, 0.0, volume=2_000_000))
    assert m["avg_dollar_volume_3m"] == pytest.approx(20_000_000)


def test_short_history_omits_long_windows():
    m = compute_price_metrics(_bars(45, 100.0, 0.002))
    assert "momentum_1m" in m
    assert "momentum_12m" not in m
    assert "pct_below_52w_high" not in m


def test_new_metrics_are_catalog_and_hard_gate_supported():
    for metric in ("momentum_1m", "momentum_3m", "momentum_6m", "momentum_12m",
                   "pct_below_52w_high", "volatility_90d",
                   "avg_dollar_volume_3m", "avg_volume_3m"):
        assert metric_catalog.is_supported(metric), metric
        assert metric_catalog.supports_hard_gate(metric), metric


def test_refresh_writes_observations_and_supersedes_rolling(stores):
    stores.identity.ensure_entity("AAA", name="Alpha Corp", sector="Technology")
    stores.bulk.upsert_prices(_bars(400, 100.0, 0.001, end=date(2026, 6, 11), ticker="AAA"))

    assert refresh_price_metrics(stores, ["AAA"]) == 1
    ent = stores.identity.resolve_ticker("AAA")
    latest = stores.financial.latest(ent["id"])
    assert latest["momentum_3m"] > 0
    assert "avg_dollar_volume_3m" in latest

    # Next-day refresh supersedes the prior rolling snapshot instead of
    # accumulating one live row per day.
    stores.bulk.upsert_prices(_bars(401, 100.0, 0.001, end=date(2026, 6, 12), ticker="AAA"))
    assert refresh_price_metrics(stores, ["AAA"]) == 1
    live = stores.ws.query(
        "SELECT COUNT(*) AS n FROM financial_observations "
        "WHERE entity_id = ? AND metric = 'momentum_3m' AND superseded_by IS NULL",
        (ent["id"],),
    )
    assert live[0]["n"] == 1


def test_momentum_question_routes_to_data_mode():
    from backend.chat.service import keyword_mode

    assert keyword_mode("What is AAA's 6 month momentum?", False) == "data_question"
    assert keyword_mode("show BBB volatility", False) == "data_question"
    assert keyword_mode("what's my strategy?", False) == "strategy_status"


def test_screener_can_gate_on_momentum(stores):
    from backend.domain.criteria import Criterion, evaluate

    stores.identity.ensure_entity("BBB", name="Beta", sector="Industrials")
    stores.bulk.upsert_prices(_bars(400, 50.0, 0.002, end=date(2026, 6, 11), ticker="BBB"))
    refresh_price_metrics(stores, ["BBB"])
    ent = stores.identity.resolve_ticker("BBB")
    observed = stores.financial.latest(ent["id"]).get("momentum_6m")
    crit = Criterion("screen.momentum_6m_min", "screen", "trend filter", "test",
                     metric="momentum_6m", operator=">=", value=0.05)
    assert evaluate(crit, observed).satisfied is True
