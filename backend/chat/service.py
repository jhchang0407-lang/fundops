"""FundOps Chat service: one entry point, mode-routed behavior.

A single fast classification call decides what each message is (strategy
change, exploration, status, archive question, approval, rejection,
cancellation, other). Approval language only ever activates the Current
Pending Draft, and only when that draft was shown in this chat session —
after a restart the draft is re-shown and confirmed again, never silently
activated (CONTEXT: Live Strategy Chat Session, evals 3/4/6).
"""

from __future__ import annotations

import re

from backend.chat import analyst, archive_qa, product_guide, strategy_chat
from backend.core.ai import get_ai
from backend.domain import labels
from backend.services import strategy_service

MODES = (
    "strategy_change", "strategy_exploration", "strategy_status",
    "archive_question", "data_question", "product_question", "action_request",
    "approval", "rejection", "cancellation", "other",
)
# Internal classification -> contract response mode.
_CONTRACT_MODE = {
    "strategy_change": "strategy",
    "approval": "strategy",
    "rejection": "strategy",
    "cancellation": "strategy",
    "strategy_exploration": "exploration",
    "strategy_status": "status",
    "archive_question": "archive",
    "data_question": "data",
    "product_question": "guide",
    "action_request": "action",
    "other": "status",
}

BLOCK_ROW_CAP = 50  # table rows persisted per block in message refs

_APPROVAL_PHRASES = (
    "yes", "ok", "okay", "approve", "approved", "go ahead", "sounds good",
    "looks good", "do it", "confirm", "confirmed", "ship it", "yep", "yeah",
    "sure", "lgtm", "yes please", "approve it", "save it",
)
_CANCEL_PHRASES = (
    "never mind", "nevermind", "cancel", "don't save", "do not save",
    "forget it", "discard", "scrap that", "drop it",
)
_REJECT_PHRASES = (
    "not what i meant", "that's not right", "that is not right",
    "that is not what", "thats not what", "not right", "wrong",
    "but not", "don't like", "do not like", "instead",
)
_STATUS_PHRASES = (
    "what is my", "what's my", "whats my", "my current", "current strategy",
    "my strategy", "my constitution", "why is", "why did you set",
    "what are my", "current requirement",
)
_EXPLORE_PHRASES = (
    "wondering", "should i care", "should we care", "thinking about",
    "what would happen", "curious", "pros and cons", "tradeoff", "trade-off",
    "is it worth", "worth caring",
)
_ARCHIVE_PHRASES = (
    "research", "memo", "thesis", "verdict", "screener", "history", "archive",
    "what did", "have we", "did we", "do we have", "do we know", "know about",
    "last time", "when did", "what do we", "ever looked",
)
_CHANGE_PHRASES = (
    "i want", "change", "strategy", "invest", "focus on", "screen for",
    "require", "prefer", "add a rule", "set my", "tighten", "loosen",
    "care about", "look for",
)
_DATA_PHRASES = (
    "price", "chart", "compare", "holding", "portfolio", "market cap",
    "revenue", "margin", "p/e", "pe ratio", "eps", "roic", "roe", "fcf",
    "free cash flow", "valuation", "metric", "insider", "ownership",
    "financials", "growth", "momentum", "volatility", "volume",
    "52 week", "52w", "peers", "macro", "treasury", "fed funds", "cpi",
    "unemployment", "watchlist",
)
# Retrospective phrasing keeps archive questions in archive mode even when
# they mention metrics ("what did the memo say about margins?").
_RETRO_PHRASES = (
    "what did", "have we", "did we", "last time", "when did", "ever looked",
    "what do we know", "memo", "thesis", "verdict",
)
# Strategy nouns keep "what is my ROIC requirement?" in status mode even
# though it names a metric.
_STRATEGY_NOUNS = (
    "strategy", "constitution", "requirement", "rule", "hurdle", "threshold",
    "wired", "wiring",
)
# Action requests: "run thesis on TSLA", "start the pipeline", "generate a
# memo for KO" — the verb must PRECEDE the workflow noun so retrospective
# questions ("what did the screener run show") stay in archive mode.
_ACTION_VERBS = ("run", "launch", "start", "kick off", "generate", "rerun", "re-run")
_ACTION_TARGETS = {
    "pipeline": "pipeline", "screener": "screener", "screen": "screener",
    "thesis": "thesis", "memo": "memo", "ic review": "ic_review",
}


def _action_intent(msg: str) -> str | None:
    """The requested workflow capability, when the message is an imperative
    action request (verb before target); else None."""
    for verb in _ACTION_VERBS:
        vi = msg.find(verb)
        if vi < 0:
            continue
        for word, cap in _ACTION_TARGETS.items():
            ti = msg.find(word)
            if ti > vi:
                return cap
    return None


# Product questions: how-the-app-works phrasing + a feature noun → the guide.
_PRODUCT_PREFIXES = (
    "how does", "how do i", "how can i", "what is the", "what is a", "what is",
    "what does", "what are the", "where do", "where can i", "where does",
    "explain the", "explain how", "why can't i", "can i",
)
_PRODUCT_NOUNS = (
    "ic review", "screener", "pipeline", "memo", "thesis health", "briefing",
    "inbox", "runs page", "markets page", "library", "constitution",
    "thematic", "monitoring plan", "watch item", "provider", "web search",
    "fundops", "this app", "the app", "provenance", "artifact", "stage",
    "gate score", "data quality", "evidence packet", "sync",
)

_CLASSIFY_SHAPE = (
    '{"mode": "strategy_change|strategy_exploration|strategy_status|'
    'archive_question|data_question|product_question|action_request|approval|'
    'rejection|cancellation|other"}'
)
_CLASSIFY_SYSTEM = (
    "You route FundOps Chat messages. Classify the NEW user message into exactly "
    "one mode. approval/rejection/cancellation refer to the Current Pending Draft "
    "shown in conversation; archive_question asks about past research, artifacts, "
    "tickers, or portfolio history (read-only); data_question asks for current "
    "numbers from local data — financials, metrics, prices, comparisons, ad-hoc "
    "screens ('right now', not a strategy change), holdings, ownership, and "
    "thesis-health / monitoring status ('why did KO's thesis health break', "
    "'what's breaking on X' — current monitoring records, NOT archived research); "
    "product_question asks how FundOps itself works — its features, pages, "
    "stages, data sources ('how does IC review decide', 'what is thesis "
    "health', 'where do memos come from'); action_request asks to START a "
    "workflow ('run thesis on TSLA', 'start the pipeline', 'generate a memo "
    "for KO'); "
    "strategy_status reads the current strategy; strategy_exploration weighs an "
    "idea without committing; strategy_change states or changes investing intent."
)


_TICKERISH = re.compile(r"\b[A-Z]{1,5}\b")
_NOT_TICKERS = {"I", "A", "AI", "IC", "OK", "RUN", "THE", "ON", "FOR", "CAN",
                "YOU", "PLEASE", "NOW", "MEMO", "FULL"}


def _handle_action_request(stores, message: str, context: dict | None) -> dict:
    """Chat never writes silently — it offers the run as a click-to-confirm
    action chip, says exactly what will happen, and is honest about provider
    state instead of falling back to the generic menu."""
    from backend.core.ai import get_ai

    msg = message.lower()
    cap = _action_intent(msg) or "pipeline"

    known = set(stores.identity.all_tickers()) | set(stores.identity.known_tickers())
    mentioned, _ = archive_qa.ticker_mentions(message, known)
    ticker = mentioned[0] if mentioned else None
    if not ticker:
        # Directed research can fetch fundamentals for NEW tickers too — accept
        # an uppercase symbol even when it isn't retained yet.
        cands = [t for t in _TICKERISH.findall(message) if t not in _NOT_TICKERS]
        ticker = cands[0] if cands else None
    if not ticker and (context or {}).get("ticker"):
        ticker = str(context["ticker"]).upper()

    lines: list[str] = []
    actions: list[dict] = []
    if cap in ("thesis", "memo") and ticker:
        what = ("a Completed Thesis (return decomposition anchored on deterministic "
                "valuation)" if cap == "thesis"
                else "a full seven-section investment memo with a monitoring plan")
        lines.append(
            f"I can start a directed {cap} run for {ticker} — it fetches "
            f"{ticker}'s fundamentals if needed and produces {what}, recorded "
            "as a durable run. Click to confirm:")
        actions.append({"type": "run_directed", "capability": cap, "ticker": ticker,
                        "label": f"Start directed {cap} on {ticker}"})
    elif cap in ("thesis", "memo"):
        lines.append(
            f"A {cap} run needs a target: name a ticker ('run {cap} on NVDA') or "
            "run the full pipeline and the screener will pick the candidates.")
        actions.append({"type": "run_workflow", "kind": "pipeline",
                        "label": "Run the full pipeline"})
    elif cap == "screener":
        lines.append("I can run the screener over your universe against the "
                     "Constitution's requirements — deterministic, no model. "
                     "Click to confirm:")
        actions.append({"type": "run_workflow", "kind": "screener",
                        "label": "Run the screener"})
    elif cap == "ic_review":
        lines.append("IC review judges the current thesis selections — run it from "
                     "the IC page once theses are selected, or run the full "
                     "pipeline to do every stage in order.")
        actions.append({"type": "run_workflow", "kind": "pipeline",
                        "label": "Run the full pipeline"})
    else:  # pipeline
        lines.append("I can run the full pipeline — screener → thesis → IC review "
                     "→ memo, each stage recorded as a durable run. Click to confirm:")
        actions.append({"type": "run_workflow", "kind": "pipeline",
                        "label": "Run the full pipeline"})

    if get_ai().provider == "stub":
        lines.append(
            "Heads up: no AI provider is connected right now (offline stub mode), "
            "so model-written stages will produce deterministic placeholders. "
            "Connect one in Settings → AI provider & models.")
    return {"reply": "\n\n".join(lines), "actions": actions}


def keyword_mode(message: str, pending_exists: bool) -> str:
    """Deterministic fallback classifier (offline stub)."""
    msg = message.strip().lower()
    bare = msg.rstrip(".!?, ")
    plain_assent = " but " not in f" {bare} " and " not " not in f" {bare} "
    if bare in _APPROVAL_PHRASES or (
        len(bare) <= 24 and plain_assent
        and any(bare.startswith(p) for p in _APPROVAL_PHRASES)
    ):
        return "approval"
    if any(p in msg for p in _CANCEL_PHRASES):
        return "cancellation"
    if pending_exists and (bare.startswith("no") or any(p in msg for p in _REJECT_PHRASES)):
        return "rejection"
    interrogative = "?" in msg or bare.startswith(
        ("what", "why", "how", "show", "tell me", "explain")
    )
    # Data questions outrank status/archive/change, but retrospective phrasing
    # ("what did we..."), strategy nouns ("my ROIC requirement"), and strategy
    # intent ("i want...") stay where they were.
    # Action requests beat question routing: "can you run thesis on TSLA" is
    # a request to DO something, not a question about anything.
    if _action_intent(msg):
        return "action_request"
    # Product questions — "how does IC review work", "what is thesis health",
    # "where do memos come from" — are about FundOps itself, answered from the
    # curated guide. Phrasing prefixes deliberately exclude "why did/why is"
    # so ticker-status questions ("why did KO's thesis health break") still
    # reach the monitoring records below.
    if any(bare.startswith(p) for p in _PRODUCT_PREFIXES) \
            and any(n in msg for n in _PRODUCT_NOUNS) \
            and not any(p in msg for p in _STATUS_PHRASES):
        return "product_question"
    # Thesis-health / monitoring is a CURRENT-status question answered from
    # monitoring records (get_thesis_health), not the artifact archive — even
    # though it's phrased retrospectively ("why did KO's thesis health break")
    # and contains "thesis". This rule must beat the retro/archive logic below.
    if interrogative and ("thesis health" in msg or "health break" in msg
                          or "health broke" in msg
                          or ("health" in msg and any(
                              w in msg for w in ("broke", "broken", "break",
                                                 "watch", "monitor")))):
        return "data_question"
    data_intent = interrogative or bare.startswith(("compare", "screen")) \
        or "right now" in msg
    if data_intent and any(p in msg for p in _DATA_PHRASES) \
            and not any(p in msg for p in _RETRO_PHRASES) \
            and not any(p in msg for p in _STRATEGY_NOUNS):
        return "data_question"
    if interrogative and any(p in msg for p in _STATUS_PHRASES):
        return "strategy_status"
    if any(p in msg for p in _EXPLORE_PHRASES):
        return "strategy_exploration"
    if "?" in msg and any(p in msg for p in _ARCHIVE_PHRASES):
        return "archive_question"
    if any(p in msg for p in _CHANGE_PHRASES):
        return "strategy_change"
    return "other"


async def _classify(message: str, history: list[dict], pending_exists: bool,
                    has_constitution: bool, draft_live: bool,
                    context: dict | None = None) -> str:
    recent = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-6:])
    context_line = ""
    if context and context.get("page"):
        where = context["page"]
        if context.get("ticker"):
            where += f" page for {str(context['ticker']).upper()}"
        context_line = f"The user is currently viewing the {where}.\n"
    user = (
        f"Current Pending Draft exists: {'yes' if pending_exists else 'no'} "
        f"(shown in this session: {'yes' if draft_live else 'no'})\n"
        f"Active Constitution exists: {'yes' if has_constitution else 'no'}\n"
        f"{context_line}"
        f"Recent conversation (most recent last):\n{recent or '(none)'}\n\n"
        f'New user message: """{message}"""'
    )
    result = await get_ai().complete_json(
        "chat_mode_routing", _CLASSIFY_SYSTEM, user, _CLASSIFY_SHAPE,
        tier="fast", max_output_tokens=50,
        stub={"mode": keyword_mode(message, pending_exists)},
    )
    mode = result.get("mode") if isinstance(result, dict) else None
    return mode if mode in MODES else keyword_mode(message, pending_exists)


def _last_assistant_refs(history: list[dict]) -> dict:
    for m in reversed(history):
        if m["role"] == "assistant":
            return m.get("refs") or {}
    return {}


async def handle_message(stores, session_id: str | None, message: str,
                         context: dict | None = None) -> dict:
    """Handle one FundOps Chat message; returns the chat contract response.
    `context` is the ambient page context ({page, ticker?}) when the message
    came from the chat drawer on another page."""
    sid = stores.constitution.ensure_chat_session(session_id)
    history = stores.constitution.chat_history(sid)
    pending = stores.constitution.pending_proposal()
    active = stores.constitution.active_version()
    # The Current Pending Draft is "live" only if the most recent assistant
    # message in THIS session showed it (Live Strategy Chat Session boundary).
    draft_live = bool(pending) and \
        _last_assistant_refs(history).get("draft_id") == pending["id"]

    mode = await _classify(message, history, bool(pending), bool(active),
                           draft_live, context)
    # Reading a retained document: archive/other questions go to the analyst,
    # which is the only mode that can READ the open artifact (get_artifact) —
    # archive search only matches titles/metadata and misses content questions.
    if (context or {}).get("artifact_id") and mode in ("archive_question", "other"):
        mode = "data_question"
    contract_mode = _CONTRACT_MODE[mode]
    stores.constitution.add_chat_message(
        sid, "user", message, mode=contract_mode, refs={"classified_mode": mode},
    )

    out: dict = {"session_id": sid, "mode": contract_mode}
    reply_refs: dict = {"classified_mode": mode}

    if mode == "approval":
        result = _handle_approval(stores, pending, draft_live)
    elif mode == "rejection":
        result = await _handle_rejection(stores, sid, message, history, pending)
    elif mode == "cancellation":
        result = _handle_cancellation(stores, pending)
    elif mode == "strategy_change":
        result = await strategy_chat.handle_strategy_change(stores, sid, message, history)
    elif mode == "strategy_exploration":
        result = {"reply": await strategy_chat.explore(stores, sid, message, history)}
    elif mode == "strategy_status":
        result = {"reply": strategy_chat.status_answer(stores, message)}
    elif mode == "archive_question":
        result = await archive_qa.answer(stores, sid, message)
    elif mode == "data_question":
        result = await analyst.answer(stores, sid, message, history, context)
    elif mode == "product_question":
        result = await product_guide.answer(stores, message)
    elif mode == "action_request":
        result = _handle_action_request(stores, message, context)
    else:
        result = {"reply": (
            "I can help with your strategy (describe how you want to invest, or ask "
            "what's currently wired) or answer questions about retained research and "
            "portfolio history. What would you like to do?"
        )}

    # Deterministic safety net: humanize any leaked internal token (kind tags,
    # capability keys, criterion ids, raw metric ids, raw operators) before the
    # reply reaches the user — covers both deterministic composers and model
    # output (drafts, archive answers).
    out["reply"] = labels.humanize_chat_text(result["reply"])
    if result.get("draft") is not None:
        # The draft IS the ProposalCard; carry the proposal id on it so the UI
        # can approve/reject without a side channel (draft_id also kept in refs
        # for the Live Strategy Chat Session draft-liveness check).
        draft = dict(result["draft"])
        if result.get("draft_id"):
            draft["id"] = result["draft_id"]
        # Attach humanized display fields to each rule so the structured draft
        # card renders product language without mapping raw ids on the client.
        draft["rules"] = [
            {**r,
             "rule": labels.describe_rule(r),
             "metric_label": labels.metric_label(r.get("metric") or r.get("criterion_id")),
             "kind_label": labels.kind_label(r.get("kind"))}
            for r in (draft.get("rules") or [])
        ]
        out["draft"] = draft
        reply_refs["draft_id"] = result.get("draft_id")
    if result.get("citations") is not None:
        out["citations"] = result["citations"]
        reply_refs["citations"] = result["citations"]
    if result.get("actions") is not None:
        out["actions"] = result["actions"]
    if result.get("blocks"):
        out["blocks"] = result["blocks"]
        # Persist (row-capped) so /chat/history replays render the blocks.
        reply_refs["blocks"] = [
            {**b, "rows": b["rows"][:BLOCK_ROW_CAP]} if b.get("rows") else b
            for b in result["blocks"]
        ]
    if result.get("version_id"):
        reply_refs["version_id"] = result["version_id"]

    stores.constitution.add_chat_message(
        sid, "assistant", out["reply"], mode=contract_mode, refs=reply_refs,
    )
    return out


def _handle_approval(stores, pending: dict | None, draft_live: bool) -> dict:
    if not pending:
        return {"reply": (
            "There's no pending strategy draft to approve right now, so I haven't "
            "activated anything. What would you like to approve — should I draft a "
            "strategy change first?"
        )}
    if not draft_live:
        # Stale session (e.g. app restart): re-show, never activate from a bare yes.
        payload = pending["payload"]
        reply = (
            "This is a new chat session, so I won't activate a draft from \"yes\" "
            "alone. Here is the pending draft again — please review and confirm.\n\n"
            + strategy_chat.render_draft(payload, None)
        )
        return {"reply": reply, "draft": payload, "draft_id": pending["id"]}
    try:
        version = strategy_service.accept_proposal(stores, pending["id"])
    except (ValueError, LookupError) as exc:
        # Wiring failure visibility: never fake success (eval 15).
        return {"reply": (
            f"Approval did not complete — nothing was activated or wired: {exc} "
            "Your previous Constitution (if any) is unchanged; the draft is still "
            "pending. Tell me how to adjust it, or say \"cancel\" to drop it."
        )}
    return {
        "reply": version["activation_confirmation"],
        "version_id": version["id"],
    }


async def _handle_rejection(stores, session_id: str, message: str,
                            history: list[dict], pending: dict | None) -> dict:
    if not pending:
        return {"reply": (
            "There's no pending draft, so nothing was saved or wired. "
            "What would you like to change about your strategy?"
        )}
    if strategy_chat.has_specifics(message):
        # Specific correction: revise into a new full draft (auto-cancels the
        # prior pending draft) and ask for approval again.
        result = await strategy_chat.handle_strategy_change(stores, session_id, message, history)
        if result.get("draft") is not None:
            result["reply"] = (
                "Got it — the previous draft was not saved or wired. "
                "Here is the revised draft:\n\n" + result["reply"]
            )
        return result
    return {"reply": (
        "Understood — that draft has not been saved or wired, and it won't be unless "
        "you approve it. What part is wrong: the rules, the thresholds, the ranking "
        "emphasis, or the overall direction?"
    )}


def _handle_cancellation(stores, pending: dict | None) -> dict:
    if not pending:
        return {"reply": (
            "There's no pending draft to cancel — nothing has been saved or wired."
        )}
    stores.constitution.decide_proposal(pending["id"], "cancelled")
    stores.dashboard.resolve_source("strategy_proposal", pending["id"])
    return {"reply": (
        "Cancelled. Nothing was saved and no settings were wired; that draft is no "
        "longer an approval target. Your strategy is unchanged."
    )}
