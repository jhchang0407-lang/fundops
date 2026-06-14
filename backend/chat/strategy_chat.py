"""Strategy Chat: strategy-changing conversational behavior (ADR-0007..0011).

Drafts Strategy Change Proposals from conversation, validates them through
deterministic guardrails, previews wiring, and asks for explicit approval.
Nothing is saved or wired until the user approves; unsupported desires are
preserved as Strategy Preference Memory instead of fake rules.
"""

from __future__ import annotations

import re

from backend.core.ai import get_ai
from backend.domain import guardrails, labels, metric_catalog, wiring
from backend.domain.criteria import Criterion

# --- deterministic signal detection (also the offline stub heuristics) -------

# theme -> (criterion suffix, metric, operator, threshold, interpretation)
_SIGNAL_RULES: dict[str, tuple[str, str, str, float, str]] = {
    "growth": ("revenue_growth_min", "revenue_growth", ">=", 0.10,
               "Require revenue growth of at least 10% per year"),
    "quality": ("roic_min", "roic", ">=", 0.15,
                "Require return on invested capital of at least 15%"),
    "margin": ("gross_margin_min", "gross_margin", ">=", 0.40,
               "Require gross margins of at least 40%"),
    "value": ("pe_max", "pe", "<=", 25.0,
              "Require a price/earnings multiple of 25x or less"),
    "debt": ("debt_equity_max", "debt_equity", "<=", 1.0,
             "Require debt/equity of 1.0x or less"),
    "dividend": ("dividend_yield_min", "dividend_yield", ">=", 0.02,
                 "Require a dividend yield of at least 2%"),
    "payout": ("payout_ratio_max", "payout_ratio", "<=", 0.60,
               "Require a payout ratio of 60% or less"),
    "cashflow": ("fcf_yield_min", "fcf_yield", ">=", 0.04,
                 "Require a free-cash-flow yield of at least 4%"),
    "dilution": ("sbc_to_revenue_max", "sbc_to_revenue", "<=", 0.05,
                 "Require stock-based compensation under 5% of revenue"),
}

_SIGNAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "growth": ("revenue growth", "growing", "growth", "grower"),
    "quality": ("roic", "return on invested", "return on capital", "quality", "compounder"),
    "margin": ("margin",),
    "value": ("valuation", "p/e", "pe ratio", "earnings multiple", "cheap", "times earnings",
              "fair price", "undervalued", "value"),
    "debt": ("debt", "leverage", "balance sheet"),
    "dividend": ("dividend",),
    "payout": ("payout",),
    "cashflow": ("free cash flow", "fcf", "cash flow", "cash generation"),
    "dilution": ("stock-based comp", "stock based comp", "sbc", "dilution"),
}

_UNSUPPORTED_KEYWORDS: dict[str, str] = {
    "ceo": "Strong CEO / leadership quality (no observable signal chosen yet)",
    "management": "Management quality (no observable signal chosen yet)",
    "moat": "Durable competitive moat (qualitative; tracked as a preference)",
    "brand": "Brand strength (qualitative; tracked as a preference)",
    "culture": "Company culture (qualitative; tracked as a preference)",
}

_CLARIFYING_EXAMPLES = (
    "revenue growth", "gross margins", "return on invested capital (ROIC)",
    "free-cash-flow quality", "debt levels", "stock-based compensation",
)


def detect_signals(message: str) -> list[str]:
    """Themes in the message that map to wireable observable signals."""
    msg = message.lower()
    return [theme for theme, words in _SIGNAL_KEYWORDS.items()
            if any(w in msg for w in words)]


def has_specifics(message: str) -> bool:
    """True when a message carries concrete, draftable strategy content."""
    return bool(re.search(r"\d", message)) or bool(detect_signals(message))


def _detect_unsupported(message: str) -> list[str]:
    msg = message.lower()
    return [label for kw, label in _UNSUPPORTED_KEYWORDS.items() if kw in msg]


# --- offline stub draft -------------------------------------------------------

def _clarifying_prompt() -> str:
    examples = ", ".join(_CLARIFYING_EXAMPLES)
    return (
        "Before I draft anything: what does a \"good company\" look like to you in "
        "observable terms? For example, FundOps can screen on data like "
        f"{examples}. Which of those (or what else) matters most to you?"
    )


def _stub_proposal(message: str) -> dict:
    """Deterministic quality/value-blend ProposalCard from message keywords.

    Must always produce criteria that pass guardrails — the offline product
    stays honest end to end.
    """
    themes = detect_signals(message)
    rules: list[dict] = []
    for theme in themes:
        suffix, metric, op, value, interp = _SIGNAL_RULES[theme]
        rules.append({
            "criterion_id": f"screen.{suffix}",
            "kind": "screen",
            "metric": metric,
            "operator": op,
            "value": value,
            "weight": None,
            "data_support_level": "fully",
            "rule_rationale": f"User asked for {theme}-oriented requirements in chat",
            "rule_source": "chat",
            "interpretation": interp,
        })
    # Ranking blend: emphasize detected themes, default quality/value/growth.
    rank_metrics = []
    for theme, metric, label in (
        ("quality", "roic", "Higher ROIC ranks better"),
        ("cashflow", "fcf_yield", "Higher free-cash-flow yield ranks better"),
        ("growth", "revenue_growth", "Faster revenue growth ranks better"),
        ("dividend", "dividend_yield", "Higher dividend yield ranks better"),
    ):
        if theme in themes:
            rank_metrics.append((metric, label))
    if not rank_metrics:
        rank_metrics = [("roic", "Higher ROIC ranks better"),
                        ("fcf_yield", "Higher free-cash-flow yield ranks better"),
                        ("revenue_growth", "Faster revenue growth ranks better")]
    weight = round(1.0 / len(rank_metrics), 4)
    for metric, label in rank_metrics:
        rules.append({
            "criterion_id": f"rank.{metric}",
            "kind": "rank",
            "metric": metric,
            "operator": ">",
            "value": 0.0,
            "weight": weight,
            "data_support_level": "fully",
            "rule_rationale": "Ranking emphasis inferred from the user's stated priorities",
            "rule_source": "chat",
            "interpretation": label,
        })

    blend_themes = [t for t in ("quality", "value", "growth", "dividend") if t in themes] or \
                   ["quality", "value"]
    share = round(1.0 / len(blend_themes), 2)
    style_blend = {t: share for t in blend_themes}
    north_star = ("Own well-run businesses that meet every stated requirement — "
                  + ", ".join(blend_themes) + " first")
    screen_count = sum(1 for r in rules if r["kind"] == "screen")
    summary = (
        f"A {'/'.join(blend_themes)} strategy: companies must clear {screen_count} hard "
        f"screening requirement(s) ({', '.join(_SIGNAL_RULES[t][1] for t in themes)}), and "
        "survivors are ranked by " + ", ".join(m for m, _ in rank_metrics) + "."
    )
    return {
        "summary": summary,
        "north_star": north_star,
        "style_blend": style_blend,
        "rules": rules,
        "ic": {},
        "universe": {"name": "S&P 500"},
        "unsupported_preferences": _detect_unsupported(message),
        "tradeoffs": [
            "Hard requirements narrow the candidate pool; great companies that miss one "
            "threshold are excluded entirely.",
            "Fixed numeric thresholds can be sensitive to market timing and accounting noise.",
        ],
    }


def _stub_draft_decision(message: str) -> dict:
    themes = detect_signals(message)
    has_numbers = bool(re.search(r"\d", message))
    ready = len(themes) >= 3 or (len(themes) >= 2 and has_numbers)
    if not ready:
        return {"ready": False, "clarifying_prompt": _clarifying_prompt(), "proposal": None}
    return {"ready": True, "clarifying_prompt": None, "proposal": _stub_proposal(message)}


# --- AI drafting --------------------------------------------------------------

_PROPOSAL_SHAPE = """{
  "ready": true|false,
  "clarifying_prompt": "one broad clarifying question with observable-signal examples, or null when ready",
  "proposal": null | {
    "summary": "plain-English strategy summary",
    "north_star": "one-sentence investing goal",
    "style_blend": {"label": 0.0},
    "rules": [{
      "criterion_id": "kind.metric_purpose e.g. screen.roic_min",
      "kind": "screen|rank|research_review|ic_hurdle|preference",
      "metric": "metric id from the catalog",
      "operator": ">|<|>=|<=|==|!=|between|in|not_in",
      "value": 0.0,
      "weight": null,
      "data_support_level": "fully|partial|proxy|research_review|unsupported",
      "rule_rationale": "why the user wants this",
      "rule_source": "chat",
      "interpretation": "plain-English meaning"
    }],
    "ic": {"gate_score_blend": null, "pass_cutoff": null},
    "universe": {"name": "S&P 500", "tickers": null},
    "unsupported_preferences": ["desires FundOps cannot wire yet"],
    "tradeoffs": ["what this strategy gives up or risks"]
  }
}"""

_DRAFT_SYSTEM = (
    "You are FundOps Strategy Chat. You translate a user's investing intent into a "
    "reviewable Strategy Change Proposal. FIRST apply a Strategy Readiness Check: "
    "you need an investing goal/north star and at least some concrete criteria "
    "preferences (a universe idea is optional). If the message is still vague, set "
    "ready=false and ask ONE broad clarifying question that offers observable-signal "
    "examples — never a survey, never instant defaults. When ready, draft the proposal: "
    "criteria MUST use metric ids from the provided catalog with supported operators; "
    "percent-style metrics use decimal values (15% -> 0.15). Only hard-gate-capable "
    "metrics may be 'screen' or 'ic_hurdle' kinds. Anything not observable goes in "
    "unsupported_preferences, never a fake rule. Be honest about tradeoffs."
)


def _metric_catalog_text() -> str:
    hard, soft = [], []
    for mid in metric_catalog.all_metric_ids():
        m = metric_catalog.get_metric(mid)
        if m is None:
            continue
        (hard if m.hard_gate_capable else soft).append(f"{mid}({','.join(m.operators)})")
    return (
        "Hard-gate-capable metrics (valid for screen/ic_hurdle, also rank): "
        + ", ".join(hard)
        + "\nRank/research-review only metrics: " + ", ".join(soft)
    )


def _conversation_text(history: list[dict], message: str, limit: int = 10) -> str:
    lines = [f"{m['role']}: {m['content'][:500]}" for m in history[-limit:]]
    lines.append(f"user: {message}")
    return "\n".join(lines)


def preference_text(stores, limit: int = 5) -> str:
    """Strategy Preference Memory read-back: unsupported desires saved in
    earlier sessions inform new drafts instead of being write-only."""
    prefs = [
        m["content"].get("text")
        for m in stores.constitution.memory(kind="preference")[:limit]
        if isinstance(m.get("content"), dict) and m["content"].get("text")
    ]
    if not prefs:
        return ""
    return ("Remembered preferences from earlier sessions (not currently "
            "enforceable as rules):\n- " + "\n- ".join(prefs))


def _active_summary(active: dict | None) -> str:
    if not active:
        return "No active Constitution yet (first-time setup)."
    crits = ", ".join(
        f"{c['criterion_id']} {c.get('operator') or ''} {c.get('value')}".strip()
        for c in active.get("criteria", [])
    )
    return (
        f"Active Constitution v{active['version_number']}: north star = "
        f"{active.get('north_star') or 'unset'}; criteria: {crits or 'none'}."
    )


def _normalize_payload(payload: dict) -> dict:
    payload = dict(payload or {})
    rules = []
    for raw in payload.get("rules") or []:
        if not isinstance(raw, dict):
            continue
        r = dict(raw)
        r.setdefault("rule_source", "chat")
        r["rule_source"] = r.get("rule_source") or "chat"
        r.setdefault("data_support_level", "fully")
        r["rule_rationale"] = r.get("rule_rationale") or "Requested by the user in Strategy Chat"
        rules.append(r)
    payload["rules"] = rules
    payload.setdefault("unsupported_preferences", [])
    payload.setdefault("tradeoffs", [])
    payload.setdefault("ic", {})
    payload.setdefault("style_blend", {})
    if not payload.get("universe"):
        payload["universe"] = {"name": "S&P 500"}
    return payload


def _salvage(payload: dict) -> tuple[dict, list[str]]:
    """Drop criteria that individually fail guardrails; keep them visible as
    preserved-but-not-wired preferences instead of faking success."""
    kept, dropped = [], []
    for raw in payload.get("rules") or []:
        try:
            errs, _ = guardrails.validate_criterion(Criterion.from_dict(raw))
        except (KeyError, TypeError):
            errs = ["malformed criterion"]
        if errs:
            dropped.append(
                f"{raw.get('criterion_id') or raw.get('metric') or 'rule'} — "
                f"could not be wired ({'; '.join(errs)})"
            )
        else:
            kept.append(raw)
    out = dict(payload)
    out["rules"] = kept
    if dropped:
        out["unsupported_preferences"] = list(payload.get("unsupported_preferences") or []) + dropped
    return out, dropped


# --- draft rendering ------------------------------------------------------------

def _fmt_rule(i: int, r: dict) -> str:
    # Human, kind-aware rule text — never raw ids/operators (labels.describe_rule
    # handles 'Rank by FCF Yield' vs 'ROIC ≥ 15%').
    line = f"{i}. {labels.kind_label(r.get('kind'))} — {labels.describe_rule(r)}"
    if r.get("interpretation"):
        line += f" ({r['interpretation']})"
    return line


def build_approval_prompt(active: dict | None, payload: dict) -> str:
    if active is None:
        return (
            "Approving this draft will create Constitution Version 1 and wire the "
            "settings previewed above across Screener, Thesis, IC Review, Memo, and "
            "Portfolio Review. Nothing is saved or wired until you approve. "
            "Reply \"yes\" to approve, or tell me what to change."
        )
    from backend.services.strategy_service import diff_criteria
    diff = diff_criteria(active.get("criteria", []), payload.get("rules", []))
    parts = []
    if diff["added"]:
        parts.append(f"{len(diff['added'])} rule(s) added")
    if diff["removed"]:
        parts.append(f"{len(diff['removed'])} rule(s) removed")
    if diff["changed"]:
        parts.append(f"{len(diff['changed'])} rule(s) changed")
    change_text = ", ".join(parts) or "no criteria changes"
    n = active["version_number"]
    return (
        f"Approving this draft will create Constitution Version {n + 1} "
        f"(replacing v{n}). Changes vs v{n}: {change_text}. No other workflow "
        "settings change. Reply \"yes\" to approve, or tell me what to adjust."
    )


def _fmt_blend(blend: dict) -> str:
    return " / ".join(
        f"{k} {v:.0%}" if isinstance(v, (int, float)) else f"{k} {v}"
        for k, v in blend.items()
    )


def render_draft(payload: dict, validation: guardrails.GuardrailResult | None) -> str:
    lines = ["Strategy Draft (nothing is saved or wired yet)", "", payload.get("summary", "")]
    if payload.get("north_star"):
        lines += ["", f"North star: {payload['north_star']}"]
    blend = payload.get("style_blend") or {}
    if blend:
        lines.append("Style blend: " + _fmt_blend(blend))
    rules = payload.get("rules") or []
    if rules:
        lines += ["", "Exact rules:"]
        lines += [_fmt_rule(i + 1, r) for i, r in enumerate(rules)]
    preview = payload.get("wiring_preview") or {}
    if preview:
        lines += ["", "Wiring preview — approval wires these settings:"]
        lines += [f"- {cap}: {summary}" for cap, summary in preview.items()]
    unsupported = payload.get("unsupported_preferences") or []
    if unsupported:
        lines += ["", "Saved preferences (preserved, NOT wired):"]
        lines += [f"- {p}" for p in unsupported]
    tradeoffs = payload.get("tradeoffs") or []
    if tradeoffs:
        lines += ["", "Tradeoffs:"]
        lines += [f"- {t}" for t in tradeoffs]
    if validation and validation.warnings:
        lines += ["", "Restrictiveness warning:"]
        lines += [f"- {w}" for w in validation.warnings]
        lines.append("You can proceed as-is; this is a heads-up, not a block.")
    lines += ["", payload.get("approval_prompt", "")]
    return "\n".join(line for line in lines if line is not None)


# --- entry points ---------------------------------------------------------------

async def handle_strategy_change(stores, session_id: str, message: str,
                                 history: list[dict]) -> dict:
    """Strategy Readiness Check + drafting in one deep call; guardrail-validated
    proposal creation with wiring preview and approval prompt."""
    active = stores.constitution.active_version()
    prefs = preference_text(stores)
    user_prompt = (
        f"{_active_summary(active)}\n\n"
        + (f"{prefs}\n\n" if prefs else "")
        + f"Conversation (most recent last):\n{_conversation_text(history, message)}\n\n"
        f"Wireable metric catalog:\n{_metric_catalog_text()}"
    )
    result = await get_ai().complete_json(
        "strategy_draft", _DRAFT_SYSTEM, user_prompt, _PROPOSAL_SHAPE,
        tier="deep", max_output_tokens=4000, stub=_stub_draft_decision(message),
    )
    if not isinstance(result, dict) or not result.get("ready") or not result.get("proposal"):
        prompt = (result or {}).get("clarifying_prompt") if isinstance(result, dict) else None
        return {"reply": prompt or _clarifying_prompt(), "draft": None, "draft_id": None}

    payload = _normalize_payload(result["proposal"])
    validation = guardrails.validate_proposal(payload)
    if validation.errors and get_ai().configured:
        repaired = await get_ai().complete_json(
            "strategy_draft_repair", _DRAFT_SYSTEM,
            user_prompt
            + "\n\nYour previous proposal failed deterministic guardrails with these exact "
              "errors — return a corrected full proposal (ready=true):\n- "
            + "\n- ".join(validation.errors)
            + f"\n\nPrevious proposal: {payload}",
            _PROPOSAL_SHAPE, tier="deep", stub={"ready": True, "proposal": payload},
        )
        if isinstance(repaired, dict) and repaired.get("proposal"):
            payload = _normalize_payload(repaired["proposal"])
            validation = guardrails.validate_proposal(payload)
    dropped: list[str] = []
    if validation.errors:
        payload, dropped = _salvage(payload)
        validation = guardrails.validate_proposal(payload)
    if validation.errors:
        return {
            "reply": (
                "I couldn't turn that into a valid, wireable draft — nothing was saved. "
                "Guardrails reported: " + "; ".join(validation.errors)
                + ". Tell me which observable signals to use and I'll try again."
            ),
            "draft": None, "draft_id": None,
        }

    criteria = [Criterion.from_dict(r) for r in payload["rules"]]
    projections = wiring.project_settings(
        criteria, payload.get("north_star"),
        ic_config=payload.get("ic") or {}, universe=payload.get("universe"),
    )
    payload["wiring_preview"] = {cap: p["summary"] for cap, p in projections.items()}
    payload["approval_prompt"] = build_approval_prompt(active, payload)

    prior_pending = stores.constitution.pending_proposal()
    proposal = stores.constitution.create_proposal(
        payload, validation.to_dict(), payload.get("summary"), session_id,
    )
    if prior_pending:
        stores.dashboard.resolve_source("strategy_proposal", prior_pending["id"])
    stores.dashboard.upsert_item(
        kind="decision", section="needs_decision", source_type="strategy_proposal",
        source_id=proposal["id"], source_version="1",
        title="Strategy proposal awaiting approval", body=payload.get("summary"),
    )
    for pref in payload.get("unsupported_preferences") or []:
        stores.constitution.remember("preference", {"text": pref},
                                     source=f"chat:{session_id}")

    reply = render_draft(payload, validation)
    if dropped:
        reply = (
            "Heads-up: some of what you asked for couldn't be wired and is preserved "
            "as a saved preference instead — see \"Saved preferences\" below.\n\n" + reply
        )
    return {"reply": reply, "draft": payload, "draft_id": proposal["id"]}


_EXPLORE_SHAPE = '{"explanation": "tradeoff discussion", "offer": "one-line offer to draft"}'


async def explore(stores, session_id: str, message: str, history: list[dict]) -> str:
    """Strategy Tradeoff Explanation: discuss, never draft."""
    active = stores.constitution.active_version()
    themes = detect_signals(message) or ["that change"]
    topic = themes[0]
    stub = {
        "explanation": (
            f"Worth thinking through before changing anything. Leaning more on {topic} "
            "typically improves how aligned your pipeline is with that trait, but it "
            "narrows the candidate pool — companies strong elsewhere get filtered or "
            "ranked down. Watch for false signals too: a single good year can look like "
            "a durable trend, and thresholds near sector norms churn candidates in and "
            "out. Nothing in your current setup changes from this conversation."
        ),
        "offer": ("If you want, I can draft a concrete rule change for your review — "
                  "you'd see exact rules and wiring before anything activates."),
    }
    prefs = preference_text(stores)
    result = await get_ai().complete_json(
        "strategy_exploration",
        "You are FundOps Strategy Chat in exploration mode. Discuss what the idea "
        "improves, what it narrows, and possible false signals. Do NOT propose exact "
        "rules and do NOT change anything; end by offering to draft a change.",
        f"{_active_summary(active)}\n\n"
        + (f"{prefs}\n\n" if prefs else "")
        + f"Conversation:\n{_conversation_text(history, message)}",
        _EXPLORE_SHAPE, tier="deep", stub=stub,
    )
    if not isinstance(result, dict):
        result = stub
    return f"{result.get('explanation', '')}\n\n{result.get('offer', '')}".strip()


def status_answer(stores, message: str) -> str:
    """Read-only Strategy Status: answer from the active Constitution, criteria
    rationales, and durable wiring summaries. Deterministic — no model call."""
    active = stores.constitution.active_version()
    if not active:
        return (
            "There's no active Constitution yet, so no strategy settings are wired. "
            "Tell me how you want to invest and I'll draft one for your approval."
        )
    msg = message.lower()
    hits = []
    for c in active.get("criteria", []):
        metric = c.get("metric") or ""
        m = metric_catalog.get_metric(metric) if metric else None
        names = {metric, metric.replace("_", " ")}
        if m:
            names.add(m.label.lower())
        if any(n and n in msg for n in names):
            hits.append(c)
    if hits:
        lines = []
        for c in hits:
            line = f"Your current {labels.kind_label(c.get('kind')).lower()} — {labels.describe_rule(c)}."
            if c.get("interpretation"):
                line += f" In plain terms: {c['interpretation']}."
            if c.get("rule_rationale"):
                line += f" Saved rationale: {c['rule_rationale']}"
            else:
                line += (" No rationale was saved with this rule, so I can only offer a "
                         "general explanation of the metric, not why you chose this value.")
            lines.append(line)
        lines.append("Want to change any of this? Say so and I'll draft a proposal — "
                     "nothing changes until you approve.")
        return "\n".join(lines)
    crit_lines = [_fmt_rule(i + 1, c) for i, c in enumerate(active.get("criteria", []))]
    projections = stores.constitution.projections_for(active["id"])
    proj_lines = [f"- {labels.capability_label(p['capability'])}: {p['summary_text']}"
                  for p in projections]
    blend = active.get("style_blend") or {}
    parts = [
        f"Active Constitution v{active['version_number']} "
        f"(activated {active.get('activated_at', '')[:10]}).",
        f"North star: {active.get('north_star') or 'not set'}.",
    ]
    if blend:
        parts.append("Style blend: " + _fmt_blend(blend))
    if crit_lines:
        parts += ["", "Rules:"] + crit_lines
    if proj_lines:
        parts += ["", "Wired settings:"] + proj_lines
    parts += ["", "Ask about any specific rule, or tell me what to change."]
    return "\n".join(parts)
