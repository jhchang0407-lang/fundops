"""Chat analyst: a bounded tool-calling loop over retained local data.

Every iteration is one `complete_json` call returning a typed action — either
a tool call or the final answer. This keeps the loop provider-agnostic: the
OpenAI provider gets a few iterations, the agent CLI (slow subprocess per
call) gets fewer, and the offline stub plans exactly one tool
deterministically so the whole surface works with no model configured.

Tools are read-only (backend/chat/tools.py); each executed call is recorded
as Execution Provenance with kind="tool" under the chat session id, so a
conversation's data lookups are auditable like any workflow run.
"""

from __future__ import annotations

import json
import re

from backend.chat import archive_qa, tools
from backend.core.ai import get_ai

LOOP_BUDGET = {"openai": 4, "agent_cli": 2, "stub": 1}
MAX_BLOCKS = 4
MAX_CITATIONS = 8
MAX_ACTIONS = 4

_ACTION_SHAPE = (
    '{"action": "tool|final", "tool": "tool name when action=tool else null", '
    '"args": {"...": "tool arguments"}, '
    '"answer": "final answer in plain prose when action=final else null", '
    '"cited_steps": [1]}'
)
_SYSTEM_BASE = (
    "You are the FundOps data analyst. You answer questions about companies, "
    "metrics, prices, screens, ownership, the portfolio, and retained research "
    "using ONLY the tools below — never invent numbers; every figure in your "
    "answer must come from a tool result. Call one tool at a time. When you "
    "have enough, return action=final with a concise answer and cited_steps "
    "listing the step numbers you used. If data is missing, say so plainly. "
    "You can only read — you never change strategy, portfolio, or settings.\n\n"
    "Tools:\n"
)

# Deterministic stub planning: metric vocabulary for offline keyword matching.
_METRIC_WORDS = {
    "roic": "roic", "roe": "roe", "p/e": "pe", "pe ratio": "pe", "pe": "pe",
    "gross margin": "gross_margin", "operating margin": "operating_margin",
    "net margin": "net_margin", "fcf margin": "fcf_margin",
    "fcf yield": "fcf_yield", "free cash flow": "free_cash_flow",
    "revenue growth": "revenue_growth", "revenue": "revenue", "sales": "revenue",
    "eps": "eps", "net income": "net_income", "market cap": "market_cap",
    "1 month momentum": "momentum_1m", "1m momentum": "momentum_1m",
    "3 month momentum": "momentum_3m", "3m momentum": "momentum_3m",
    "6 month momentum": "momentum_6m", "6m momentum": "momentum_6m",
    "12 month momentum": "momentum_12m", "12m momentum": "momentum_12m",
    "momentum": "momentum_6m", "volatility": "volatility_90d",
    "dollar volume": "avg_dollar_volume_3m", "52 week high": "pct_below_52w_high",
    "52w high": "pct_below_52w_high",
    "debt": "debt_equity", "margin": "gross_margin",
}
_RULE_RE = re.compile(
    r"([a-z/ ]+?)\s*(?:is\s+)?(above|over|greater than|at least|>=|>|below|under|less than|at most|<=|<)\s*"
    r"(-?\d+(?:\.\d+)?)\s*(%|percent)?",
)
_LT_WORDS = ("below", "under", "less than", "at most", "<=", "<")


def _stub_metric(text: str) -> str | None:
    for word, metric in _METRIC_WORDS.items():
        if word in text:
            return metric
    return None


def _stub_rules(text: str) -> list[dict]:
    rules = []
    for m in _RULE_RE.finditer(text):
        metric = _stub_metric(m.group(1).strip())
        if not metric:
            continue
        value = float(m.group(3))
        if m.group(4):
            value = value / 100
        op = "<=" if m.group(2) in _LT_WORDS else ">="
        rules.append({"metric": metric, "operator": op, "value": value})
    return rules


def plan_stub(stores, message: str, context: dict | None) -> tuple[str, dict]:
    """Offline single-tool plan: keyword intent + ticker mentions. Mirrors
    `keyword_mode`'s role for classification (deterministic, test-stable)."""
    text = message.lower()
    known = set(stores.identity.all_tickers()) | set(stores.identity.known_tickers())
    mentioned, _ = archive_qa.ticker_mentions(message, known)
    comparing = "compare" in text or " vs " in text or "versus" in text
    ctx_ticker = str((context or {}).get("ticker") or "").upper()
    if ctx_ticker and ctx_ticker in known and ctx_ticker not in mentioned:
        if not mentioned:
            mentioned = [ctx_ticker]
        elif comparing or "this" in text.split():
            # "compare this with BBB" on the AAA page → AAA vs BBB
            mentioned = [ctx_ticker, *mentioned]

    # Reading an artifact: questions about "this report/memo/note" — or any
    # question with no other resolvable target — ground on the open document.
    ctx_artifact = str((context or {}).get("artifact_id") or "")
    if ctx_artifact and ("this" in text.split() or "report" in text or "memo" in text
                         or "note" in text or "document" in text or "passage" in text
                         or not mentioned):
        return "get_artifact", {"artifact_id": ctx_artifact}

    if "portfolio" in text or "holding" in text or "positions" in text:
        return "get_portfolio_summary", {}
    if "macro" in text or "fed funds" in text or "treasury" in text or "cpi" in text \
            or "unemployment" in text or "interest rate" in text:
        series = next((s for s in ("DGS10", "DFF", "UNRATE", "CPIAUCSL")
                       if s.lower() in text), None)
        return "get_macro", ({"series": series} if series else {})
    if "watchlist" in text or "theme" in text:
        named = next((w["name"] for w in stores.context.list_watchlists()
                      if w["name"].lower() in text), None)
        return "get_watchlist", ({"name": named} if named else {})
    if mentioned and ("peers" in text or "peer group" in text or "vs industry" in text):
        return "compare_companies", {"peers_of": mentioned[0]}
    if ("screen" in text or "which companies" in text or "find companies" in text):
        rules = _stub_rules(text)
        if rules:
            return "screen_universe", {"criteria": rules}
    if mentioned and ("thesis health" in text or "health break" in text
                      or "broke" in text or "broken" in text or "monitoring" in text
                      or "watch item" in text or ("health" in text and "thesis" in text)):
        return "get_thesis_health", {"ticker": mentioned[0]}
    if mentioned and ("price" in text or "chart" in text):
        rng = next((r for r in ("1m", "6m", "5y", "1y") if r in text), "1y")
        return "get_price_history", {"ticker": mentioned[0], "range": rng}
    if len(mentioned) >= 2 and comparing:
        metric_ids = []
        for word, metric in _METRIC_WORDS.items():
            if word in text and metric not in metric_ids:
                metric_ids.append(metric)
        args: dict = {"tickers": mentioned}
        if metric_ids:
            args["metrics"] = metric_ids
        return "compare_companies", args
    if mentioned and ("insider" in text or "ownership" in text or "holders" in text or "who owns" in text):
        return "get_ownership", {"ticker": mentioned[0]}
    if mentioned:
        metric = _stub_metric(text)
        if metric:
            return "get_metric", {"ticker": mentioned[0], "metric": metric}
        return "get_company_financials", {"ticker": mentioned[0]}
    return "search_archive", {"query": message}


def _stub_final(steps: list[dict]) -> str:
    good = [s for s in steps if not s["error"]]
    if not good:
        reason = steps[-1]["error"] if steps else "no data available"
        return (f"I couldn't answer that from local data: {reason}. "
                "Data arrives with syncs and research runs.")
    return "Here's what the retained local data shows:\n\n" + "\n\n".join(
        s["summary"] for s in good
    )


def _system_prompt(stores, context: dict | None, budget: int) -> str:
    prompt = _SYSTEM_BASE + tools.catalog_text()
    prompt += f"\n\nYou have at most {budget} tool call(s) for this question."
    if context and context.get("page"):
        where = context["page"]
        if context.get("ticker"):
            where += f" page for {str(context['ticker']).upper()}"
        prompt += (f"\nThe user is currently viewing the {where} — resolve "
                   "references like 'this company' against it.")
        if context.get("artifact_id"):
            aid = str(context["artifact_id"])
            art = stores.artifacts.get(aid)
            if art:
                title = ((art.get("payload") or {}).get("body") or {}).get("title") \
                    or art.get("ticker") or art["kind"]
                prompt += (
                    f"\nSpecifically, they are reading retained artifact {aid} "
                    f"({art['kind']}: “{title}”). For questions about 'this "
                    f"report/document' or its subject matter, call "
                    f"get_artifact(artifact_id=\"{aid}\") FIRST and answer from "
                    "its content.")
    from backend.chat.strategy_chat import preference_text  # lazy: avoids cycle
    prefs = preference_text(stores)
    if prefs:
        prompt += "\n" + prefs
    return prompt


def _user_prompt(message: str, history: list[dict], steps: list[dict]) -> str:
    recent = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-6:])
    lines = [f"Recent conversation (most recent last):\n{recent or '(none)'}",
             f'Question: """{message}"""']
    if steps:
        transcript = "\n".join(
            f"Step {s['n']} — {s['tool']}({json.dumps(s['args'], default=str)[:200]}): "
            + (f"ERROR: {s['error']}" if s["error"] else s["summary"][:800])
            for s in steps
        )
        lines.append(f"Tool results so far:\n{transcript}")
        lines.append("Decide the next action: another tool call if something is "
                     "missing, else action=final with the answer.")
    else:
        lines.append("Decide the first action.")
    return "\n\n".join(lines)


async def answer(stores, session_id: str, message: str, history: list[dict],
                 context: dict | None = None) -> dict:
    """Data-question entry point: {reply, citations, actions, blocks}."""
    provider = get_ai().provider
    budget = LOOP_BUDGET.get(provider, 2)
    system = _system_prompt(stores, context, budget)
    steps: list[dict] = []
    final_answer: str | None = None
    cited: list[int] = []

    for _round in range(budget + 1):
        if provider == "stub":
            if not steps:
                tool_name, args = plan_stub(stores, message, context)
                stub_action: dict = {"action": "tool", "tool": tool_name, "args": args}
            else:
                stub_action = {"action": "final", "answer": _stub_final(steps),
                               "cited_steps": [s["n"] for s in steps if not s["error"]]}
        else:
            stub_action = {"action": "final", "answer": _stub_final(steps),
                           "cited_steps": [s["n"] for s in steps if not s["error"]]}

        result = await get_ai().complete_json(
            "chat_analyst", system, _user_prompt(message, history, steps),
            _ACTION_SHAPE, tier="fast", run_id=session_id, stub=stub_action,
        )
        if not isinstance(result, dict):
            break
        if result.get("action") == "tool" and len(steps) < budget:
            name = str(result.get("tool") or "")
            args = result.get("args") if isinstance(result.get("args"), dict) else {}
            tr = tools.execute(stores, name, args)
            stores.ops.record_provenance(
                step=f"chat_tool:{name}", kind="tool", run_id=session_id,
                inputs_ref=json.dumps(args, default=str)[:500],
                validation={"ok": tr["error"] is None,
                            **({"error": tr["error"]} if tr["error"] else {})},
            )
            steps.append({"n": len(steps) + 1, "tool": name, "args": args,
                          "summary": tr["summary"], "error": tr["error"],
                          "block": tr["block"], "citations": tr["citations"]})
            continue
        final_answer = result.get("answer") if isinstance(result.get("answer"), str) else None
        cited = [i for i in (result.get("cited_steps") or [])
                 if isinstance(i, int) and 1 <= i <= len(steps)]
        break

    if not final_answer:
        final_answer = _stub_final(steps)
    good_steps = [s for s in steps if not s["error"]]
    used = [steps[i - 1] for i in cited if not steps[i - 1]["error"]] or good_steps

    blocks = [s["block"] for s in used if s["block"]][:MAX_BLOCKS]
    citations: list[dict] = []
    seen = set()
    for s in used:
        for c in s["citations"]:
            key = (c.get("artifact_id"), c.get("ticker"), c.get("kind"), c.get("label"))
            if key not in seen and len(citations) < MAX_CITATIONS:
                seen.add(key)
                citations.append(c)
    actions: list[dict] = []
    for c in citations:
        t = c.get("ticker")
        if t and len(actions) < MAX_ACTIONS and \
                not any(a.get("ticker") == t for a in actions):
            actions.append({"type": "open_company", "ticker": t,
                            "label": f"Open {t} company page"})

    return {"reply": final_answer, "citations": citations,
            "actions": actions, "blocks": blocks}
