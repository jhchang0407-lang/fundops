"""Strategy v2 API routes.

Handles:
- Strategy conversation (create/refine strategy via AI chat)
- Strategy CRUD (get, list, update)
- Scoring code generation and review
- Feedback capture on screener results
- Screener v2 run (using AI-generated scoring)
"""

import json
import logging
import asyncio
import time
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.api.deps import get_config, get_llm, get_memory
from backend.core.db_v2 import ScreenerV2DB
from backend.learning.behavioral import analyze_drift
from backend.learning.feedback_loop import detect_patterns
from backend.scoring.strategy import (
    build_conversation_messages,
    parse_strategy_response,
    validate_strategy_profile,
    create_strategy_id,
)
from backend.scoring.codegen import generate_scoring_code
from backend.scoring.sandbox import compile_scoring_function, execute_scoring, ScoringCodeError

router = APIRouter()
log = logging.getLogger("fundops.api.strategy")

# In-memory cache of compiled scoring functions: version_id -> callable
_scoring_cache: dict = {}


def _strip_agent_actions_from_message(msg: str) -> str:
    """Remove raw JSON agent_actions blocks from the AI's conversational response.

    The AI sometimes includes sections like:
      "Agent actions I submitted\n[{...json...}]"
    or raw JSON blocks that are meant for the extraction layer, not the user.
    Strip these so the chat stays clean and readable.
    """
    import re

    # Remove "Agent actions I submitted" or similar headers followed by JSON arrays
    msg = re.sub(
        r'\n*(?:Agent actions?\s*(?:I\s+)?submitted|Actions?\s+applied|Changes?\s+submitted)[\s:]*\n*\[[\s\S]*?\]\s*',
        '\n',
        msg,
        flags=re.IGNORECASE,
    )

    # Remove standalone JSON arrays that look like agent_actions (start with [{ and contain "agent":)
    msg = re.sub(
        r'\n*\[\s*\{[^}]*"agent"\s*:[^]]*\]\s*',
        '',
        msg,
    )

    # Remove "```json ... ```" code blocks containing agent_actions
    msg = re.sub(
        r'```(?:json)?\s*\[?\s*\{[^}]*"agent"\s*:[\s\S]*?```',
        '',
        msg,
    )

    # Clean up excessive newlines left after stripping
    msg = re.sub(r'\n{3,}', '\n\n', msg)

    return msg.strip()


def _get_db() -> ScreenerV2DB:
    """Get the v2 database instance."""
    config = get_config()
    db_path = config.resolved.get("db_path", str(Path.home() / ".fundops" / "fundops.db"))
    return ScreenerV2DB(db_path=db_path)


async def _regenerate_scoring_code(strategy_id: str, reason: str = "Strategy refined via chat"):
    """Regenerate scoring code from current constitution and update active version.

    Called after any conversation action that changes scoring-relevant fields
    (dimensions, weights, filters, signals, disqualifiers, sector routing).
    """
    try:
        from backend.scoring.codegen import generate_scoring_code as _gen_scoring
        llm = get_llm()
        db = _get_db()
        try:
            # Build profile from current constitution
            constitution = db.get_active_constitution()
            if not constitution:
                log.warning("No active constitution — skipping scoring code regeneration")
                return
            strategy = db.get_strategy(strategy_id)
            if not strategy:
                log.warning(f"No strategy {strategy_id} — skipping scoring code regeneration")
                return

            # Build the profile dict that codegen expects
            profile = {
                "north_star": constitution.get("north_star", ""),
                "dimensions": constitution.get("dimensions", {}),
                "must_have_signals": constitution.get("must_have_signals", []),
                "anti_signals": constitution.get("anti_signals", []),
                "disqualifiers": constitution.get("disqualifiers", []),
                "sector_routing": constitution.get("sector_routing"),
                "agent_profiles": constitution.get("agent_profiles", {}),
            }

            # Get current version number to increment
            current_vid = strategy.get("active_version_id")
            current_version_num = 1
            if current_vid:
                versions = db.conn.execute(
                    "SELECT version_number FROM strategy_versions WHERE id = ?", (current_vid,)
                ).fetchone()
                if versions:
                    current_version_num = (versions[0] or 0) + 1

            result = await _gen_scoring(llm, profile)
            version_row = db.create_version(
                version_id=result["version_id"],
                strategy_id=strategy_id,
                version_number=current_version_num,
                scoring_code=result["scoring_code"],
                label_map=result["label_map"],
                explanation=result["explanation"],
                change_reason=reason,
            )
            # create_version already sets active_version_id on strategy_profiles,
            # but also update the constitution for consistency.
            new_vid = version_row["id"] if version_row else None
            try:
                db.update_constitution(
                    strategy_id,
                    active_version_id=new_vid,
                    _change_type="system",
                    _change_summary=f"Scoring code regenerated: {reason}",
                    _trigger="codegen",
                )
            except Exception:
                pass
            # Clear cache so next screener run uses new code
            if new_vid is not None:
                _scoring_cache.pop(new_vid, None)
            if current_vid:
                _scoring_cache.pop(current_vid, None)
            log.info(f"Scoring code regenerated for {strategy_id} (v{current_version_num}): {reason}")
        finally:
            db.close()
    except Exception as e:
        log.error(f"Scoring code regeneration failed: {e}", exc_info=True)


# --- Strategy Conversation ---

class ConversationMessage(BaseModel):
    role: str
    content: str


class StrategyConversationRequest(BaseModel):
    message: str
    history: list[ConversationMessage] = []
    strategy_id: Optional[str] = None  # None = new strategy, set = refining
    session_id: Optional[str] = None   # For conversation persistence


@router.post("/strategy/conversation")
async def strategy_conversation(body: StrategyConversationRequest):
    """Multi-turn AI conversation for strategy definition.

    First-time: AI probes 7 dimensions of the user's investment philosophy.
    Refinement: Shows current strategy, helps adjust specific dimensions.

    Persists conversation history and injects decision context from judgment events.
    """
    if not body.message.strip():
        raise HTTPException(400, "Message cannot be empty")

    llm = get_llm()
    if not llm:
        raise HTTPException(503, "AI model not configured. Set up in Settings > AI Model.")

    db = _get_db()

    # Get existing strategy/constitution for refinement mode
    current_strategy = None
    constitution = db.get_active_constitution()
    if body.strategy_id:
        current_strategy = db.get_strategy(body.strategy_id)

    # Generate or use session ID for persistence
    session_id = body.session_id
    if not session_id:
        import uuid
        session_id = f"sess-{uuid.uuid4().hex[:8]}"

    # Save the user message (with retry for DB lock)
    constitution_id = (constitution or {}).get("id") or (current_strategy or {}).get("id")
    for _attempt in range(3):
        try:
            db.save_conversation_message(
                session_id=session_id, role="user", content=body.message,
                constitution_id=constitution_id,
            )
            break
        except Exception as e:
            if "locked" in str(e) and _attempt < 2:
                await asyncio.sleep(0.5)
            else:
                log.warning(f"Failed to save user message: {e}")
                break  # Non-fatal — continue with conversation even if save fails

    # Get current agent settings to pass as context
    # Translate internal config keys to human-readable names so the AI doesn't echo code at the user
    config = get_config()
    _KEY_LABELS = {
        "hurdle_pct": "min_return_pct",
        "hurdle_base_pct": "base_return_hurdle",
        "hurdle_bear_pct": "bear_return_hurdle",
        "bear_haircut_pct": "bear_case_haircut",
        "haircut_pct": "bear_case_haircut",
        "min_gross_margin_pct": "min_gross_margin",
        "max_position_pct": "max_position_size_pct",
        "concentration_limit_pct": "max_concentration_pct",
        "web_search_intensity": "research_depth",
        "max_research_words": "max_research_length",
    }
    def _humanize(cfg: dict) -> dict:
        return {_KEY_LABELS.get(k, k): v for k, v in cfg.items()
                if not k.startswith("growth_aware") and k not in ("lenses", "style_profile")}

    agent_settings = {}
    for agent_name in ["screener", "thesis", "ic_review", "allocator"]:
        agent_cfg = config.resolved.get("agents", {}).get(agent_name, {}).get("config", {})
        if agent_cfg:
            agent_settings[agent_name] = _humanize(agent_cfg)

    # Include portfolio config from the constitution's agent_profiles
    if constitution:
        portfolio_config = constitution.get("agent_profiles", {}).get("portfolio", {})
        if portfolio_config:
            agent_settings["portfolio"] = {
                "concentration_limit": portfolio_config.get("concentration_limit_pct", 20),
                "drawdown_threshold": portfolio_config.get("drawdown_threshold_pct", -15),
                "thesis_health_enabled": True,
            }

    # Build decision context from recent judgment events (scoped to active strategy)
    decision_context = ""
    constitution_version = constitution.get("version") if constitution else None
    if constitution_id:
        recent_events = db.get_recent_events(limit=50)
        # Filter to events from the current constitution version (or legacy events with no version)
        recent_events = [
            e for e in recent_events
            if e.get("constitution_version") == constitution_version
            or e.get("constitution_version") is None
        ]
        if recent_events:
            decision_lines = []
            for ev in recent_events[:10]:
                ticker = ev.get("ticker", "")
                etype = ev.get("event_type", "")
                data = ev.get("data", {})
                if etype in ("ic_passed", "ic_failed"):
                    decision_lines.append(
                        f"- IC {data.get('verdict', etype)}: {ticker} "
                        f"(conv {data.get('conviction', '?')}/5, "
                        f"base {data.get('base_return', '?')}%, "
                        f"bear {data.get('bear_return', '?')}%)"
                    )
                elif etype == "promoted":
                    decision_lines.append(f"- Promoted: {ticker} from screener")
                elif etype == "dismissed":
                    reason = data.get("dismiss_reason", "")
                    decision_lines.append(f"- Dismissed: {ticker} ({reason})" if reason else f"- Dismissed: {ticker}")
                elif etype == "thesis_generated":
                    decision_lines.append(
                        f"- Thesis: {ticker} (FV ${data.get('fair_value', '?')}, "
                        f"{data.get('expected_return', '?')}% ret, {data.get('conviction', '?')} conviction)"
                    )
            if decision_lines:
                decision_context = "\n\nRECENT DECISIONS BY THIS USER:\n" + "\n".join(decision_lines)

    # If refining, append decision context to agent settings
    if current_strategy or constitution:
        if decision_context:
            agent_settings["_decision_history"] = decision_context

    # Build conversation — restore from DB if frontend lost state
    history = [{"role": m.role, "content": m.content} for m in body.history]
    if not history and session_id:
        db_history = db.get_conversation_history(session_id=session_id)
        if db_history:
            history = [{"role": h["role"], "content": h["content"]} for h in db_history]

    # Enhance the strategy context for refinement mode
    strategy_for_prompt = current_strategy
    if not strategy_for_prompt and constitution:
        strategy_for_prompt = {
            "north_star": constitution.get("north_star", ""),
            "dimensions": constitution.get("dimensions", {}),
            "sector_routing": constitution.get("sector_routing", {}),
            "must_have_signals": constitution.get("must_have_signals", []),
            "anti_signals": constitution.get("anti_signals", []),
            "ic_hurdles": constitution.get("ic_hurdles", {}),
            "style_identity": constitution.get("style_identity", ""),
        }

    # Build learning context from both loops
    learning_context = None
    pending_proposals = []  # captured for proposal_actions in response
    if strategy_for_prompt and constitution:
        learning_lines = []
        try:
            # Loop 1a: behavioral drift (Said vs Did)
            drift = await analyze_drift(db, constitution)
            if drift.get("has_enough_data"):
                learning_lines.append(f"BEHAVIORAL DRIFT ({drift['decisions_analyzed']} IC decisions analyzed):")
                if drift.get("signal_drift"):
                    for sd in drift["signal_drift"][:3]:
                        learning_lines.append(
                            f"  - Must-have '{sd['signal']}' violated in {sd['violation_rate']}% of approvals ({sd['violations']}/{sd['total_approvals']} names)"
                        )
                if drift.get("anti_signal_violations"):
                    for av in drift["anti_signal_violations"][:3]:
                        learning_lines.append(
                            f"  - Anti-signal '{av['signal']}' present in {av['violations']} approved names"
                        )
                if drift.get("style_drift"):
                    for sd in drift["style_drift"][:2]:
                        learning_lines.append(f"  - Style: {sd['note']}")
                if drift.get("override_patterns"):
                    learning_lines.append(f"  - {len(drift['override_patterns'])} IC overrides recorded")
                if drift.get("approval_profile"):
                    prof = drift["approval_profile"]
                    base = prof.get("base_return") or {}
                    conv = prof.get("conviction") or {}
                    if base.get("median"):
                        learning_lines.append(
                            f"  - Approval profile: median base return {base['median']}%, mean conviction {conv.get('mean', '?')}/5"
                        )
                if not any([drift.get("signal_drift"), drift.get("anti_signal_violations"), drift.get("style_drift")]):
                    learning_lines.append("  - No significant drift between stated constitution and actual decisions.")
            else:
                decisions_so_far = drift.get("decisions_analyzed", 0)
                learning_lines.append(
                    f"BEHAVIORAL ANALYSIS: {decisions_so_far} IC decisions so far (need 5 to unlock drift analysis)."
                )
        except Exception as e:
            log.warning(f"Behavioral drift analysis failed: {e}")

        try:
            # Loop 1b: screener feedback patterns
            patterns = await detect_patterns(db)
            if patterns:
                learning_lines.append(f"\nSCREENER FEEDBACK PATTERNS ({len(patterns)} detected):")
                for pat in patterns[:3]:
                    learning_lines.append(f"  - {pat['details']}")
            else:
                learning_lines.append("\nSCREENER FEEDBACK: No patterns yet (need 3+ consistent dismiss/promote actions).")
        except Exception as e:
            log.warning(f"Feedback pattern detection failed: {e}")

        try:
            # Pending proposals (scoped to current constitution)
            pending_proposals = db.get_pending_proposals(constitution_id=constitution_id)[:5] if hasattr(db, 'get_pending_proposals') else []
            if pending_proposals:
                learning_lines.append(f"\nPENDING PROPOSALS ({len(pending_proposals)}):")
                for prop in pending_proposals[:3]:
                    source = prop.get("source", "behavioral")
                    learning_lines.append(f"  - [{source.upper()}] {prop.get('proposal') or prop.get('description', '')}")
        except Exception as e:
            log.debug(f"Pending proposals fetch failed: {e}")

        try:
            # Loop 3: outcome tracking — how screened stocks actually performed (scoped to current strategy)
            active_version_id = constitution.get("active_version_id") if constitution else None
            outcomes = db.get_outcomes_for_strategy(strategy_version_id=active_version_id, limit=20) if hasattr(db, 'get_outcomes_for_strategy') else []
            if outcomes:
                alphas = [o.get('alpha_pct', 0) for o in outcomes if o.get('alpha_pct') is not None]
                avg_alpha = sum(alphas) / len(alphas) if alphas else 0
                positive_alpha = [a for a in alphas if a > 0]
                hit_rate = len(positive_alpha) / len(alphas) * 100 if alphas else 0
                learning_lines.append(
                    f"\nOUTCOME TRACKING ({len(outcomes)} outcomes): "
                    f"Avg alpha: {avg_alpha:+.1f}%. Hit rate: {hit_rate:.0f}% ({len(positive_alpha)}/{len(alphas)} beat benchmark). "
                    f"If relevant, share these stats — especially what thesis patterns are working."
                )
        except Exception as e:
            log.debug(f"Failed to fetch outcomes for conversation context: {e}")

        if learning_lines:
            learning_context = "\n".join(learning_lines)

    memory_store = get_memory()
    memory_context = memory_store.format_for_injection()

    messages = build_conversation_messages(body.message, history, strategy_for_prompt, agent_settings, learning_context, memory_context)

    try:
        from backend.scoring.strategy import (
            EXTRACTION_SYSTEM_PROMPT,
            STRATEGY_EXTRACTION_SCHEMA,
        )

        is_refinement = bool(strategy_for_prompt)
        extraction_system = EXTRACTION_SYSTEM_PROMPT + (
            "\n\nThis is a REFINEMENT conversation. Focus on extracting agent_actions for config changes."
            if is_refinement else
            "\n\nThis is a SETUP conversation. Focus on extracting strategy_profile when is_complete=true."
        )

        two_pass = await llm.generate_then_extract(
            messages=messages,
            extraction_system=extraction_system,
            extraction_schema=STRATEGY_EXTRACTION_SCHEMA,
            agent="strategy_conversation",
            reasoning_effort="medium",
            extraction_reasoning_effort="low",
        )

        log.info(f"Strategy Pass 1 ({len(two_pass.raw_text)} chars)")
        log.info(f"Strategy Pass 2 extracted keys: {list(two_pass.extracted.keys())}")

        # Always prefer raw Pass 1 text for fidelity
        two_pass.extracted["message"] = two_pass.raw_text
        parsed = parse_strategy_response(two_pass.raw_text, extracted=two_pass.extracted)

        # Clean raw JSON / agent_actions dumps from the conversational message.
        # The AI sometimes includes "Agent actions I submitted [...]" or raw JSON
        # blocks in its response. These are for the extraction layer, not the user.
        clean_msg = _strip_agent_actions_from_message(parsed["message"])

        response = {
            "message": clean_msg,
            "options": parsed["options"],
            "extracted": parsed["extracted"],
            "dimensions_complete": parsed["dimensions_complete"],
            "is_complete": parsed["is_complete"],
            "agent_actions": parsed.get("agent_actions", []),
            "session_id": session_id,
            "proposal_actions": [
                {"id": p["id"], "label": (p.get("proposal", "") or p.get("description", ""))[:60] + "..."}
                for p in (pending_proposals or [])[:3]
            ] if pending_proposals else [],
        }

        # Save the assistant response (with retry for DB lock)
        for _attempt in range(3):
            try:
                db.save_conversation_message(
                    session_id=session_id, role="assistant", content=parsed["message"],
                    constitution_id=constitution_id,
                    extracted=parsed.get("extracted"),
                )
                break
            except Exception as e:
                if "locked" in str(e) and _attempt < 2:
                    await asyncio.sleep(0.5)
                else:
                    log.warning(f"Failed to save assistant message: {e}")
                    break

        # Save memory updates from extraction
        memory_updates = parsed.get("memory_updates") or two_pass.extracted.get("memory_updates") or []
        if memory_updates:
            try:
                saved_ids = memory_store.save_from_extraction(memory_updates, session_id=session_id)
                log.info(f"Saved {len(saved_ids)} memory entries: {saved_ids}")
                response["memory_updates_saved"] = len(saved_ids)
            except Exception as e:
                log.warning(f"Memory save failed: {e}")

        # If strategy is complete, validate and auto-save directly to DB
        if parsed["is_complete"] and parsed["strategy_profile"]:
            profile = parsed["strategy_profile"]
            errors = validate_strategy_profile(profile)
            if errors:
                response["is_complete"] = False
                response["message"] += f"\n\n(Some dimensions need clarification: {', '.join(errors)})"
            else:
                response["strategy_profile"] = profile
                # Auto-save — don't rely on the frontend to call /strategy/save separately
                try:
                    strategy_id = create_strategy_id()
                    name = profile.get("north_star", "My Strategy")[:50]
                    agent_defaults = profile.get("agent_defaults", {})
                    ic_d = agent_defaults.get("ic_review", {})
                    alloc_d = agent_defaults.get("allocator", {})

                    db.create_constitution(
                        constitution_id=strategy_id,
                        name=name,
                        north_star=profile.get("north_star"),
                        north_star_summary=profile.get("north_star_summary"),
                        style_identity=profile.get("style_identity"),
                        time_horizon=profile.get("time_horizon"),
                        must_have_signals=profile.get("must_have_signals"),
                        anti_signals=profile.get("anti_signals"),
                        ic_hurdles={
                            "base_return_pct": ic_d.get("hurdle_base_pct", 20),
                            "bear_return_pct": ic_d.get("hurdle_bear_pct", 15),
                            "haircut_pct": ic_d.get("haircut_pct", 70),
                        } if ic_d else None,
                        disqualifiers=profile.get("disqualifiers"),
                        position_sizing={
                            "max_position_pct": alloc_d.get("max_position_pct", 15),
                            "concentration_limit_pct": alloc_d.get("concentration_limit_pct", 20),
                        } if alloc_d else None,
                        dimensions=profile.get("dimensions"),
                        sector_routing=profile.get("sector_routing"),
                        agent_profiles=agent_defaults if agent_defaults else None,
                        universe_type=profile.get("universe", {}).get("type", "preset"),
                        universe_name=profile.get("universe", {}).get("name", "us_largecap_200"),
                    )
                    universe_info = profile.get("universe", {})
                    db.create_strategy(
                        strategy_id=strategy_id,
                        name=name,
                        north_star=profile.get("north_star"),
                        dimensions=profile.get("dimensions"),
                        sector_routing=profile.get("sector_routing"),
                        universe_type=universe_info.get("type", "preset"),
                        universe_name=universe_info.get("name", "us_largecap_200"),
                    )
                    db.record_judgment_event(
                        event_type="constitution_created",
                        constitution_version=1,
                        agent="strategy_conversation",
                        data={"north_star": profile.get("north_star"),
                              "dimensions": list(profile.get("dimensions", {}).keys())},
                    )
                    response["strategy_saved"] = True
                    response["strategy_id"] = strategy_id
                    log.info(f"Auto-saved strategy {strategy_id}: {profile.get('north_star', '')[:60]}")

                    # Kick off scoring code generation in background and save result to DB
                    async def _generate_and_save(sid: str, prof: dict):
                        try:
                            result = await generate_scoring_code(llm, prof)
                            _db = _get_db()
                            version_row = _db.create_version(
                                version_id=result["version_id"],
                                strategy_id=sid,
                                version_number=1,
                                scoring_code=result["scoring_code"],
                                label_map=result["label_map"],
                                explanation=result["explanation"],
                                change_reason="Generated from strategy conversation",
                            )
                            # create_version already sets active_version_id; also update constitution
                            new_vid = version_row["id"] if version_row else None
                            try:
                                _db.update_constitution(
                                    sid,
                                    active_version_id=new_vid,
                                    _change_type="system",
                                    _change_summary="Scoring code generated from conversation",
                                    _trigger="codegen",
                                )
                            except Exception:
                                pass  # constitution row may not exist if save above failed
                            log.info(f"Scoring code generated and saved for strategy {sid}")
                        except Exception as cg_err:
                            log.warning(f"Background scoring codegen failed for {sid}: {cg_err}")

                    asyncio.create_task(_generate_and_save(strategy_id, profile))

                except Exception as save_err:
                    log.error(f"Auto-save strategy failed: {save_err}")
                    response["strategy_save_error"] = str(save_err)

        # Handle agent-specific actions (ongoing tuning, not strategy creation)
        # Persist changes to the constitution DB so they survive restarts and show in the modal
        if parsed.get("agent_actions"):
            applied = []
            action_db = _get_db()
            active_constitution = action_db.get_active_constitution()

            # Known screener filter and weight keys — used to auto-classify flat actions
            _SCREENER_FILTER_KEYS = {
                "gross_margin_pct", "revenue_growth_ttm_yoy", "revenue_cagr_3yr",
                "operating_margin_latest_pct", "net_margin", "roic", "roe",
                "fcf_yield", "rs_percentile_3m", "rs_percentile_6m",
                "debt_equity", "pe_ratio", "ev_ebitda", "revenue_not_declining",
                "positive_fcf_required", "price_above_50d_sma", "rsi_min", "rsi_max",
                "min_volume_ratio", "operating_margin_yoy_change_bps",
            }
            _SCREENER_WEIGHT_KEYS = {
                "momentum", "growth", "quality", "valuation", "cheapness",
                "technical", "fundamental", "value", "profitability",
            }
            _IC_KEYS = {
                "base_return_hurdle", "bear_return_hurdle", "bear_case_haircut",
                "hurdle_base_pct", "hurdle_bear_pct", "haircut_pct",
                "base_return_pct", "bear_return_pct",
            }
            _ALLOCATOR_KEYS = {
                "max_position_size_pct", "max_concentration_pct",
                "max_position_pct", "concentration_limit_pct",
                "min_expected_return_pct", "position_types",
                "core_compounder", "core", "tactical", "balanced",
            }
            _STRATEGY_KEYS = {
                "north_star", "north_star_summary", "style_identity",
                "time_horizon", "must_have_signals", "anti_signals",
                "disqualifiers", "dimensions", "sector_routing",
                "sell_discipline",
            }

            for action in parsed["agent_actions"]:
                agent_name = action.get("agent")
                changes = action.get("changes", {})

                # Handle simplified flat format: [{"gross_margin_pct": ">=50%"}]
                # If no "agent" key, infer target from the keys present
                if not agent_name:
                    keys = set(action.keys()) - {"action", "description", "reason"}
                    if keys & _SCREENER_FILTER_KEYS:
                        agent_name = "screener"
                        changes = {k: v for k, v in action.items()
                                   if k in _SCREENER_FILTER_KEYS or k in _SCREENER_WEIGHT_KEYS}
                    elif keys & _SCREENER_WEIGHT_KEYS:
                        agent_name = "screener"
                        changes = {k: v for k, v in action.items() if k in _SCREENER_WEIGHT_KEYS}
                    elif keys & _IC_KEYS:
                        agent_name = "ic_review"
                        changes = {k: v for k, v in action.items() if k in _IC_KEYS}
                    elif keys & _ALLOCATOR_KEYS:
                        agent_name = "allocator"
                        changes = {k: v for k, v in action.items() if k in _ALLOCATOR_KEYS}
                    elif keys & _STRATEGY_KEYS:
                        agent_name = "strategy"
                        changes = {k: v for k, v in action.items() if k in _STRATEGY_KEYS}

                if not agent_name or not changes:
                    continue

                applied.append(f"{agent_name}: {list(changes.keys())}")

                if not active_constitution:
                    continue
                cid = active_constitution["id"]

                if agent_name == "screener":
                    # Split changes into weights, filters, and config
                    WEIGHT_KEYS = {"momentum", "growth", "quality", "valuation", "cheapness",
                                   "technical", "fundamental", "value", "profitability"}
                    CONFIG_KEYS = {"candidate_cap", "pool_size", "sector_exclusions"}

                    # Unwrap nested format: {"filters": {...}, "weights": {...}}
                    if "filters" in changes and isinstance(changes["filters"], dict):
                        flat_filters = changes.pop("filters")
                        changes.update(flat_filters)
                    if "weights" in changes and isinstance(changes["weights"], dict):
                        flat_weights = changes.pop("weights")
                        changes.update(flat_weights)

                    weights_update = {k: v for k, v in changes.items()
                                      if k in WEIGHT_KEYS or k.endswith("_weight")}
                    config_update = {k: v for k, v in changes.items() if k in CONFIG_KEYS}
                    filters_update = {k: v for k, v in changes.items()
                                      if k not in WEIGHT_KEYS and not k.endswith("_weight") and k not in CONFIG_KEYS}

                    agent_profiles = dict(active_constitution.get("agent_profiles") or {})
                    screener_profile = dict(agent_profiles.get("screener") or {})
                    if weights_update:
                        screener_profile["weights"] = {**dict(screener_profile.get("weights") or {}), **weights_update}
                    if filters_update:
                        # Normalize filter keys: remove old keys that are synonyms of new ones
                        # e.g., updating gross_margin_floor should remove gross_margin_pct
                        _FILTER_SYNONYMS = {
                            "gross_margin": {"gross_margin_pct", "gross_margin_floor", "gross_margin_min"},
                            "roic": {"roic", "roic_floor", "roic_min"},
                            "net_margin": {"net_margin", "net_income_margin_floor", "net_margin_floor", "net_margin_min"},
                            "debt_equity": {"debt_equity", "debt_to_equity_limit", "debt_equity_max", "debt_limit"},
                            "revenue_growth": {"revenue_growth_floor", "revenue_growth_cagr_3y", "revenue_cagr_3yr"},
                        }
                        # Build reverse map: key → canonical group
                        _key_to_group = {}
                        for group, keys in _FILTER_SYNONYMS.items():
                            for k in keys:
                                _key_to_group[k] = group
                        # Find which groups are being updated
                        updated_groups = {_key_to_group.get(k) for k in filters_update.keys()} - {None}
                        # Remove old keys from those groups
                        existing_filters = dict(screener_profile.get("filters") or {})
                        for group in updated_groups:
                            for old_key in _FILTER_SYNONYMS.get(group, set()):
                                existing_filters.pop(old_key, None)
                        # Merge new values
                        screener_profile["filters"] = {**existing_filters, **filters_update}
                    if config_update:
                        screener_profile.update(config_update)
                    agent_profiles["screener"] = screener_profile
                    active_constitution = action_db.update_constitution(
                        cid, agent_profiles=agent_profiles,
                        _change_type="conversation",
                        _change_summary=f"Screener updated: {list(changes.keys())}",
                        _trigger="chat",
                    )
                    # Also persist config changes to workflow.yaml
                    if config_update:
                        try:
                            config = get_config()
                            scout_cfg = config.resolved.setdefault("agents", {}).setdefault("screener", {}).setdefault("config", {})
                            scout_cfg.update(config_update)
                            config.save_to_disk()
                        except Exception as e:
                            log.warning(f"Failed to persist screener config: {e}")
                    # Regenerate scoring code when weights or filters change
                    # Awaited with timeout so response isn't blocked if codegen retries
                    if weights_update or filters_update:
                        try:
                            await asyncio.wait_for(
                                _regenerate_scoring_code(
                                    cid, f"Screener updated: {list(changes.keys())}"
                                ),
                                timeout=30,
                            )
                        except asyncio.TimeoutError:
                            log.warning("Scoring code regeneration timed out (30s) — will retry on next run")

                elif agent_name in ("ic", "ic_review"):
                    IC_KEY_MAP = {
                        "hurdle_base_pct": "base_return_pct",
                        "hurdle_bear_pct": "bear_return_pct",
                        "base_return_hurdle": "base_return_pct",
                        "bear_return_hurdle": "bear_return_pct",
                        "base_return_pct": "base_return_pct",
                        "bear_return_pct": "bear_return_pct",
                        "haircut_pct": "haircut_pct",
                        "bear_case_haircut": "haircut_pct",
                        # Additional aliases the LLM sometimes uses
                        "bear_case_return_hurdle": "bear_return_pct",
                        "base_case_return_hurdle": "base_return_pct",
                        "bear_hurdle": "bear_return_pct",
                        "base_hurdle": "base_return_pct",
                    }
                    # IC hurdle keys → ic_hurdles column
                    hurdle_changes = {k: v for k, v in changes.items() if k in IC_KEY_MAP}
                    if hurdle_changes:
                        hurdles = dict(active_constitution.get("ic_hurdles") or {})
                        for k, v in hurdle_changes.items():
                            # Normalize: strip "%" suffix, convert to number
                            if isinstance(v, str):
                                v = v.replace("%", "").strip()
                                try:
                                    v = float(v)
                                    if v == int(v):
                                        v = int(v)
                                except ValueError:
                                    pass
                            hurdles[IC_KEY_MAP.get(k, k)] = v
                        active_constitution = action_db.update_constitution(
                            cid, ic_hurdles=hurdles,
                            _change_type="conversation",
                            _change_summary="IC hurdles updated via chat",
                            _trigger="chat",
                        )
                    # All other IC keys → agent_profiles.ic_review (discount_floors, ai_override, style_fit, etc.)
                    profile_changes = {k: v for k, v in changes.items() if k not in IC_KEY_MAP}
                    if profile_changes:
                        ap = dict(active_constitution.get("agent_profiles") or {})
                        ic_profile = dict(ap.get("ic_review") or {})
                        ic_profile.update(profile_changes)
                        ap["ic_review"] = ic_profile
                        active_constitution = action_db.update_constitution(
                            cid, agent_profiles=ap,
                            _change_type="conversation",
                            _change_summary=f"IC review settings updated: {list(profile_changes.keys())}",
                            _trigger="chat",
                    )

                elif agent_name == "allocator":
                    _PS_KEYS = {"max_position_pct", "concentration_limit_pct",
                                "min_position_pct", "max_sector_pct", "min_expected_return_pct"}
                    _PT_KEYS = {"position_types", "core_compounder", "core", "tactical",
                                "tactical_dislocation", "balanced"}
                    ps = dict(active_constitution.get("position_sizing") or {})
                    for k, v in changes.items():
                        if k in _PS_KEYS:
                            ps[k] = v
                    active_constitution = action_db.update_constitution(
                        cid, position_sizing=ps,
                        _change_type="conversation",
                        _change_summary="Allocator limits updated via chat",
                        _trigger="chat",
                    )
                    # Handle position type sizing (core, tactical, balanced ranges)
                    pt_changes = {}
                    if "position_types" in changes and isinstance(changes["position_types"], dict):
                        pt_changes = changes["position_types"]
                    else:
                        for k in _PT_KEYS - {"position_types"}:
                            if k in changes:
                                pt_changes[k] = changes[k]
                    # Handle position types + all other allocator profile keys generically
                    profile_keys = {k: v for k, v in changes.items() if k not in _PS_KEYS}
                    if profile_keys:
                        ap = dict(active_constitution.get("agent_profiles") or {})
                        alloc_profile = dict(ap.get("allocator") or {})
                        # Unwrap position_types dict
                        if "position_types" in profile_keys and isinstance(profile_keys["position_types"], dict):
                            existing_pt = dict(alloc_profile.get("position_types") or {})
                            existing_pt.update(profile_keys.pop("position_types"))
                            alloc_profile["position_types"] = existing_pt
                        # Unwrap action_triggers dict
                        if "action_triggers" in profile_keys and isinstance(profile_keys["action_triggers"], dict):
                            existing_at = dict(alloc_profile.get("action_triggers") or {})
                            existing_at.update(profile_keys.pop("action_triggers"))
                            alloc_profile["action_triggers"] = existing_at
                        # Flat position type keys → nest under position_types
                        for k in list(profile_keys.keys()):
                            if k in _PT_KEYS - {"position_types"}:
                                pt = dict(alloc_profile.get("position_types") or {})
                                pt[k] = profile_keys.pop(k)
                                alloc_profile["position_types"] = pt
                        # Flat trigger keys → nest under action_triggers
                        _TRIGGER_KEYS = {"add_trigger", "trim_trigger", "swap_trigger", "exit_trigger",
                                         "add", "trim", "swap", "exit"}
                        for k in list(profile_keys.keys()):
                            if k in _TRIGGER_KEYS:
                                at = dict(alloc_profile.get("action_triggers") or {})
                                clean_key = k.replace("_trigger", "")
                                at[clean_key] = profile_keys.pop(k)
                                alloc_profile["action_triggers"] = at
                        # Everything else goes directly to the profile
                        alloc_profile.update(profile_keys)
                        ap["allocator"] = alloc_profile
                        active_constitution = action_db.update_constitution(
                            cid, agent_profiles=ap,
                            _change_type="conversation",
                            _change_summary=f"Allocator updated: {list(changes.keys())}",
                            _trigger="chat",
                        )

                elif agent_name == "universe":
                    # Change the stock universe preset or custom tickers
                    preset = changes.get("preset")
                    custom = changes.get("custom_tickers")
                    update_kwargs: dict = {}
                    if preset:
                        update_kwargs["universe_type"] = "preset"
                        update_kwargs["universe_name"] = preset
                        update_kwargs["universe_custom"] = None
                    elif custom:
                        update_kwargs["universe_type"] = "custom"
                        update_kwargs["universe_custom"] = ",".join(custom) if isinstance(custom, list) else custom
                    if update_kwargs:
                        active_constitution = action_db.update_constitution(
                            cid, **update_kwargs,
                            _change_type="conversation",
                            _change_summary=f"Universe changed to {preset or 'custom'}",
                            _trigger="chat",
                        )
                        # NOTE: strategy_profiles table is legacy — constitution is the
                        # single source of truth for universe. No sync needed.
                        # Constitution is the single source of truth for universe.
                        # Screener reads it via _apply_universe() at runtime.

                elif agent_name in ("thesis", "memo", "portfolio"):
                    ap = dict(active_constitution.get("agent_profiles") or {})
                    profile = dict(ap.get(agent_name) or {})
                    # Deep-merge nested dicts instead of replacing them
                    for k, v in changes.items():
                        if isinstance(v, dict) and isinstance(profile.get(k), dict):
                            profile[k] = {**profile[k], **v}
                        else:
                            profile[k] = v
                    ap[agent_name] = profile
                    active_constitution = action_db.update_constitution(
                        cid, agent_profiles=ap,
                        _change_type="conversation",
                        _change_summary=f"{agent_name.title()} settings updated via chat",
                        _trigger="chat",
                    )

                elif agent_name in ("strategy", "constitution"):
                    # Strategy-level changes: north_star, must_have_signals, anti_signals,
                    # dimensions, style_identity, time_horizon, etc.
                    _STRATEGY_FIELDS = {
                        "north_star", "north_star_summary", "style_identity",
                        "time_horizon", "must_have_signals", "anti_signals",
                        "disqualifiers", "dimensions", "sector_routing",
                        "sell_discipline", "ic_hurdles",
                    }
                    update_kwargs_strat: dict = {}
                    for k, v in changes.items():
                        if k in _STRATEGY_FIELDS:
                            update_kwargs_strat[k] = v
                    if update_kwargs_strat:
                        changed_names = list(update_kwargs_strat.keys())
                        active_constitution = action_db.update_constitution(
                            cid, **update_kwargs_strat,
                            _change_type="conversation",
                            _change_summary=f"Strategy updated via chat: {', '.join(changed_names)}",
                            _trigger="chat",
                        )
                        # NOTE: strategy_profiles table is legacy — constitution is the
                        # single source of truth. No sync needed.
                        # Regenerate scoring code to reflect constitution changes
                        _SCORING_RELEVANT = {"dimensions", "must_have_signals", "anti_signals",
                                             "disqualifiers", "sector_routing", "north_star"}
                        if _SCORING_RELEVANT & set(changed_names):
                            try:
                                await asyncio.wait_for(
                                    _regenerate_scoring_code(
                                        cid, f"Constitution updated: {', '.join(changed_names)}"
                                    ),
                                    timeout=30,
                                )
                            except asyncio.TimeoutError:
                                log.warning("Scoring code regeneration timed out (30s) — will retry on next run")

            if applied:
                response["applied_actions"] = applied
                # Auto-resolve pending proposals since the AI discussed and applied changes
                try:
                    pending = action_db.get_pending_proposals(
                        constitution_id=active_constitution["id"] if active_constitution else None
                    )
                    for prop in (pending or []):
                        action_db.resolve_proposal(
                            prop["id"], "accepted",
                            applied_version_id=active_constitution.get("active_version_id") if active_constitution else None,
                        )
                    if pending:
                        log.info(f"Auto-resolved {len(pending)} proposals after chat-applied changes")
                except Exception as e:
                    log.debug(f"Auto-resolve proposals failed: {e}")

        return response

    except Exception as e:
        log.error(f"Strategy conversation failed: {e}")
        return {
            "message": f"Sorry, I had trouble processing that. Error: {str(e)}",
            "options": [],
            "extracted": {},
            "dimensions_complete": [],
            "is_complete": False,
            "session_id": session_id,
        }


# --- Strategy CRUD ---

@router.get("/strategy")
async def get_active_strategy():
    """Get the active strategy profile and constitution."""
    db = _get_db()
    strategy = db.get_active_strategy()
    constitution = db.get_active_constitution()

    if not strategy and not constitution:
        return {"strategy": None, "constitution": None, "has_strategy": False}

    # Get active version details
    version = None
    version_id = (constitution or {}).get("active_version_id") or (strategy or {}).get("active_version_id")
    if version_id:
        version = db.get_version(version_id)

    return {
        "strategy": strategy,
        "constitution": constitution,
        "version": version,
        "has_strategy": True,
    }


@router.get("/strategy/list")
async def list_strategies():
    """List all strategy profiles."""
    db = _get_db()
    return {"strategies": db.list_strategies()}


class SaveStrategyRequest(BaseModel):
    profile: dict
    name: Optional[str] = None


@router.post("/strategy/save")
async def save_strategy(body: SaveStrategyRequest):
    """Save a strategy profile from the conversation.

    Creates the constitution + legacy strategy in DB, triggers scoring code generation.
    The constitution is the primary object; strategy_profiles is kept for screener compat.
    """
    profile = body.profile
    errors = validate_strategy_profile(profile)
    if errors:
        raise HTTPException(400, f"Invalid strategy profile: {', '.join(errors)}")

    llm = get_llm()
    if not llm:
        raise HTTPException(503, "AI model not configured.")

    db = _get_db()

    strategy_id = create_strategy_id()
    name = body.name or profile.get("north_star", "My Strategy")[:50]

    # Extract constitution fields from the strategy conversation profile
    agent_defaults = profile.get("agent_defaults", {})
    ic_defaults = agent_defaults.get("ic_review", {})
    allocator_defaults = agent_defaults.get("allocator", {})
    portfolio_defaults = agent_defaults.get("portfolio", {})

    # Create the constitution (primary object)
    constitution = db.create_constitution(
        constitution_id=strategy_id,
        name=name,
        north_star=profile.get("north_star"),
        north_star_summary=profile.get("north_star_summary"),
        style_identity=profile.get("style_identity"),
        time_horizon=profile.get("time_horizon"),
        must_have_signals=profile.get("must_have_signals"),
        anti_signals=profile.get("anti_signals"),
        ic_hurdles={
            "base_return_pct": ic_defaults.get("hurdle_base_pct", 20),
            "bear_return_pct": ic_defaults.get("hurdle_bear_pct", 15),
            "haircut_pct": ic_defaults.get("haircut_pct", 70),
        } if ic_defaults else None,
        disqualifiers=profile.get("disqualifiers"),
        position_sizing={
            "max_position_pct": allocator_defaults.get("max_position_pct", 15),
            "concentration_limit_pct": allocator_defaults.get("concentration_limit_pct", 20),
        } if allocator_defaults else None,
        sell_discipline=profile.get("sell_discipline"),
        dimensions=profile.get("dimensions"),
        sector_routing=profile.get("sector_routing"),
        agent_profiles=agent_defaults if agent_defaults else None,
        universe_type=profile.get("universe", {}).get("type", "preset"),
        universe_name=profile.get("universe", {}).get("name", "us_largecap_200"),
    )

    # Also create legacy strategy_profiles entry for screener v2 compat
    universe_info = profile.get("universe", {})
    strategy = db.create_strategy(
        strategy_id=strategy_id,
        name=name,
        north_star=profile.get("north_star"),
        dimensions=profile.get("dimensions"),
        sector_routing=profile.get("sector_routing"),
        universe_type=universe_info.get("type", "preset"),
        universe_name=universe_info.get("name", "us_largecap_200"),
    )

    # Record the creation as a judgment event
    db.record_judgment_event(
        event_type="constitution_created",
        constitution_version=1,
        agent="strategy_conversation",
        data={"north_star": profile.get("north_star"), "dimensions": list(profile.get("dimensions", {}).keys())},
        rationale="Initial strategy creation from conversation",
    )

    # Generate scoring code
    try:
        codegen_result = await generate_scoring_code(llm, profile)

        version = db.create_version(
            version_id=codegen_result["version_id"],
            strategy_id=strategy_id,
            version_number=1,
            scoring_code=codegen_result["scoring_code"],
            label_map=codegen_result["label_map"],
            explanation=codegen_result["explanation"],
            change_reason="Initial strategy creation",
        )

        # create_version already sets active_version_id on strategy_profiles;
        # also update constitution for consistency
        new_vid = version["id"] if version else None
        try:
            db.update_constitution(strategy_id, active_version_id=new_vid,
                                   _change_type="system", _change_summary="Scoring code generated",
                                   _trigger="codegen")
        except Exception:
            pass

        return {
            "strategy": strategy,
            "constitution": constitution,
            "version": version,
            "explanation": codegen_result["explanation"],
            "scoring_code": codegen_result["scoring_code"],
        }

    except ScoringCodeError as e:
        log.error(f"Scoring code generation failed: {e}")
        return {
            "strategy": strategy,
            "constitution": constitution,
            "version": None,
            "error": str(e),
            "message": "Strategy saved but scoring code generation failed. You can retry from Settings.",
        }


@router.get("/strategy/{strategy_id}/versions")
async def get_strategy_versions(strategy_id: str):
    """Get version history for a strategy."""
    db = _get_db()
    versions = db.get_version_history(strategy_id)
    return {"versions": versions}


@router.post("/strategy/{strategy_id}/regenerate")
async def regenerate_scoring_code(strategy_id: str):
    """Regenerate scoring code for a strategy."""
    llm = get_llm()
    if not llm:
        raise HTTPException(503, "AI model not configured.")

    db = _get_db()
    strategy = db.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(404, "Strategy not found")

    profile = {
        "north_star": strategy["north_star"],
        "dimensions": strategy["dimensions"],
        "sector_routing": strategy["sector_routing"],
    }

    try:
        codegen_result = await generate_scoring_code(llm, profile)

        # Get next version number
        versions = db.get_version_history(strategy_id)
        next_version = (versions[0]["version_number"] + 1) if versions else 1

        version = db.create_version(
            version_id=codegen_result["version_id"],
            strategy_id=strategy_id,
            version_number=next_version,
            scoring_code=codegen_result["scoring_code"],
            label_map=codegen_result["label_map"],
            explanation=codegen_result["explanation"],
            change_reason="Regenerated scoring code",
        )

        # create_version already sets active_version_id on strategy_profiles;
        # also update constitution for consistency
        new_vid = version["id"] if version else None
        try:
            db.update_constitution(
                strategy_id,
                active_version_id=new_vid,
                _change_type="system",
                _change_summary="Scoring code regenerated",
                _trigger="regenerate",
            )
        except Exception:
            pass  # constitution row may not exist if strategy was legacy-created

        # Invalidate cache
        _scoring_cache.pop(codegen_result["version_id"], None)

        return {
            "version": version,
            "explanation": codegen_result["explanation"],
            "scoring_code": codegen_result["scoring_code"],
        }

    except ScoringCodeError as e:
        raise HTTPException(500, f"Code generation failed: {e}")


# --- Screener v2 Run ---

class ScreenerV2RunRequest(BaseModel):
    strategy_id: Optional[str] = None


@router.post("/screener/v2/run")
async def run_screener_v2(body: ScreenerV2RunRequest = ScreenerV2RunRequest()):
    """Run the screener using AI-generated scoring (async job queue).

    Submits the full pipeline (SEC enrichment + AI scoring) as a background job.
    Returns job_id immediately. Poll /jobs/{job_id} for status.
    Results available at /screener/v2/results when complete.
    """
    db = _get_db()

    # Get strategy (read from JSON body)
    strategy_id = body.strategy_id
    if strategy_id:
        strategy = db.get_strategy(strategy_id)
    else:
        strategy = db.get_active_strategy()

    if not strategy:
        raise HTTPException(400, "No strategy found. Create one first via the Strategy conversation.")

    if not strategy.get("active_version_id"):
        raise HTTPException(400, "No scoring code generated. Go to Settings > Strategy and save your strategy first.")

    # Get scoring code
    version = db.get_version(strategy["active_version_id"])
    if not version:
        raise HTTPException(500, "Scoring version not found in database.")

    version_id = version["id"]

    # Compile scoring code (cache it)
    if version_id not in _scoring_cache:
        try:
            score_fn = compile_scoring_function(version["scoring_code"])
            _scoring_cache[version_id] = score_fn
        except ScoringCodeError as e:
            raise HTTPException(500, f"Scoring code is invalid: {e}")

    score_fn = _scoring_cache[version_id]

    # Build the async job function
    from backend.agents.screener import ScreenerAgent
    from backend.api.deps import get_config as get_app_config, get_yfinance, get_sec, get_fmp, get_db as get_app_db, get_job_queue

    app_config = get_app_config()
    agent_config = app_config.resolved.get("agents", {}).get("screener", {}).get("config", {})

    # Use universe from strategy if set
    if strategy.get("universe_name"):
        agent_config = {**agent_config, "universe": strategy["universe_name"]}
    elif strategy.get("universe_custom"):
        custom = strategy["universe_custom"]
        if isinstance(custom, list):
            custom = ",".join(custom)
        agent_config = {**agent_config, "custom_tickers": custom}

    strategy_name = strategy.get("name", "Strategy")
    strategy_id_used = strategy["id"]

    async def v2_screener_job(ctx):
        progress = ctx.get("_update_progress", lambda msg: None)
        progress("Fetching universe...")

        screener = ScreenerAgent(
            config=agent_config,
            fmp=get_fmp(),
            yfinance=get_yfinance(),
            sec=get_sec(),
            db=get_app_db(),
        )

        context = {"strategy_id": strategy_id_used}
        screener_result = await screener.run(context)

        if not screener_result.ok:
            raise Exception(f"Data collection failed: {'; '.join(screener_result.errors)}")

        stocks = screener_result.data.get("all_scored", [])
        if not stocks:
            stocks = screener_result.data.get("handoff_candidates", [])

        progress(f"Scoring {len(stocks)} stocks with {strategy_name}...")

        scoring_result = execute_scoring(score_fn, stocks)

        # Save run to DB
        top_results = scoring_result["results"][:20]

        run_db = _get_db()
        run_id = run_db.record_screener_run(
            strategy_version_id=version_id,
            universe_size=screener_result.data.get("universe_size", len(stocks)),
            scored_count=scoring_result["scored_count"],
            failed_count=scoring_result["failed_count"],
            top_results=top_results,
            all_results=scoring_result["results"],
            duration_s=0,
            status=scoring_result["status"],
        )

        progress(f"Done — {scoring_result['scored_count']} stocks scored")

        return type("Result", (), {
            "data": {
                "run_id": run_id,
                "scored_count": scoring_result["scored_count"],
                "failed_count": scoring_result["failed_count"],
                "status": scoring_result["status"],
                "strategy_name": strategy_name,
            },
            "ok": True,
        })()

    jobs = get_job_queue()
    job_id = await jobs.submit("screener", v2_screener_job, {})
    return {"job_id": job_id, "status": "running", "strategy_name": strategy_name}


# --- Feedback ---

class FeedbackRequest(BaseModel):
    screener_run_id: str
    ticker: str
    feedback: str  # "promoted", "thumbs_up", "thumbs_down", "dismissed"
    dismiss_reason: Optional[str] = None
    note: Optional[str] = None
    score_at_feedback: Optional[float] = None
    rank_at_feedback: Optional[int] = None


@router.post("/screener/v2/feedback")
async def record_feedback(body: FeedbackRequest):
    """Record user feedback on a screener result.

    Also records a judgment event for the feedback loop.
    """
    valid_feedback = {"promoted", "thumbs_up", "thumbs_down", "dismissed"}
    if body.feedback not in valid_feedback:
        raise HTTPException(400, f"Invalid feedback type. Must be one of: {valid_feedback}")

    db = _get_db()
    db.record_feedback(
        screener_run_id=body.screener_run_id,
        ticker=body.ticker,
        feedback=body.feedback,
        dismiss_reason=body.dismiss_reason,
        note=body.note,
        score_at_feedback=body.score_at_feedback,
        rank_at_feedback=body.rank_at_feedback,
    )

    # Record judgment event
    constitution = db.get_active_constitution()
    event_type = "promoted" if body.feedback == "promoted" else "dismissed" if body.feedback == "dismissed" else "feedback"
    db.record_judgment_event(
        event_type=event_type,
        ticker=body.ticker,
        constitution_version=constitution["version"] if constitution else None,
        agent="user",
        data={
            "feedback": body.feedback,
            "dismiss_reason": body.dismiss_reason,
            "note": body.note,
            "score": body.score_at_feedback,
            "rank": body.rank_at_feedback,
            "screener_run_id": body.screener_run_id,
        },
        rationale=body.note or body.dismiss_reason,
    )

    return {"saved": True}


@router.get("/screener/v2/feedback/{run_id}")
async def get_run_feedback(run_id: str):
    """Get all feedback for a screener run."""
    db = _get_db()
    feedback = db.get_feedback_for_run(run_id)
    return {"feedback": feedback}


# --- Screener v2 Results ---

@router.get("/screener/v2/results")
async def get_latest_results():
    """Get results from the most recent screener v2 run."""
    db = _get_db()
    runs = db.get_runs_by_strategy(limit=1)
    if not runs:
        return {"results": [], "run_id": None, "label_map": {}}

    run = db.get_screener_run(runs[0]["id"])
    if not run:
        return {"results": [], "run_id": None, "label_map": {}}

    # Get label map from the version
    version = db.get_version(run["strategy_version_id"])
    label_map = version.get("label_map", {}) if version else {}

    # Get feedback for this run
    feedback = db.get_feedback_for_run(run["id"])
    feedback_map = {f["ticker"]: f for f in feedback}

    # Merge feedback into results
    results = run.get("all_results") or run.get("top_results") or []
    for r in results:
        ticker = r.get("ticker")
        if ticker in feedback_map:
            r["feedback"] = feedback_map[ticker]["feedback"]
            r["dismiss_reason"] = feedback_map[ticker].get("dismiss_reason")

    return {
        "results": results,
        "run_id": run["id"],
        "label_map": label_map,
        "scored_count": run.get("scored_count", 0),
        "failed_count": run.get("failed_count", 0),
        "status": run.get("status"),
        "run_at": run.get("run_at"),
    }


# --- Constitution API ---

@router.get("/constitution")
async def get_constitution():
    """Get the active constitution."""
    db = _get_db()
    constitution = db.get_active_constitution()
    if not constitution:
        return {"constitution": None, "has_constitution": False}
    return {"constitution": constitution, "has_constitution": True}


@router.get("/constitution/changelog")
async def get_constitution_changelog():
    """Get the constitution's evolution history."""
    db = _get_db()
    constitution = db.get_active_constitution()
    if not constitution:
        return {"changelog": []}
    changelog = db.get_changelog(constitution["id"])
    return {"changelog": changelog, "constitution_id": constitution["id"]}


# --- Judgment Events API ---

@router.get("/events/ticker/{ticker}")
async def get_ticker_events(ticker: str):
    """Get all judgment events for a ticker (the decision chain)."""
    db = _get_db()
    events = db.get_events_by_ticker(ticker)
    return {"events": events, "ticker": ticker}


@router.get("/events/chain/{event_id}")
async def get_event_chain(event_id: int):
    """Walk the event chain from root to the specified event."""
    db = _get_db()
    chain = db.get_event_chain(event_id)
    return {"chain": chain}


@router.get("/events/recent")
async def get_recent_events(limit: int = 100):
    """Get recent judgment events across all tickers."""
    db = _get_db()
    events = db.get_recent_events(limit=limit)
    return {"events": events}


# --- Conversation History ---

@router.get("/strategy/conversation/history")
async def get_conversation_history(strategy_id: str = None, session_id: str = None):
    """Load persisted conversation history.

    Returns the most recent conversation session so the UI can resume where it left off.
    """
    db = _get_db()

    if session_id:
        history = db.get_conversation_history(session_id=session_id)
        return {"history": history, "session_id": session_id}

    # Auto-detect: find latest session for this strategy or active constitution
    constitution = db.get_active_constitution()
    constitution_id = strategy_id or (constitution.get("id") if constitution else None)

    if constitution_id:
        latest_session = db.get_latest_session_id(constitution_id)
        if latest_session:
            history = db.get_conversation_history(session_id=latest_session)
            return {"history": history, "session_id": latest_session}

    return {"history": [], "session_id": None}


# --- Library ---

@router.get("/library/similar/{ticker}")
async def find_similar_library(ticker: str, sector: str = None,
                                gross_margin: float = None, roic: float = None):
    """Find similar researched names in the library."""
    db = _get_db()
    results = db.find_similar(
        ticker=ticker, sector=sector,
        gross_margin=gross_margin, roic=roic,
    )
    return {"similar": results, "ticker": ticker}


@router.get("/library/ticker/{ticker}")
async def get_library_ticker(ticker: str):
    """Get full research file for a ticker — enriched for the Library Browse tab.

    Transforms raw library entries into the TickerResearch shape the frontend expects:
    assumptions, timeline, fundamentals, predictions, feedback patterns.
    """
    import json as _json
    from backend.api.deps import get_db as _get_main_db

    db = _get_db()
    main_db = _get_main_db()
    entries = db.get_library_by_ticker(ticker)

    # Get all agent runs for this ticker to build the timeline and enrich data
    all_runs = main_db.get_runs_for_ticker(ticker) if hasattr(main_db, 'get_runs_for_ticker') else []

    # If no library entries AND no agent runs, nothing to show
    if not entries and not all_runs:
        return {"entries": [], "ticker": ticker}

    # Parse latest thesis and IC review for rich data
    thesis_data = {}
    ic_data = {}
    for run in (all_runs if isinstance(all_runs, list) else []):
        agent = run.get("agent", "")
        if agent == "thesis" and not thesis_data:
            try:
                fo = run.get("full_output")
                thesis_data = _json.loads(fo) if isinstance(fo, str) else (fo or {})
            except Exception:
                pass
        elif agent == "ic_review" and not ic_data:
            try:
                fo = run.get("full_output")
                parsed = _json.loads(fo) if isinstance(fo, str) else (fo or {})
                # Skip override-only entries
                if parsed.get("ai_review") or parsed.get("base_return") is not None:
                    ic_data = parsed
            except Exception:
                pass

    # Latest entry for header data — fall back to agent_runs if no library entries
    latest = entries[0] if entries else (all_runs[0] if all_runs else {})
    first = entries[-1] if entries else (all_runs[-1] if all_runs else latest)

    # Enrich sector/industry from thesis or entries
    entry_sector = latest.get("sector") or thesis_data.get("sector") or ""
    entry_industry = latest.get("industry") or thesis_data.get("industry") or ""
    company_name = thesis_data.get("company_name") or ticker

    # Build assumptions from IC review key_assumptions
    assumptions = []
    ic_assumptions = ic_data.get("key_assumptions") or []
    if isinstance(ic_assumptions, str):
        try:
            ic_assumptions = _json.loads(ic_assumptions)
        except Exception:
            ic_assumptions = [ic_assumptions]
    for a in (ic_assumptions if isinstance(ic_assumptions, list) else []):
        text = a if isinstance(a, str) else a.get("assumption", str(a))
        assumptions.append({
            "assumption": text,
            "predicted": "monitoring",
            "actual": "—",
            "status": "intact",  # Default to intact until outcome tracking runs
            "delta": "",
        })

    # Build return predictions from thesis + IC data
    return_predictions = []
    thesis_return = thesis_data.get("expected_return")
    thesis_fv = thesis_data.get("fair_value")
    ic_base = ic_data.get("base_return")
    ic_bear = ic_data.get("bear_return")
    ic_base_sources = ic_data.get("return_sources_base", {})
    ic_bear_sources = ic_data.get("return_sources_bear", {})

    if thesis_return is not None or ic_base is not None:
        return_predictions.append({
            "metric": "Expected Return",
            "thesis": f"{thesis_return:.0f}%" if thesis_return is not None else "—",
            "icBear": f"{ic_bear:.0f}%" if ic_bear is not None else "—",
            "icBase": f"{ic_base:.0f}%" if ic_base is not None else "—",
            "actual": "—",
        })
    if thesis_fv is not None:
        price = thesis_data.get("price") or thesis_data.get("current_price")
        return_predictions.append({
            "metric": "Fair Value",
            "thesis": f"${thesis_fv:.0f}",
            "icBear": "—",
            "icBase": "—",
            "actual": f"${price:.0f}" if price else "—",
        })
    disc = thesis_data.get("discount_pct") or ic_data.get("discount_pct")
    if disc is not None:
        return_predictions.append({
            "metric": "Discount to FV",
            "thesis": f"{disc:.0f}%",
            "icBear": "—",
            "icBase": "—",
            "actual": "—",
        })
    # Return source decomposition — merge thesis + IC stress-tested sources
    thesis_sources = thesis_data.get("return_sources", {})
    # Map keys across thesis (discount_closing, growth, margin_expansion, dividends)
    # and IC (discount, growth, margin, dividends)
    source_mapping = [
        ("Discount Closing", ["discount_closing", "discount"], "discount", "discount"),
        ("Growth", ["growth"], "growth", "growth"),
        ("Margin Expansion", ["margin_expansion", "margin"], "margin", "margin"),
        ("Dividends", ["dividends"], "dividends", "dividends"),
    ]
    for label, thesis_keys, bear_key, base_key in source_mapping:
        thesis_val = None
        for tk in thesis_keys:
            thesis_val = thesis_sources.get(tk)
            if thesis_val is not None:
                break
        bear_val = ic_bear_sources.get(bear_key)
        base_val = ic_base_sources.get(base_key)
        if any(v is not None and v != 0 for v in [thesis_val, bear_val, base_val]):
            return_predictions.append({
                "metric": label,
                "thesis": f"{thesis_val:.1f}%" if thesis_val is not None else "—",
                "icBear": f"{bear_val:.1f}%" if bear_val is not None else "—",
                "icBase": f"{base_val:.1f}%" if base_val is not None else "—",
                "actual": "—",
            })

    # Also get judgment events (thesis_generated, ic_passed, ic_failed) from v2 DB
    judgment_events = []
    try:
        judgment_events = db.get_events_by_ticker(ticker) or []
    except Exception:
        pass

    # Build timeline from agent runs + judgment events — include full content for reading
    timeline = []

    # Add judgment events first (thesis, IC verdicts)
    for jev in (judgment_events if isinstance(judgment_events, list) else []):
        event_type = jev.get("event_type", "")
        agent_name = jev.get("agent", event_type)
        jev_data = jev.get("data", {})
        if isinstance(jev_data, str):
            try:
                jev_data = _json.loads(jev_data)
            except Exception:
                jev_data = {}

        # Map event_type to display type
        display_type = {
            "thesis_generated": "thesis",
            "ic_passed": "ic_review",
            "ic_failed": "ic_review",
            "memo_completed": "memo",
            "thesis_alert": "alert",
        }.get(event_type, event_type)

        verdict_val = jev_data.get("verdict") or ("PASS" if "passed" in event_type else "NO_PASS" if "failed" in event_type else None)

        entry: dict = {
            "type": display_type,
            "date": (jev.get("created_at") or "")[:10],
            "dotColor": "var(--positive)" if verdict_val == "PASS" else "var(--negative)" if verdict_val == "NO_PASS" else "var(--text-muted)",
            "typeColor": {"thesis": "var(--info)", "ic_review": "var(--positive)", "memo": "var(--accent)", "alert": "var(--warning)"}.get(display_type, "var(--text-muted)"),
            "summary": jev.get("rationale", "") or f"{event_type}",
            "verdict": verdict_val.lower() if verdict_val else None,
        }

        # Enrich with data fields and readable content
        if display_type == "ic_review" and jev_data:
            entry["conviction"] = jev_data.get("conviction")
            base_ret = jev_data.get("base_return")
            bear_ret = jev_data.get("bear_return")
            if base_ret is not None:
                entry["returns"] = f"Base {base_ret:.0f}% / Bear {bear_ret:.0f}%"
            entry["meta"] = f"conv {jev_data.get('conviction', '?')}/5"
            # Add full IC review content from agent_runs data
            if ic_data.get("ai_review"):
                entry["icContent"] = ic_data["ai_review"]
            scorecard = ic_data.get("constitution_scorecard", {})
            if scorecard:
                met = len(scorecard.get("signals_met", []))
                missed = len(scorecard.get("signals_missed", []))
                anti = len(scorecard.get("anti_signals_triggered", []))
                entry["scorecard"] = f"{met} met, {missed} missed, {anti} anti-signals"

        elif display_type == "thesis" and jev_data:
            entry["meta"] = f"FV ${jev_data.get('fair_value', 0):.0f}, {jev_data.get('expected_return', 0):.0f}% exp return" if jev_data.get("fair_value") else None
            # Add full thesis narrative from agent_runs data
            narrative = thesis_data.get("thesis_narrative") or thesis_data.get("variant_view") or ""
            if narrative:
                entry["thesisContent"] = narrative
            # Add structured quality + return data
            quality = thesis_data.get("quality", {})
            returns = thesis_data.get("return_sources", {})
            if quality or returns:
                structured = []
                if quality:
                    structured.append({
                        "label": "Quality Metrics",
                        "rows": [{"key": k, "value": f"{v:.1f}%" if isinstance(v, (int, float)) else str(v)} for k, v in quality.items()],
                    })
                if returns:
                    structured.append({
                        "label": "Return Sources",
                        "rows": [{"key": k, "value": f"{v:.1f}%"} for k, v in returns.items()],
                    })
                entry["structuredData"] = structured

        timeline.append(entry)

    # Then add agent_runs (memos, screener runs, etc.)
    for run in (all_runs if isinstance(all_runs, list) else []):
        agent = run.get("agent", "")
        run_type = run.get("run_type", "")
        if run_type in ("job_start", "job_complete"):
            continue
        verdict = run.get("verdict")
        summary = run.get("summary", "")[:200] if run.get("summary") else ""

        # Parse full_output for content
        full_output = {}
        try:
            fo = run.get("full_output")
            full_output = _json.loads(fo) if isinstance(fo, str) else (fo or {})
        except Exception:
            pass

        entry: dict = {
            "type": agent,
            "date": (run.get("run_at") or "")[:10],
            "dotColor": "var(--positive)" if verdict == "PASS" else "var(--negative)" if verdict == "NO_PASS" else "var(--text-muted)",
            "typeColor": {
                "screener": "var(--text-muted)",
                "thesis": "var(--info)",
                "ic_review": "var(--positive)",
                "memo": "var(--accent)",
            }.get(agent, "var(--text-muted)"),
            "summary": summary or f"{agent} run",
            "verdict": verdict.lower() if verdict else None,
        }

        # Add readable content based on agent type
        if agent == "thesis" and full_output:
            narrative = full_output.get("thesis_narrative") or full_output.get("variant_view") or ""
            if narrative:
                entry["thesisContent"] = narrative
            entry["meta"] = f"FV ${full_output.get('fair_value', 0):.0f}, {full_output.get('expected_return', 0):.0f}% exp return" if full_output.get("fair_value") else None
            # Structured data for thesis
            quality = full_output.get("quality", {})
            returns = full_output.get("return_sources", {})
            if quality or returns:
                structured = []
                if quality:
                    structured.append({
                        "label": "Quality Metrics",
                        "rows": [{"key": k, "value": f"{v:.1f}%" if isinstance(v, (int, float)) else str(v)} for k, v in quality.items()],
                    })
                if returns:
                    structured.append({
                        "label": "Return Sources",
                        "rows": [{"key": k, "value": f"{v:.1f}%"} for k, v in returns.items()],
                    })
                entry["structuredData"] = structured

        elif agent == "ic_review" and full_output:
            ai_review = full_output.get("ai_review", "")
            base_ret = full_output.get("base_return")
            bear_ret = full_output.get("bear_return")
            conviction = full_output.get("conviction")
            if ai_review:
                entry["icContent"] = ai_review
            if base_ret is not None:
                entry["returns"] = f"Base {base_ret:.0f}% / Bear {bear_ret:.0f}%"
            if conviction is not None:
                entry["conviction"] = conviction
            scorecard = full_output.get("constitution_scorecard", {})
            if scorecard:
                met = len(scorecard.get("signals_met", []))
                missed = len(scorecard.get("signals_missed", []))
                anti = len(scorecard.get("anti_signals_triggered", []))
                entry["scorecard"] = f"{met} met, {missed} missed, {anti} anti-signals"

        elif agent == "memo" and full_output:
            # Memo content — link to the Memos tab
            char_count = len(str(full_output.get("content", ""))) or len(str(full_output))
            cost = full_output.get("cost", 0)
            entry["summary"] = f"{run_type or 'memo'}, {char_count:,} chars, ${cost:.2f}" if cost else f"{run_type or 'memo'}, {char_count:,} chars"
            entry["actions"] = [{"label": "Read in Memos tab", "style": "amber", "onClick": "memos-inv" if "investment" in (run_type or "") else "memos-res"}]

        elif agent == "screener" and full_output:
            scores = full_output.get("scores", {})
            if scores:
                entry["structuredData"] = [{
                    "label": "Screener Scores",
                    "rows": [{"key": k, "value": f"{v:.1f}" if isinstance(v, (int, float)) else str(v)} for k, v in scores.items()],
                }]

        timeline.append(entry)

    # Build fundamentals from thesis quality data
    fundamentals = []
    quality = thesis_data.get("quality") or {}
    for label, key in [("Gross Margin", "gross_margin"), ("ROIC", "roic"),
                       ("ROE", "roe"), ("D/E", "debt_equity"), ("FCF Yield", "fcf_yield")]:
        val = quality.get(key) or latest.get(key)
        if val is not None:
            if "margin" in key or "roic" in key or "roe" in key or "yield" in key:
                display = f"{val:.1f}%"
            else:
                display = f"{val:.2f}"
            fundamentals.append({
                "metric": label,
                "expected": display,
                "quarters": [],
                "trend": "→",
                "trendColor": "var(--text-muted)",
            })

    return {
        "entries": entries,
        "ticker": ticker,
        # TickerResearch shape for the Browse tab
        "name": company_name,
        "status": "researched",
        "sector": entry_sector,
        "industry": entry_industry,
        "firstResearched": (first.get("created_at") or first.get("run_at") or "")[:10],
        "latestActivity": (latest.get("created_at") or latest.get("run_at") or "")[:10],
        "artifactCount": len(entries) or len(all_runs),
        "stageCount": len(set(e.get("entry_type", "") or e.get("agent", "") for e in (entries or all_runs))),
        "priceAtFirst": None,
        "priceNow": None,
        "returnPct": None,
        "assumptions": assumptions,
        "predictionAccuracy": "—",
        "returnPredictions": return_predictions,
        "timeline": timeline,
        "fundamentals": fundamentals,
        "feedbackPatterns": [],
        "refinementProposals": [],
        "behavioralSignals": [],
    }


@router.get("/library/stats")
async def get_library_stats():
    """Get library summary statistics."""
    db = _get_db()
    stats = db.get_library_stats()
    return stats


# --- Feedback Loop (Loop 1: Preference Alignment) ---

@router.get("/strategy/refinement-proposals")
async def get_refinement_proposals():
    """Get pending refinement proposals from feedback patterns.

    The system detects patterns in user feedback (dismissals, promotions)
    and proposes scoring code changes. This endpoint returns those proposals.
    """
    db = _get_db()
    constitution = db.get_active_constitution()

    # Detect patterns from feedback
    from backend.learning.feedback_loop import detect_patterns
    patterns = await detect_patterns(db)

    # Get existing pending proposals
    pending = db.get_pending_proposals(
        constitution_id=constitution["id"] if constitution else None
    )

    # Get proposal acceptance stats (for autonomy graduation context)
    stats = db.get_proposal_stats()

    return {
        "proposals": pending,
        "detected_patterns": [
            {"type": p["type"], "tag": p["tag"], "count": p["count"],
             "details": p["details"], "tickers": p["tickers"][:5]}
            for p in patterns
        ],
        "stats": stats,
    }


@router.post("/strategy/refinement-proposals/generate")
async def generate_refinement_proposals():
    """Detect feedback patterns and generate refinement proposals.

    Runs pattern detection, then generates AI proposals for each actionable pattern.
    """
    llm = get_llm()
    if not llm:
        raise HTTPException(503, "AI model not configured.")

    db = _get_db()
    constitution = db.get_active_constitution()

    # Detect patterns
    from backend.learning.feedback_loop import detect_patterns, propose_refinement
    patterns = await detect_patterns(db)

    if not patterns:
        return {"proposals": [], "message": "No actionable patterns found in feedback yet."}

    # Get current scoring code
    current_code = ""
    if constitution and constitution.get("active_version_id"):
        version = db.get_version(constitution["active_version_id"])
        if version:
            current_code = version.get("scoring_code", "")

    if not current_code:
        return {"proposals": [], "message": "No scoring code found. Generate one first."}

    # Generate proposals for each pattern
    proposals = []
    for pattern in patterns:
        proposal = await propose_refinement(llm, pattern, current_code, constitution)

        # Store in DB
        stored = db.store_proposal(
            proposal_id=proposal["id"],
            constitution_id=constitution["id"] if constitution else None,
            pattern_type=proposal["pattern"]["type"],
            pattern_tag=proposal["pattern"]["tag"],
            pattern_count=proposal["pattern"]["count"],
            pattern_tickers=proposal["pattern"]["tickers"],
            proposal=proposal["proposal"],
            analysis=proposal.get("analysis", ""),
            code_change=proposal.get("code_change", ""),
            confidence=proposal["confidence"],
            risk=proposal.get("risk", ""),
            evidence_summary=proposal["evidence_summary"],
        )

        # Record judgment event
        db.record_judgment_event(
            event_type="refinement_proposed",
            constitution_version=constitution["version"] if constitution else None,
            agent="feedback_loop",
            data={
                "proposal_id": proposal["id"],
                "pattern_type": proposal["pattern"]["type"],
                "confidence": proposal["confidence"],
            },
            rationale=proposal["proposal"],
        )

        proposals.append(stored)

    return {"proposals": proposals, "patterns_found": len(patterns)}


@router.post("/strategy/refinement-proposals/{proposal_id}/accept")
async def accept_refinement(proposal_id: str):
    """Accept a refinement proposal and create a new strategy version.

    Generates updated scoring code incorporating the proposed change.
    """
    llm = get_llm()
    if not llm:
        raise HTTPException(503, "AI model not configured.")

    db = _get_db()
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    if proposal["status"] != "pending":
        raise HTTPException(400, f"Proposal already resolved: {proposal['status']}")

    constitution = db.get_active_constitution()
    if not constitution or not constitution.get("active_version_id"):
        raise HTTPException(400, "No active strategy version to modify")

    # Get current code
    version = db.get_version(constitution["active_version_id"])
    current_code = version["scoring_code"]

    # Generate refined code
    from backend.learning.feedback_loop import generate_refined_code
    new_code = await generate_refined_code(llm, current_code, proposal)

    if not new_code:
        # Fall back to full regeneration with the proposal as context
        raise HTTPException(500, "Could not generate valid refined code. Try regenerating from scratch.")

    # Get strategy for version tracking
    strategy = db.get_strategy(constitution["id"])
    if not strategy:
        raise HTTPException(500, "Strategy not found for this constitution")

    # Create new version
    versions = db.get_version_history(constitution["id"])
    next_version = (versions[0]["version_number"] + 1) if versions else 1
    import uuid as uuid_mod
    version_id = f"v-{uuid_mod.uuid4().hex[:8]}"

    new_version = db.create_version(
        version_id=version_id,
        strategy_id=constitution["id"],
        version_number=next_version,
        scoring_code=new_code,
        label_map=version.get("label_map"),  # Keep existing labels
        explanation=f"Refined: {proposal['proposal']}",
        change_reason=f"Feedback loop: {proposal['proposal']}",
    )
    new_vid = new_version["id"] if new_version else None

    # Update constitution
    db.update_constitution(
        constitution["id"],
        active_version_id=new_vid,
        _change_type="feedback",
        _change_summary=proposal["proposal"],
        _trigger=f"proposal:{proposal_id}",
    )

    # Resolve proposal
    db.resolve_proposal(proposal_id, "accepted", applied_version_id=version_id)

    # Record judgment events
    db.record_judgment_event(
        event_type="refinement_accepted",
        constitution_version=constitution["version"],
        agent="user",
        data={"proposal_id": proposal_id, "new_version_id": version_id},
        rationale=f"Accepted: {proposal['proposal']}",
    )

    # Clear scoring cache
    _scoring_cache.pop(version_id, None)

    return {
        "accepted": True,
        "new_version": new_version,
        "proposal": proposal,
    }


@router.post("/strategy/refinement-proposals/{proposal_id}/reject")
async def reject_refinement(proposal_id: str):
    """Reject a refinement proposal."""
    db = _get_db()
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    if proposal["status"] != "pending":
        raise HTTPException(400, f"Proposal already resolved: {proposal['status']}")

    db.resolve_proposal(proposal_id, "rejected")

    constitution = db.get_active_constitution()
    db.record_judgment_event(
        event_type="refinement_rejected",
        constitution_version=constitution["version"] if constitution else None,
        agent="user",
        data={"proposal_id": proposal_id},
        rationale=f"Rejected: {proposal['proposal']}",
    )

    return {"rejected": True, "proposal_id": proposal_id}


# --- Behavioral Calibration (Loop 2: Said vs Did) ---

@router.get("/strategy/mirror")
async def get_behavioral_mirror():
    """The Mirror — compare constitution with actual behavior.

    Returns drift analysis: stated preferences vs revealed preferences,
    approval profile statistics, and style drift notes.
    """
    db = _get_db()
    constitution = db.get_active_constitution()
    if not constitution:
        return {"error": "No constitution found", "has_enough_data": False}

    from backend.learning.behavioral import analyze_drift
    drift = await analyze_drift(db, constitution)

    return {
        "constitution": {
            "style_identity": constitution.get("style_identity"),
            "north_star": constitution.get("north_star"),
            "must_have_signals": constitution.get("must_have_signals"),
            "anti_signals": constitution.get("anti_signals"),
            "ic_hurdles": constitution.get("ic_hurdles"),
            "version": constitution.get("version"),
        },
        "drift": drift,
    }


@router.post("/strategy/mirror/propose-update")
async def propose_behavioral_update():
    """Based on detected drift, propose a constitution update.

    The system decides: should the constitution change to match behavior,
    or should the investor tighten discipline?
    """
    llm = get_llm()
    if not llm:
        raise HTTPException(503, "AI model not configured.")

    db = _get_db()
    constitution = db.get_active_constitution()
    if not constitution:
        raise HTTPException(400, "No constitution found")

    from backend.learning.behavioral import analyze_drift, propose_constitution_update
    drift = await analyze_drift(db, constitution)

    if not drift.get("has_enough_data"):
        return {"proposal": None, "message": drift.get("summary", "Not enough data yet.")}

    proposal = await propose_constitution_update(llm, drift, constitution)
    if not proposal:
        return {"proposal": None, "message": "No significant drift detected. Constitution matches behavior."}

    # Record as judgment event
    db.record_judgment_event(
        event_type="behavioral_drift_detected",
        constitution_version=constitution["version"],
        agent="behavioral_calibration",
        data={
            "direction": proposal["direction"],
            "proposal": proposal["proposal"],
            "changes": proposal.get("changes", {}),
        },
        rationale=proposal["proposal"],
    )

    return {"proposal": proposal, "drift": drift}


@router.post("/strategy/mirror/apply-update")
async def apply_behavioral_update(body: dict):
    """Apply a behavioral constitution update.

    Updates specific constitution fields based on the behavioral proposal.
    """
    db = _get_db()
    constitution = db.get_active_constitution()
    if not constitution:
        raise HTTPException(400, "No constitution found")

    changes = body.get("changes", {})
    if not changes:
        raise HTTPException(400, "No changes provided")

    # Only allow updating constitution fields
    allowed_fields = {
        "must_have_signals", "anti_signals", "ic_hurdles", "style_identity",
        "disqualifiers", "position_sizing", "concentration_rules", "sell_discipline",
    }
    filtered = {k: v for k, v in changes.items() if k in allowed_fields}
    if not filtered:
        raise HTTPException(400, "No valid constitution fields in changes")

    updated = db.update_constitution(
        constitution["id"],
        **filtered,
        _change_type="behavioral",
        _change_summary=body.get("proposal", "Behavioral calibration update"),
        _trigger="mirror",
    )

    db.record_judgment_event(
        event_type="constitution_updated",
        constitution_version=updated["version"],
        agent="user",
        data={"changes": filtered, "trigger": "behavioral_calibration"},
        rationale=body.get("proposal", "Applied behavioral drift correction"),
    )

    return {"updated": True, "constitution": updated}


@router.post("/strategy/reset")
async def reset_constitution():
    """Delete constitution, strategy, and conversation history. Preserves library + judgment events."""
    db = _get_db()
    deleted = db.reset_constitution()

    # Clear in-memory caches so the system starts fresh
    global _scoring_cache
    _scoring_cache.clear()

    # Clear the config's cached constitution reference
    try:
        config = get_config()
        config.resolved.pop("active_constitution", None)
        config.resolved.pop("constitution", None)
    except Exception:
        pass

    return {"reset": True, "deleted": deleted}
