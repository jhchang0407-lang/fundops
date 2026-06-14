"""Shared company evidence packets for AI generation (ADR-0013, ADR-0021, ADR-0022).

Thesis, IC Review, and Memo all write from the same deterministic,
information-dense packet built from retained platform data: latest financials,
multi-period observation history with computed trends, price context,
same-sector peers, ownership records, and a criterion-by-criterion check
against the ACTIVE constitution — which is what keeps generation
strategy-aware for any constitution, not just hard-coded quality screens.

Everything in this module is deterministic: packets are equally the grounding
for real model calls and for offline stub prose, so offline output cites the
same trends, peer positions, and constitution outcomes a strong model would.
Workflow artifacts (thesis / IC verdicts / memos) never feed back into
packets: provenance stays provenance (ADR-0013).
"""

from __future__ import annotations

from backend.core.metric_schema import METRIC_SCHEMA
from backend.domain.criteria import Criterion, evaluate
from backend.services import company_factsheet as cf

# Metrics whose history grounds trend analysis (when retained).
KEY_HISTORY_METRICS = cf.KEY_HISTORY_METRICS
ANNUAL_PERIODS = cf.ANNUAL_PERIODS
QUARTERLY_PERIODS = cf.QUARTERLY_PERIODS
PEER_LIMIT = 5

# Decimal-stored metrics whose schema type is float but whose natural display
# is a percentage (schema notes: "0.05 = 5%").
_DECIMAL_AS_PCT = {"fcf_yield", "earnings_yield", "implied_growth", "growth_gap"}
_MULTIPLES = {"pe", "pb", "ps", "ev_ebitda", "ev_fcf", "pfcf", "peg", "ptangible_book"}
_LARGE_VALUES = {"revenue", "market_cap", "free_cash_flow", "net_income", "ebitda",
                 "net_debt", "owner_earnings", "maintenance_capex", "growth_capex"}

# Latest-financials display order for prompt text (information-dense, bounded).
_PROMPT_METRICS = (
    "revenue", "revenue_growth", "gross_margin", "operating_margin", "net_margin",
    "fcf_margin", "fcf_yield", "earnings_yield", "eps", "roic", "roe",
    "debt_equity", "interest_coverage", "pe", "pb", "ev_ebitda", "dividend_yield",
)


# --- formatting -----------------------------------------------------------------------

def display_name(metric_id: str) -> str:
    d = METRIC_SCHEMA.get(metric_id)
    return d.display_name if d else metric_id.replace("_", " ")


def fmt_money(v: float) -> str:
    a = abs(v)
    for div, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{v / div:,.1f}{suffix}"
    return f"{v:,.0f}"


def fmt_value(metric_id: str, value) -> str:
    """Human-sensible rendering of one metric value (46.0%, 22.0x, 50.0B...)."""
    if not isinstance(value, (int, float)):
        return "n/a"
    d = METRIC_SCHEMA.get(metric_id)
    if (d and d.data_type == "percent") or metric_id in _DECIMAL_AS_PCT:
        return f"{value * 100:.1f}%"
    if metric_id in _MULTIPLES:
        return f"{value:.1f}x"
    if metric_id in _LARGE_VALUES or abs(value) >= 1e7:
        return fmt_money(value)
    return f"{value:,.2f}"


# --- packet builder --------------------------------------------------------------------

def build_company_packet(stores, ticker: str, entity_id: str | None = None) -> dict:
    """One shared company evidence packet (see module docstring)."""
    ticker = ticker.upper()
    sheet = cf.build_company_fact_sheet(
        stores, ticker, profile="memo", entity_id=entity_id, ensure=True,
    )
    ent = sheet["identity"]
    entity_id = sheet["identity"]["entity_id"]
    latest = sheet["latest"]
    notes = list(sheet["data_quality_notes"])
    if not latest:
        notes.append("no retained latest financials for this entity")

    history = sheet["history"]
    trends = sheet["trends"]
    n_annual = max((len(s.get("annual") or []) for s in history.values()), default=0)
    if n_annual < 2:
        notes.append(f"annual history limited to {n_annual} period(s); "
                     "multi-year trend analysis unavailable")
    if not any(s.get("quarterly") for s in history.values()):
        notes.append("no quarterly observations retained")

    price_context = sheet["price_context"]
    if price_context.get("high_52w") is None:
        notes.append("no retained daily price history (52-week range unavailable)")

    peers = _build_peers(stores, ent.get("sector"), entity_id)
    if not peers:
        notes.append("no same-sector peers with retained financials")

    ownership = _build_ownership(stores, ticker)
    if not ownership["largest_holders"]:
        notes.append("no beneficial ownership records retained")

    constitution_check = _build_constitution_check(stores, latest)

    return {
        "identity": {"ticker": ticker, "name": ent.get("name") or ticker,
                     "sector": ent.get("sector"), "industry": ent.get("industry")},
        "latest": latest,
        "history": history,
        "trends": trends,
        "price_context": price_context,
        "peers": peers,
        "ownership": ownership,
        "constitution_check": constitution_check,
        "data_quality_notes": list(dict.fromkeys(notes)),
        "source_metadata": sheet["source_metadata"],
        "source_drilldowns": sheet["source_drilldowns"],
    }


def enriched_snapshot(stores, entity_id: str, price: float | None,
                      latest: dict | None = None) -> dict:
    """Latest financials with price-dependent + growth metrics filled in.

    Price-dependent metrics (market_cap, pe, fcf_yield) and revenue_growth are
    deliberately NOT stored — they change with price or need multi-period
    context — so any read surface (Company Page snapshot, chat) must derive
    them at read time the same way the thesis packet does (ADR-0017)."""
    return cf.enriched_snapshot(stores, entity_id, price, latest)


def _build_history(stores, entity_id: str) -> dict:
    """Per-metric observation series, newest first: up to 5 annual + 8 quarterly."""
    return cf.build_history(stores, entity_id)


def _build_trends(history: dict) -> dict:
    """Deterministic trend computations from the retained history."""
    return cf.build_trends(history)


def _cagr(series: list[dict]) -> float | None:
    """CAGR in % over a newest-first series; needs 2+ positive endpoints."""
    return cf._cagr(series)


def _trajectory(series: list[dict]) -> dict | None:
    """Margin trajectory over a newest-first annual series, in bps."""
    return cf._trajectory(series)


def _build_price_context(stores, ticker: str, latest: dict) -> dict:
    return cf.build_price_context(stores, ticker, latest)


def _enrich_valuation_metrics(latest: dict, price: float | None,
                              trends: dict, notes: list[str]) -> None:
    """Fill in price-dependent and growth metrics in-place when missing, from
    data the packet already has. Decimals for yields (0.05 = 5%), matching
    to_flat_metrics. Only fills gaps — never overwrites a stored value."""
    cf.enrich_valuation_metrics(latest, price, trends, notes)


def _build_peers(stores, sector: str | None, entity_id: str) -> list[dict]:
    """Same-sector entities with retained latest financials (comparison rows)."""
    if not sector:
        return []
    rows = stores.ws.query(
        "SELECT e.id AS entity_id, a.ticker FROM investment_entities e "
        "JOIN ticker_aliases a ON a.entity_id = e.id AND a.valid_to IS NULL "
        "WHERE e.sector = ? AND e.id != ? ORDER BY a.ticker LIMIT 25",
        (sector, entity_id),
    )
    peers = []
    for r in rows:
        m = stores.financial.latest(r["entity_id"])
        if not m:
            continue
        peers.append({"ticker": r["ticker"], "roic": m.get("roic"),
                      "gross_margin": m.get("gross_margin"),
                      "revenue_growth": m.get("revenue_growth"), "pe": m.get("pe")})
        if len(peers) >= PEER_LIMIT:
            break
    return peers


def _build_ownership(stores, ticker: str) -> dict:
    holders: list[dict] = []
    try:  # lazy + guarded: ingest services are an optional parallel module
        from backend.services.ingest.beneficial import largest_holders
        holders = largest_holders(stores, ticker, top=3)
    except Exception:  # noqa: BLE001 — ownership is enrichment, never a blocker
        holders = []
    insider = len(stores.bulk.ownership_for(ticker, kind="insider_transaction", limit=100))
    return {"largest_holders": holders, "insider_transactions_recent": insider}


def _build_constitution_check(stores, latest: dict) -> dict:
    """Evaluate every measurable screen/rank/ic_hurdle criterion of the ACTIVE
    constitution against the latest financials. satisfied None = not
    measurable from financials (e.g. thesis-level metrics) — never a fail."""
    active = stores.constitution.active_version()
    if not active:
        return {"north_star": None, "rows": [], "research_review": [],
                "measured_all_pass": True}
    rows: list[dict] = []
    research_review: list[dict] = []
    for d in active.get("criteria") or []:
        c = Criterion.from_dict(d)
        if c.kind == "research_review":
            research_review.append({"criterion_id": c.criterion_id,
                                    "rule": c.interpretation or c.rule_rationale})
            continue
        if c.kind not in ("screen", "rank", "ic_hurdle") or not c.metric or not c.operator:
            continue
        r = evaluate(c, latest.get(c.metric))
        rows.append({
            "criterion_id": c.criterion_id, "kind": c.kind, "metric": c.metric,
            "rule": f"{display_name(c.metric)} {c.operator} {_fmt_threshold(c.metric, c.value)}",
            "observed": r.observed,
            "observed_display": fmt_value(c.metric, r.observed),
            "satisfied": r.satisfied,
            "interpretation": c.interpretation,
        })
    return {
        "north_star": active.get("north_star"),
        "rows": rows,
        "research_review": research_review,
        "measured_all_pass": all(r["satisfied"] is not False for r in rows),
    }


def _fmt_threshold(metric: str, value) -> str:
    if isinstance(value, (int, float)):
        return fmt_value(metric, value)
    return str(value)


# --- deterministic valuation -------------------------------------------------------------

def deterministic_anchors(latest: dict, price: float | None) -> dict:
    """Deterministic fair-value anchors: growth-adjusted justified PE on EPS,
    falling back to FCF-yield-plus-growth against an 8% required yield. This
    is the arithmetic the model (or the stub) must ground its valuation on."""
    eps = latest.get("eps")
    growth = latest.get("revenue_growth") or 0.0
    fcf_yield = latest.get("fcf_yield")
    fair_value = method = None
    if isinstance(eps, (int, float)) and eps > 0:
        justified_pe = max(8.0, min(35.0, 10.0 + max(growth, 0.0) * 100.0 * 0.8))
        fair_value = eps * justified_pe
        method = (f"growth-adjusted PE: justified PE {justified_pe:.1f}x on "
                  f"EPS {eps:.2f}")
    elif isinstance(fcf_yield, (int, float)) and fcf_yield > 0 and price:
        fair_value = price * (fcf_yield + max(growth, 0.0)) / 0.08
        method = "FCF-yield-plus-growth vs 8% required yield"
    upside = downside = None
    if fair_value and price:
        upside = (fair_value - price) / price * 100.0
        downside = (fair_value * 0.75 - price) / price * 100.0
    return {
        "fair_value_base": round(fair_value, 2) if fair_value else None,
        "method": method,
        "upside_pct": round(upside, 1) if upside is not None else None,
        "downside_pct": round(downside, 1) if downside is not None else None,
    }


def valuation_scenarios(anchors: dict, latest: dict, price: float | None) -> dict | None:
    """Deterministic bear/base/bull scenario table around the base anchor.
    Bear: 25% multiple/margin compression; bull: 20% re-rating on execution."""
    fv = anchors.get("fair_value_base")
    if not isinstance(fv, (int, float)) or not price:
        return None
    growth_pct = (latest.get("revenue_growth") or 0.0) * 100.0
    rows = []
    for name, mult, assumption in (
        ("bear", 0.75, f"growth fades toward {growth_pct / 2:.1f}% and the multiple "
                       "compresses 25% vs base"),
        ("base", 1.00, anchors.get("method") or "deterministic base anchor"),
        ("bull", 1.20, f"{growth_pct:.1f}% growth sustains and execution earns a "
                       "20% re-rating vs base"),
    ):
        scenario_fv = fv * mult
        rows.append([name, assumption, round(scenario_fv, 2),
                     round((scenario_fv - price) / price * 100.0, 1)])
    return {"columns": ["scenario", "assumption", "fair_value", "return_vs_price_pct"],
            "rows": rows}


# --- packet readers (shared by prompts and stubs) -----------------------------------------

def peer_rank(packet: dict, metric: str) -> tuple[int, int] | None:
    """(peers beaten, peers compared) for one metric; None when incomparable."""
    mine = (packet.get("latest") or {}).get(metric)
    values = [p.get(metric) for p in packet.get("peers") or []
              if isinstance(p.get(metric), (int, float))]
    if not isinstance(mine, (int, float)) or not values:
        return None
    return sum(1 for v in values if mine > v), len(values)


def trend_phrase(packet: dict, metric: str) -> str:
    """One deterministic phrase describing a metric's level and trajectory."""
    latest = fmt_value(metric, (packet.get("latest") or {}).get(metric))
    traj = (packet.get("trends") or {}).get(f"{metric}_trajectory")
    name = display_name(metric).lower()
    if traj:
        if traj["direction"] == "stable":
            return (f"{name} held within ±50bps over {traj['periods']} retained "
                    f"years at {latest}")
        verb = "expanded" if traj["direction"] == "expanding" else "contracted"
        return (f"{name} {verb} {traj['change_bps']:+d}bps over "
                f"{traj['periods']} retained years to {latest}")
    return f"{name} stands at {latest} in the latest retained period"


def as_prompt_text(packet: dict) -> str:
    """Tight, readable text block (~1500-2500 chars) for prompt inclusion."""
    ident = packet["identity"]
    latest = packet["latest"]
    pc = packet["price_context"]
    lines = []
    sector_line = " / ".join(x for x in (ident.get("sector"), ident.get("industry")) if x)
    lines.append(f"COMPANY: {ident['name']} ({ident['ticker']})"
                 + (f" — {sector_line}" if sector_line else ""))

    price_bits = [f"price {pc['price']:,.2f}" if isinstance(pc.get("price"), (int, float))
                  else "price n/a"]
    if pc.get("high_52w") is not None:
        off = pc.get("pct_off_52w_high")
        price_bits.append(f"52w range {pc['low_52w']:,.2f}-{pc['high_52w']:,.2f}"
                          + (f" ({off:+.1f}% vs high)" if off is not None else ""))
    if isinstance(pc.get("market_cap"), (int, float)):
        price_bits.append(f"market cap {fmt_money(pc['market_cap'])}")
    lines.append("PRICE CONTEXT: " + "; ".join(price_bits))

    shown = [f"{display_name(m)} {fmt_value(m, latest[m])}"
             for m in _PROMPT_METRICS if latest.get(m) is not None]
    lines.append("LATEST FINANCIALS: " + (" | ".join(shown) if shown else "none retained"))

    hist_lines = []
    for metric, series in packet["history"].items():
        annual = series.get("annual") or []
        if len(annual) >= 2:
            path = " <- ".join(f"{fmt_value(metric, p['value'])} ({p['period_end'][:7]})"
                               for p in annual)
            hist_lines.append(f"  {display_name(metric)}: {path}")
    if hist_lines:
        lines.append("ANNUAL HISTORY (newest first):")
        lines.extend(hist_lines)

    trends = packet["trends"]
    trend_bits = []
    if trends.get("revenue_cagr_pct") is not None:
        trend_bits.append(f"revenue CAGR {trends['revenue_cagr_pct']}% over "
                          f"{trends['revenue_cagr_years']}y")
    for metric in ("gross_margin", "operating_margin", "net_margin"):
        traj = trends.get(f"{metric}_trajectory")
        if traj:
            trend_bits.append(f"{display_name(metric).lower()} {traj['direction']} "
                              f"{traj['change_bps']:+d}bps over {traj['periods']}y")
    if trends.get("latest_quarter_revenue_yoy_pct") is not None:
        trend_bits.append(f"latest quarter revenue YoY "
                          f"{trends['latest_quarter_revenue_yoy_pct']:+.1f}%")
    if trend_bits:
        lines.append("TRENDS: " + "; ".join(trend_bits))

    if packet["peers"]:
        lines.append(f"PEERS ({ident.get('sector')}, retained financials):")
        for p in packet["peers"]:
            lines.append(
                f"  {p['ticker']}: ROIC {fmt_value('roic', p.get('roic'))}, "
                f"GM {fmt_value('gross_margin', p.get('gross_margin'))}, "
                f"growth {fmt_value('revenue_growth', p.get('revenue_growth'))}, "
                f"PE {fmt_value('pe', p.get('pe'))}")

    own = packet["ownership"]
    if own["largest_holders"] or own["insider_transactions_recent"]:
        holders = ", ".join(
            f"{h['owner_name']}"
            + (f" ({h['percent']:.1f}%)" if isinstance(h.get("percent"), (int, float)) else "")
            for h in own["largest_holders"])
        lines.append("OWNERSHIP: "
                     + (f"largest holders {holders}; " if holders else "")
                     + f"{own['insider_transactions_recent']} recent insider transactions")

    cc = packet["constitution_check"]
    if cc["rows"]:
        lines.append(f"CONSTITUTION CHECK (north star: {cc.get('north_star') or 'n/a'}):")
        for r in cc["rows"]:
            tag = {True: "PASS", False: "MISS", None: "UNEVALUABLE"}[r["satisfied"]]
            obs = (f"observed {r['observed_display']}" if r["satisfied"] is not None
                   else "not measurable from retained financials")
            lines.append(f"  [{tag}] {r['rule']} — {obs}")

    if packet["data_quality_notes"]:
        lines.append("DATA GAPS: " + "; ".join(packet["data_quality_notes"]))
    return "\n".join(lines)
