"""Quality bench: run the funnel under a DIFFERENT strategy setting with the
real model provider, on a disposable copy of the workspace.

Usage:
  FUNDOPS_DB=/tmp/fundops-qualitybench/ws.db .venv/bin/python scripts/quality_bench.py deep_value
  ... then audit:  .venv/bin/python scripts/quality_audit.py /tmp/fundops-qualitybench/ws.db

Bounded: screener (deterministic) → thesis for the top N_THESIS picks →
IC review → memo for the top pick. Uses whatever provider the user's config
resolves (agent_cli/API) — quality cannot be judged on stubs.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

N_THESIS = 2

VARIANTS: dict[str, dict] = {
    "deep_value": {
        "summary": "Quality bench variant: deep value — statistically cheap cash generators",
        "north_star": "Buy statistically cheap businesses that gush free cash flow "
                      "relative to their price.",
        "style_blend": {"value": 0.8, "quality": 0.2},
        "narrative": None,
        "rules": [
            {"criterion_id": "screen.pe_max", "kind": "screen", "metric": "pe",
             "operator": "<=", "value": 14.0, "weight": None,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Cheapness gate", "interpretation": "P/E at or below 14"},
            {"criterion_id": "screen.fcf_yield_min", "kind": "screen", "metric": "fcf_yield",
             "operator": ">=", "value": 0.06, "weight": None,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Cash generation gate", "interpretation": "FCF yield at least 6%"},
            {"criterion_id": "screen.debt_equity_max", "kind": "screen", "metric": "debt_equity",
             "operator": "<=", "value": 1.5, "weight": None,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Leverage ceiling", "interpretation": "Debt/equity at or below 1.5x"},
            {"criterion_id": "rank.fcf_yield", "kind": "rank", "metric": "fcf_yield",
             "operator": ">", "value": 0.0, "weight": 0.6,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Prefer the cheapest cash flows",
             "interpretation": "Higher FCF yield ranks better"},
            {"criterion_id": "rank.earnings_yield", "kind": "rank", "metric": "earnings_yield",
             "operator": ">", "value": 0.0, "weight": 0.4,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Earnings cheapness", "interpretation": "Higher earnings yield ranks better"},
            {"criterion_id": "ic.expected_return_min", "kind": "ic_hurdle",
             "metric": "expected_return", "operator": ">=", "value": 10.0, "weight": None,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Value needs a margin of safety",
             "interpretation": "Expected return at least 10%"},
        ],
    },
    "defensive_quality": {
        "summary": "Quality bench variant: defensive quality — profitable, low-leverage compounders",
        "north_star": "Own consistently profitable, conservatively financed businesses "
                      "and avoid balance-sheet risk entirely.",
        "style_blend": {"quality": 0.7, "low_risk": 0.3},
        "narrative": None,
        "rules": [
            {"criterion_id": "screen.net_margin_min", "kind": "screen", "metric": "net_margin",
             "operator": ">=", "value": 0.10, "weight": None,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Profitability floor", "interpretation": "Net margin at least 10%"},
            {"criterion_id": "screen.roic_min", "kind": "screen", "metric": "roic",
             "operator": ">=", "value": 0.12, "weight": None,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Capital productivity floor", "interpretation": "ROIC at least 12%"},
            {"criterion_id": "screen.debt_equity_max", "kind": "screen", "metric": "debt_equity",
             "operator": "<=", "value": 0.8, "weight": None,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Conservative balance sheet", "interpretation": "Debt/equity at or below 0.8x"},
            {"criterion_id": "rank.roic", "kind": "rank", "metric": "roic",
             "operator": ">", "value": 0.0, "weight": 0.5,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Best compounders first", "interpretation": "Higher ROIC ranks better"},
            {"criterion_id": "rank.net_margin", "kind": "rank", "metric": "net_margin",
             "operator": ">", "value": 0.0, "weight": 0.5,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Margin durability", "interpretation": "Higher net margin ranks better"},
            {"criterion_id": "ic.expected_return_min", "kind": "ic_hurdle",
             "metric": "expected_return", "operator": ">=", "value": 6.0, "weight": None,
             "data_support_level": "fully", "rule_source": "bench",
             "rule_rationale": "Defensive return floor",
             "interpretation": "Expected return at least 6%"},
        ],
    },
}


async def main() -> None:
    variant = sys.argv[1] if len(sys.argv) > 1 else "deep_value"
    spec = VARIANTS[variant]

    from backend.core.ai import get_ai
    from backend.services import strategy_service
    from backend.stores import get_stores
    from backend.workflows import ic_review, memo, screener, thesis

    stores = get_stores()
    print(f"bench db ready · provider resolves to: {get_ai().provider}", flush=True)
    assert get_ai().provider != "stub", "bench needs a real provider — stub can't test quality"

    prop = stores.constitution.create_proposal(spec, validation=None,
                                               rationale="quality bench", chat_session_id=None)
    version = strategy_service.accept_proposal(stores, prop["id"])
    print(f"[{variant}] constitution v{version['version_number']} active", flush=True)

    rid = await screener.run_screener(stores, trigger="user")
    cur = screener.screener_current(stores)
    picks = [r["ticker"] for r in (cur.get("top_picks") or [])][:N_THESIS]
    print(f"[{variant}] screener {stores.runs.get_run(rid)['stats']} → thesis on {picks}", flush=True)
    if not picks:
        print(f"[{variant}] screener passed nothing — variant too strict for this universe")
        return

    await thesis.run_thesis(stores, trigger="user", tickers=picks)
    tcur = thesis.thesis_current(stores)
    rows = {r["ticker"]: r for r in tcur.get("rows") or []}
    for t in picks:
        r = rows.get(t, {})
        print(f"[{variant}] thesis {t}: exp={r.get('expected_return_pct')}% "
              f"fv={r.get('fair_value')} state={r.get('state')}", flush=True)

    await ic_review.run_ic(stores, trigger="user")
    icur = ic_review.ic_current(stores)
    judged = (icur.get("selection") or []) + (icur.get("remaining") or [])
    for r in judged:
        if r.get("ticker") in picks:
            print(f"[{variant}] ic {r['ticker']}: {r.get('verdict')} gate={r.get('gate_score')} "
                  f"hurdles={len(r.get('hurdle_findings') or [])}", flush=True)

    await memo.run_memo(stores, ticker=picks[0], provenance="directed")
    arts = stores.artifacts.recent(kind="investment_memo", limit=1)
    print(f"[{variant}] memo for {picks[0]}: artifact {arts[0]['id'] if arts else 'NONE'}", flush=True)
    print(f"[{variant}] DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
