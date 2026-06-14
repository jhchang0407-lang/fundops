"""Archive Q&A: read-only answers grounded in retained workspace history.

Deterministic retrieval over structured records (artifacts, screener history,
IC verdicts, portfolio ledger, learning records) builds a compact context
packet; one fast model call composes the answer with citations back into the
provided records. Never mutates anything (ADR catalogue: archive answers are
cited, not regenerated truth).
"""

from __future__ import annotations

import re

from backend.core.ai import get_ai

_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
# Uppercase tokens that are finance/English vocabulary, not ticker mentions.
_NOT_TICKERS = frozenset({
    "I", "A", "OK", "AI", "IC", "PE", "PB", "PS", "EV", "ROIC", "ROE", "ROA",
    "FCF", "SBC", "CEO", "CFO", "ETF", "IPO", "USA", "US", "EPS", "TTM", "YOY",
    "FY", "SEC", "NYSE", "GAAP", "CAGR", "COGS", "EBIT", "DCF", "EBITDA", "PEG",
    "THE", "WHAT", "WHY", "HOW", "AND", "OR", "NOT", "DID", "DO", "WE", "MY",
})
_CONTEXT_CHAR_CAP = 3000
_ANSWER_SHAPE = (
    '{"answer": "grounded answer referencing record numbers like [1]", '
    '"cited": [1, 2]}'
)
_SYSTEM = (
    "You are FundOps Archive Q&A. Answer ONLY from the numbered retained records "
    "provided — they are the workspace's history. Cite records by their numbers. "
    "If the records do not answer the question, say so plainly; never invent "
    "history and never suggest changing anything."
)


def ticker_mentions(message: str, known: set[str]) -> tuple[list[str], list[str]]:
    """Ticker tokens in a message, split into (known, unknown). Shared with
    the chat analyst tools."""
    tokens = [t for t in dict.fromkeys(_TICKER_RE.findall(message)) if t not in _NOT_TICKERS]
    mentioned = [t for t in tokens if t in known]
    unknown = [t for t in tokens if t not in known and len(t) >= 2]
    return mentioned, unknown


def gather_records(stores, tickers: list[str]) -> list[dict]:
    """Candidate records: {artifact_id?, ticker?, kind, label, date, detail}."""
    records: list[dict] = []

    def add(kind: str, label: str, date: str | None, ticker: str | None = None,
            artifact_id: str | None = None, detail: str = "") -> None:
        records.append({
            "artifact_id": artifact_id, "ticker": ticker, "kind": kind,
            "label": label, "date": (date or "")[:10], "detail": detail,
        })

    if tickers:
        for t in tickers:
            for a in stores.artifacts.for_ticker(t, limit=10):
                add(a["kind"], f"{a['kind'].replace('_', ' ')} for {t}",
                    a["created_at"], ticker=t, artifact_id=a["id"])
            for s in stores.artifacts.screener_history_for_ticker(t, limit=5):
                outcome = "passed" if s["passed"] else "failed"
                rank = f", rank {s['rank']}" if s.get("rank") is not None else ""
                add("screener_result", f"screener run: {t} {outcome}{rank}",
                    s.get("run_started_at"), ticker=t,
                    artifact_id=s.get("snapshot_artifact_id"),
                    detail=f"{outcome}{rank}")
            v = stores.artifacts.latest_ic_verdict(t)
            if v:
                add("ic_verdict", f"IC verdict for {t}: {v['verdict']}",
                    v["created_at"], ticker=t, artifact_id=v.get("artifact_id"),
                    detail=f"gate score {v.get('gate_score')}")
            for lot in stores.portfolio.lots(ticker=t):
                add("portfolio_event",
                    f"bought {lot['shares']} {t} @ {lot['cost_basis']}",
                    lot["purchase_date"], ticker=t)
            for sale in stores.portfolio.sales(ticker=t):
                add("portfolio_event",
                    f"sold {sale['shares']} {t} @ {sale['price']} "
                    f"(realized P&L {sale.get('realized_pnl')})",
                    sale["sale_date"], ticker=t)
            for rec in stores.learning.records(ticker=t, limit=5):
                add("learning_record", f"{rec['kind']} for {t}", rec["created_at"],
                    ticker=t)
    else:
        for a in stores.artifacts.recent(limit=12):
            add(a["kind"],
                f"{a['kind'].replace('_', ' ')}" + (f" for {a['ticker']}" if a["ticker"] else ""),
                a["created_at"], ticker=a.get("ticker"), artifact_id=a["id"])
    return records


def _context_packet(records: list[dict]) -> str:
    lines = []
    for i, r in enumerate(records, start=1):
        line = f"[{i}] {r['date']} {r['kind']}: {r['label']}"
        if r["detail"]:
            line += f" ({r['detail']})"
        lines.append(line)
        if sum(len(x) + 1 for x in lines) > _CONTEXT_CHAR_CAP:
            lines.append("... (older records truncated)")
            break
    return "\n".join(lines)


def _stub_answer(records: list[dict], tickers: list[str]) -> dict:
    scope = f" for {', '.join(tickers)}" if tickers else ""
    head = f"Here is the retained FundOps history{scope}:"
    cited = list(range(1, min(len(records), 6) + 1))
    body = "\n".join(
        f"- [{i}] {records[i - 1]['date']} — {records[i - 1]['label']}" for i in cited
    )
    return {"answer": f"{head}\n{body}", "cited": cited}


async def answer(stores, session_id: str, message: str) -> dict:
    """Read-only archive answer: {reply, citations, actions}."""
    known = set(stores.identity.known_tickers())
    mentioned, unknown = ticker_mentions(message, known)

    if not mentioned and unknown:
        names = ", ".join(unknown)
        return {
            "reply": (
                f"There's no retained FundOps history for {names} — it hasn't appeared "
                "in any screener run, research artifact, or portfolio record in this "
                "workspace. If you want coverage, run research on it explicitly from "
                "the workflow pages."
            ),
            "citations": [], "actions": [],
        }

    records = gather_records(stores, mentioned)
    if not records:
        return {
            "reply": (
                "The archive has no retained records matching that yet. Once screener "
                "runs, theses, IC verdicts, memos, or portfolio entries exist, I can "
                "answer from them with citations."
            ),
            "citations": [], "actions": [],
        }

    result = await get_ai().complete_json(
        "archive_answer", _SYSTEM,
        f"Question: {message}\n\nRetained records:\n{_context_packet(records)}",
        _ANSWER_SHAPE, tier="fast", stub=_stub_answer(records, mentioned),
    )
    if not isinstance(result, dict) or not result.get("answer"):
        result = _stub_answer(records, mentioned)

    cited_idx = []
    for i in result.get("cited") or []:
        if isinstance(i, int) and 1 <= i <= len(records) and i not in cited_idx:
            cited_idx.append(i)
    if not cited_idx:
        cited_idx = list(range(1, min(len(records), 6) + 1))

    citations = [
        {
            "artifact_id": records[i - 1]["artifact_id"],
            "ticker": records[i - 1]["ticker"],
            "kind": records[i - 1]["kind"],
            "label": f"{records[i - 1]['label']} ({records[i - 1]['date']})",
        }
        for i in cited_idx
    ]
    actions: list[dict] = []
    seen_artifacts: set[str] = set()
    for c in citations:
        aid = c["artifact_id"]
        if aid and aid not in seen_artifacts and len(seen_artifacts) < 5:
            seen_artifacts.add(aid)
            actions.append({"type": "open_artifact", "id": aid, "label": f"Open {c['label']}"})
    for t in mentioned:
        actions.append({"type": "open_company", "ticker": t, "label": f"Open {t} company page"})

    return {"reply": result["answer"], "citations": citations, "actions": actions}
