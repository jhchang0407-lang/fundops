"""Bounded research runs over filing text and peer groups (Phase 4 harness).

Company-level:
- risk_diff: deterministic paragraph diff of the two latest 10-K Risk Factors
  sections, then one fast model call to name the themes. The diff itself is
  computed locally — the model only summarizes what provably changed.
- mdna_note: one deep call over the latest MD&A; every claim cites the
  numbered source section.

Group-level (Research Hub):
- industry_note: deterministic metrics grid (research_hub aggregates) + the
  freshest cached risk/MD&A excerpts per constituent -> one deep call ->
  cited industry note.
- risk_landscape: risk-factor excerpts across the group -> one deep call ->
  shared/divergent worry themes.

Every run produces an append-only artifact (filing_note / industry_note)
carrying its numbered sources; offline (stub) runs produce deterministic
notes from the same inputs so the workflow shape is explorable without keys.
"""

from __future__ import annotations

import asyncio
import re

from backend.core import web_research
from backend.core.ai import get_ai
from backend.core.workspace import now_iso
from backend.services import research_hub
from backend.services.ingest import filing_text

RUN_KINDS = {"industry_note", "risk_landscape", "peer_deep_dive"}
COMPANY_RUN_KINDS = {"risk_diff", "mdna_note"}
GROUP_TICKER_CAP = 8
EXCERPT_CHARS = 2_500
DIFF_PARA_CAP = 40

# Thematic deep research (SEC-only, bounded): discover a company set for a
# free-text theme, deep-read each one's 10-K Business/Risk/MD&A, synthesize a
# cited market report. Every claim traces to a filing excerpt.
THEME_COMPANY_CAP = 10
THEME_CONCURRENCY = 4
THEME_SECTIONS = ("business", "risk_factors", "mdna")
THEME_SECTION_CHARS = 4_000
_PROFILE_SHAPE = (
    '{"what_they_do": "1-2 sentences", "theme_relevance": "how they relate to the theme", '
    '"positioning": "market position/moat grounded in the filing", '
    '"key_risks": ["risk", "risk"], "cited": [1]}'
)
_REPORT_SHAPE = (
    '{"title": "report title", "body_md": "markdown report with ## sections; '
    'cite filings like [1]", "cited": [1]}'
)

_NOTE_SHAPE = (
    '{"title": "short note title", '
    '"body_md": "markdown note; cite sources like [1]", "cited": [1]}'
)


def resolve_scope(stores, sector: str | None, industry: str | None,
                  watchlist_id: str | None, tickers: list[str]) -> tuple[list[str], int]:
    """A research run's ticker scope from any one group selector. Returns
    (tickers, group_total). When the group exceeds the per-run cap, the
    LARGEST constituents by market cap are kept — never an alphabetical
    accident — and callers record the truncation in the artifact."""
    if tickers:
        out = [t.upper() for t in tickers]
    elif watchlist_id:
        wl = stores.context.get_watchlist(watchlist_id)
        if not wl:
            raise ValueError("unknown watchlist/theme")
        out = list(wl["tickers"])
    elif sector or industry:
        out = [e["ticker"] for e in
               stores.identity.entities_in_group(sector=sector, industry=industry)]
    else:
        raise ValueError("provide tickers, a watchlist_id, or a sector/industry")
    if not out:
        raise ValueError("the selected group has no tickers")
    total = len(out)
    if total > GROUP_TICKER_CAP:
        def _cap(t: str) -> float:
            ent = stores.identity.resolve_ticker(t)
            return stores.financial.latest(ent["id"]).get("market_cap") or 0.0 if ent else 0.0
        out = sorted(out, key=_cap, reverse=True)[:GROUP_TICKER_CAP]
    return out, total


# --- deterministic risk-factor diff --------------------------------------------------

def _paragraphs(text: str) -> list[str]:
    paras = [re.sub(r"\s+", " ", p).strip() for p in text.split("\n\n")]
    return [p for p in paras if len(p) > 120][:400]


def _norm(p: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", p.lower())[:240]


def diff_paragraphs(new_text: str, old_text: str) -> dict:
    """Paragraphs present in one filing but not the other (normalized match)."""
    new_paras, old_paras = _paragraphs(new_text), _paragraphs(old_text)
    old_keys = {_norm(p) for p in old_paras}
    new_keys = {_norm(p) for p in new_paras}
    added = [p for p in new_paras if _norm(p) not in old_keys][:DIFF_PARA_CAP]
    removed = [p for p in old_paras if _norm(p) not in new_keys][:DIFF_PARA_CAP]
    return {"added": added, "removed": removed,
            "new_total": len(new_paras), "old_total": len(old_paras)}


def _source_line(i: int, s: dict, what: str) -> str:
    return f"[{i}] {s.get('form') or 'filing'} filed {str(s.get('filed_at'))[:10]} — {what}"


async def run_company_note(stores, ticker: str, kind: str) -> dict:
    """risk_diff | mdna_note for one ticker -> filing_note artifact."""
    ticker = ticker.upper()
    if kind not in COMPANY_RUN_KINDS:
        raise ValueError(f"kind must be one of {sorted(COMPANY_RUN_KINDS)}")
    ent = stores.identity.resolve_ticker(ticker)

    if kind == "risk_diff":
        sections = await filing_text.sections_for_ticker(stores, ticker, "risk_factors", count=2)
        if len(sections) < 2:
            return {"ok": False, "error": (
                f"need two 10-K risk-factor sections for {ticker}; "
                f"{len(sections)} available (filing text downloads on demand — "
                "check connectivity or that two annual reports exist)")}
        new_s, old_s = sections[0], sections[1]
        diff = diff_paragraphs(new_s["content"], old_s["content"])
        sources = [_source_line(1, new_s, "current risk factors"),
                   _source_line(2, old_s, "prior-year risk factors")]
        excerpt = "\n\nADDED PARAGRAPHS (in [1], not [2]):\n" + "\n---\n".join(
            p[:600] for p in diff["added"][:12])
        excerpt += "\n\nREMOVED PARAGRAPHS (in [2], not [1]):\n" + "\n---\n".join(
            p[:600] for p in diff["removed"][:12])
        stub = {
            "title": f"{ticker} risk factors: {len(diff['added'])} added, "
                     f"{len(diff['removed'])} removed",
            "body_md": (
                f"Year-over-year risk-factor diff for {ticker} [1][2]:\n\n"
                f"- {len(diff['added'])} paragraphs added (of {diff['new_total']})\n"
                f"- {len(diff['removed'])} paragraphs removed (of {diff['old_total']})\n\n"
                + ("First added: " + diff["added"][0][:300] + "… [1]\n" if diff["added"] else "")
                + ("First removed: " + diff["removed"][0][:300] + "… [2]" if diff["removed"] else "")
            ),
            "cited": [1, 2],
        }
        prompt_body = excerpt
        system = (
            "You are the FundOps filing analyst. Summarize what CHANGED in this "
            "company's stated risk factors year over year, grouped into themes. "
            "Use ONLY the provided added/removed paragraphs; cite [1] for current, "
            "[2] for prior. Note what management started and stopped worrying about.")
        payload_extra = {"diff_counts": {"added": len(diff["added"]),
                                         "removed": len(diff["removed"])}}
    else:  # mdna_note
        sections = await filing_text.sections_for_ticker(stores, ticker, "mdna", count=1)
        if not sections:
            return {"ok": False, "error": (
                f"no MD&A section available for {ticker} yet (filing text "
                "downloads on demand)")}
        s = sections[0]
        sources = [_source_line(1, s, "MD&A")]
        prompt_body = s["content"][:24_000]
        stub = {
            "title": f"{ticker} MD&A note ({str(s.get('filed_at'))[:10]})",
            "body_md": (f"MD&A summary for {ticker} from [1] "
                        f"({len(s['content']):,} chars retained). Offline mode: "
                        "configure an AI provider for a synthesized note; the full "
                        "section text is cached locally for reading."),
            "cited": [1],
        }
        system = (
            "You are the FundOps filing analyst. Summarize this MD&A: results "
            "drivers, margin commentary, liquidity, guidance-adjacent statements, "
            "and notable language changes. Every claim cites [1]. Quote sparingly.")
        payload_extra = {}

    result = await get_ai().complete_json(
        f"research_{kind}", system,
        f"Company: {ticker} ({(ent or {}).get('name') or ticker})\n"
        f"Sources:\n" + "\n".join(sources) + "\n\n" + prompt_body,
        _NOTE_SHAPE, tier="deep", stub=stub,
    )
    if not isinstance(result, dict) or not result.get("body_md"):
        result = stub
    payload = {
        "kind": "filing_note",
        "schema_version": "1.0",
        "generated_at": now_iso(),
        "ticker": ticker,
        "body": {"title": result.get("title") or f"{ticker} {kind}",
                 "kind": kind, "sources": sources, **payload_extra},
    }
    artifact_id = stores.artifacts.save_artifact(
        "filing_note", payload, ticker=ticker,
        entity_id=(ent or {}).get("id"), rendered_md=result["body_md"],
    )
    return {"ok": True, "artifact_id": artifact_id, "title": payload["body"]["title"]}


async def run(stores, kind: str, tickers: list[str], group_label: str,
              group_total: int | None = None) -> dict:
    """industry_note | risk_landscape over a peer group -> industry_note artifact."""
    if kind not in RUN_KINDS:
        raise ValueError(f"kind must be one of {sorted(RUN_KINDS)}")
    entities = []
    for t in tickers:
        ent = stores.identity.resolve_ticker(t)
        if ent:
            entities.append({**ent, "ticker": t})
    dashboard = research_hub.group_dashboard(stores, entities, group_label)
    truncated = group_total is not None and group_total > len(tickers)
    scope_note = (f"Scope: the {len(tickers)} largest of {group_total} constituents "
                  f"by market cap." if truncated else None)

    metric_lines = []
    for c in dashboard["constituents"]:
        bits = [f"{m}={c.get(m)}" for m in ("market_cap", "roic", "gross_margin",
                                            "revenue_growth", "momentum_6m")
                if c.get(m) is not None]
        metric_lines.append(f"{c['ticker']} ({c['name']}): " + (", ".join(bits) or "no data"))

    sources, excerpts = [], []
    n = 0
    for t in tickers:
        section = "risk_factors" if kind == "risk_landscape" else "mdna"
        rows = await filing_text.sections_for_ticker(stores, t, section, count=1,
                                               allow_fetch=(len(tickers) <= 4))
        if not rows:
            continue
        n += 1
        sources.append(_source_line(n, rows[0], f"{t} {section.replace('_', ' ')}"))
        excerpts.append(f"[{n}] {t}:\n{rows[0]['content'][:EXCERPT_CHARS]}")

    stub = {
        "title": f"{group_label}: {kind.replace('_', ' ')} ({len(entities)} companies)",
        "body_md": (
            f"## {group_label}\n\n"
            + (f"{scope_note}\n\n" if scope_note else "")
            + f"Deterministic group snapshot ({dashboard['with_data']} of "
            f"{dashboard['size']} with data):\n\n"
            + "\n".join(f"- {line}" for line in metric_lines[:10])
            + (f"\n\nFiling excerpts retained for {n} companies "
               f"({', '.join(s.split(' ')[0] for s in sources)})." if n else
               "\n\nNo filing text cached yet — sections download on demand "
               "when connectivity allows.")
        ),
        "cited": list(range(1, n + 1)),
    }
    if kind == "peer_deep_dive":
        system = (
            "You are the FundOps peer analyst. Compare these specific companies "
            "head to head: business model differences, who earns the best unit "
            "economics and why (use the metrics grid), relative momentum and "
            "valuation, and what each filing emphasizes that the others don't. "
            "Cite filing excerpts by number. No buy/sell language. Write metric "
            "names in plain English (Gross Margin, Market Cap) — never raw "
            "identifiers like gross_margin.")
    else:
        system = (
            "You are the FundOps industry analyst. Write a concise industry note: "
            "structure, who earns the best economics and why (use the metrics grid), "
            "common strategic language, and — for risk_landscape — the shared and "
            "divergent stated risks. Only use the provided data; cite filing excerpts "
            "by their numbers. No buy/sell language. Write metric names in plain "
            "English (Gross Margin, Market Cap) — never raw identifiers like "
            "gross_margin.")
    result = await get_ai().complete_json(
        f"research_{kind}", system,
        f"Group: {group_label} ({len(entities)} companies)\n\n"
        f"Metrics grid:\n" + "\n".join(metric_lines)
        + "\n\nSources:\n" + ("\n".join(sources) or "(no filing text cached)")
        + "\n\n" + "\n\n".join(excerpts),
        _NOTE_SHAPE, tier="deep", stub=stub,
    )
    if not isinstance(result, dict) or not result.get("body_md"):
        result = stub
    payload = {
        "kind": "industry_note",
        "schema_version": "1.0",
        "generated_at": now_iso(),
        "body": {"title": result.get("title") or f"{group_label} {kind}",
                 "kind": kind, "group": group_label,
                 "tickers": [e["ticker"] for e in entities],
                 "scope": {"used": len(tickers),
                           "of": group_total if group_total is not None else len(tickers),
                           "note": scope_note},
                 "sources": sources,
                 "aggregates": dashboard["aggregates"]},
    }
    rendered = result["body_md"]
    if scope_note and scope_note not in rendered:
        rendered = f"{scope_note}\n\n{rendered}"
    artifact_id = stores.artifacts.save_artifact(
        "industry_note", payload, rendered_md=rendered,
    )
    return {"ok": True, "artifact_id": artifact_id,
            "title": payload["body"]["title"], "tickers": payload["body"]["tickers"]}


# --- thematic deep research -------------------------------------------------------

_EXPAND_SHAPE = '{"queries": ["short phrase", "short phrase"]}'


async def _expand_theme(query: str) -> list[str]:
    """The theme phrased the way filings phrase it: 'drone market' misses the
    majors who write 'unmanned aircraft systems'. One fast call; offline stub
    degrades to the original query only."""
    result = await get_ai().complete_json(
        "research_theme_expand",
        "You expand an investment research theme into EDGAR full-text search "
        "phrases. Return 2-3 SHORT alternative phrasings that public companies "
        "actually use in 10-K filings (industry jargon, formal product terms) — "
        "synonyms only, never the original phrase.",
        f"Theme: {query}",
        _EXPAND_SHAPE, tier="fast", stub={"queries": []},
    )
    extras = [str(q).strip() for q in (result or {}).get("queries") or [] if str(q).strip()]
    return [query, *extras][:3]


async def discover_theme_companies(stores, query: str, limit: int) -> tuple[list[dict], int]:
    """EDGAR full-text discovery → distinct companies, INCLUDING ones outside
    the configured universe (thematic research looks at the market, not just
    the screening universe — EFTS hits carry a CIK, which is enough to read
    their filings). Searches the theme plus filing-language synonyms so majors
    that never write the colloquial phrase still surface. Locally-known
    companies sort first. Returns (selected, distinct_discovered)."""
    from backend.services import fulltext_search

    hits: list[dict] = []
    for q in await _expand_theme(query):
        search = await fulltext_search.search_filings(stores, q)
        hits.extend(search.get("hits") or [])
    seen: set[str] = set()
    cands: list[dict] = []
    for h in hits:
        t = (h.get("ticker") or "").upper()
        key = t or str(h.get("cik") or "")
        if not key or key in seen:
            continue
        ent = stores.identity.resolve_ticker(t) if t else None
        if not ent and not h.get("cik"):
            continue  # nothing to read it by
        seen.add(key)
        cands.append({
            "ticker": t or f"CIK{h.get('cik')}",
            "entity_id": ent["id"] if ent else None,
            "cik": str(h.get("cik") or "") or (ent or {}).get("cik"),
            "name": h.get("company") or (ent or {}).get("name") or t,
            "in_universe": bool(h.get("in_universe")),
            "has_fin": bool(ent and stores.financial.latest(ent["id"])),
        })
    cands.sort(key=lambda c: (c["has_fin"], c["in_universe"]), reverse=True)
    return cands[:limit], len(seen)


async def _theme_filing_row(stores, c: dict) -> dict | None:
    """The newest 10-K (10-Q fallback) row for a company: the retained filings
    index when we have it, else EDGAR submissions by CIK (off-universe path)."""
    for forms in (["10-K", "10-K/A"], ["10-Q"]):
        if c.get("entity_id"):
            rows = stores.bulk.filings_for(c["ticker"], forms=forms, limit=1)
            if rows and rows[0].get("accession"):
                return rows[0]
        if c.get("cik"):
            try:
                rows = await asyncio.to_thread(
                    filing_text.latest_filings_by_cik, c["cik"], tuple(forms), 1)
            except Exception:
                rows = []
            if rows:
                rows[0].setdefault("ticker", c["ticker"])
                return rows[0]
    return None


async def _company_profile(stores, c: dict, query: str) -> dict:
    """Read one company's latest 10-K — Business, Risk Factors, MD&A from a
    single document fetch — and extract a theme-relevant profile. Source
    indices are local (renumbered globally by the caller)."""
    excerpts, local_sources, idx = [], [], 0
    filing = await _theme_filing_row(stores, c)
    if filing:
        sections = await filing_text.fetch_and_cache_sections(stores, filing)
        for section in THEME_SECTIONS:
            content = sections.get(section)
            if not content:
                continue
            idx += 1
            local_sources.append(_source_line(
                idx, filing, f"{c['ticker']} {section.replace('_', ' ')}"))
            excerpts.append(f"[{idx}] {c['ticker']} {section}:\n{content[:THEME_SECTION_CHARS]}")

    latest = stores.financial.latest(c["entity_id"]) if c.get("entity_id") else {}
    latest = latest or {}
    snapshot = {m: latest.get(m) for m in
                ("market_cap", "revenue", "revenue_growth", "gross_margin",
                 "operating_margin", "roic", "fcf_yield")
                if latest.get(m) is not None}

    stub = {"what_they_do": c["name"],
            "theme_relevance": f"surfaced by EDGAR full-text for '{query}'",
            "positioning": "see filing excerpts", "key_risks": [],
            "cited": list(range(1, idx + 1))}
    if excerpts:
        profile = await get_ai().complete_json(
            "research_theme_profile",
            "You are a financial analyst. From this company's 10-K excerpts, extract a "
            f"concise profile relevant to the theme '{query}': what the business does, how "
            "it relates to the theme, its competitive positioning, and its key stated "
            "risks. Cite excerpts by [number]. Facts only — no buy/sell language.",
            f"Company {c['ticker']} ({c['name']}). Theme: {query}\n\nFilings:\n"
            + "\n\n".join(excerpts),
            _PROFILE_SHAPE, tier="fast", stub=stub,
        )
        if not isinstance(profile, dict):
            profile = stub
    else:
        profile = stub
    return {"ticker": c["ticker"], "name": c["name"], "snapshot": snapshot,
            "profile": profile, "local_sources": local_sources, "read": bool(excerpts)}


async def run_thematic(stores, query: str, limit: int = THEME_COMPANY_CAP) -> dict:
    """Theme → discover companies (EDGAR full-text) → deep-read each one's 10-K
    Business/Risk/MD&A → synthesize a cited market report (industry_note artifact,
    body.kind='thematic_report'). SEC filings only, bounded."""
    query = (query or "").strip()
    if not query:
        raise ValueError("query is required")
    selected, discovered = await discover_theme_companies(stores, query, limit)
    if not selected:
        return {"ok": False, "discovered": discovered,
                "note": (f"No companies with retained identity matched “{query}”. EDGAR "
                         "full-text surfaced filings, but none resolve to a company FundOps "
                         "can deep-read — try a broader theme or sync more of the universe.")}

    sem = asyncio.Semaphore(THEME_CONCURRENCY)

    async def one(c):
        async with sem:
            return await _company_profile(stores, c, query)

    profiles = await asyncio.gather(*(one(c) for c in selected))

    # Renumber every company's local citations into one global sequence.
    all_sources: list[str] = []
    blocks: list[str] = []
    n = 0
    for p in profiles:
        loc = p["profile"]
        bits = [f"### {p['ticker']} — {p['name']}"]
        snap = ", ".join(f"{k}={v}" for k, v in p["snapshot"].items())
        if snap:
            bits.append(f"Financials: {snap}")
        bits.append(f"What: {loc.get('what_they_do')}")
        bits.append(f"Theme relevance: {loc.get('theme_relevance')}")
        bits.append(f"Positioning: {loc.get('positioning')}")
        risks = loc.get("key_risks") or []
        if risks:
            bits.append("Risks: " + "; ".join(str(r) for r in risks[:4]))
        blocks.append("\n".join(bits))
        for s in p["local_sources"]:
            n += 1
            all_sources.append(re.sub(r"^\[\d+\]", f"[{n}]", s))

    # Theme-level web augmentation (Settings toggle): market sizing and recent
    # developments live outside filings. [Wn] sources stay distinct from the
    # filing citation sequence.
    web = await web_research.search(f"{query} market size growth competitors outlook", 5)
    web_block, web_sources = (web_research.context_block(web["results"])
                              if web["results"] else ("", []))

    read_n = sum(1 for p in profiles if p["read"])
    coverage = (f"Scope: deep-read {read_n} of {len(selected)} companies "
                f"(discovered {discovered} via EDGAR full-text)."
                + (" SEC filings + bounded web context — filings carry every figure;"
                   " web claims cite [Wn]." if web_block else
                   " SEC filings only — every claim cites a filing."))
    stub_report = {
        "title": f"{query.title()}: thematic research ({len(profiles)} companies)",
        "body_md": f"## {query.title()} — thematic landscape\n\n{coverage}\n\n"
                   + "\n\n".join(blocks),
        "cited": list(range(1, n + 1)),
    }
    system = (
        "You are the FundOps thematic research analyst. Using the company profiles "
        "and financials below (sourced from SEC filings) plus any recent web context, "
        "write a business/market research report on the theme. Structure with ## "
        "sections: Market landscape & structure; Key players & positioning; Competitive "
        "dynamics & economics (reason from the financials); Demand drivers & catalysts; "
        "Shared & divergent risks; Coverage gaps & what's missing. Filings are the only "
        "source of figures — cite them by [number]; web context is supplementary and any "
        "web-derived claim must cite [Wn]. No speculation beyond sources, no buy/sell "
        "advice. Write metric names in plain English — never raw ids like gross_margin.")
    result = await get_ai().complete_json(
        "research_thematic", system,
        f"Theme: {query}\n\n{coverage}\n\nCompany profiles:\n\n" + "\n\n".join(blocks)
        + (f"\n\nRecent web context (supplementary):\n{web_block}" if web_block else "")
        + "\n\nSources:\n" + "\n".join(all_sources + web_sources),
        _REPORT_SHAPE, tier="deep", stub=stub_report, max_output_tokens=6000,
    )
    if not isinstance(result, dict) or not result.get("body_md"):
        result = stub_report
    rendered = result["body_md"]
    if coverage not in rendered:
        rendered = f"{coverage}\n\n{rendered}"
    payload = {
        "kind": "industry_note",
        "schema_version": "1.0",
        "generated_at": now_iso(),
        "body": {"title": result.get("title") or f"{query} thematic research",
                 "kind": "thematic_report", "theme": query,
                 "tickers": [p["ticker"] for p in profiles],
                 "scope": {"deep_read": read_n, "selected": len(selected),
                           "discovered": discovered},
                 "sources": all_sources + web_sources},
    }
    artifact_id = stores.artifacts.save_artifact("industry_note", payload, rendered_md=rendered)
    return {"ok": True, "artifact_id": artifact_id, "title": payload["body"]["title"],
            "tickers": payload["body"]["tickers"], "scope": payload["body"]["scope"]}
