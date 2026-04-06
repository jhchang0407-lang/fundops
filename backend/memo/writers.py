"""
Async LLM Section Writers — Stage 3 of the pipeline.

Handles the 3-stage writing dependency chain:
  Stage 3A: Research agents (parallel) — uses 10-K/10-Q filing text
  Stage 3B: Body sections 2-11, 13 (parallel) — after 3A merge
  Stage 3C: Synthesis sections 12, 1, 14 (parallel) — reads full memo body

Uses OpenAI models (gpt-4o, gpt-5-mini, etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Optional

from config.settings import (
    OPENAI_API_KEY,
    WRITER_MODEL,
    RESEARCH_AGENT_MODEL,
)
from pipeline.sanitize import sanitize_for_llm


def _round_floats(obj: Any, ndigits: int = 2) -> Any:
    """Recursively round all float values to *ndigits* decimal places.

    Ensures the LLM never sees floating-point artefacts like 11.254999999999999
    or spurious extra decimals in median values (30.305 → 30.31).
    """
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(item, ndigits) for item in obj]
    return obj


# ── LLM CLIENT INITIALIZATION ────────────────────────────────

_REASONING_MODEL_PREFIXES = ("o1", "o3", "gpt-5")


def _is_reasoning_model(model: str) -> bool:
    """Check if a model is a reasoning model (no temperature, no max_tokens)."""
    return any(model.startswith(p) for p in _REASONING_MODEL_PREFIXES)


async def _call_openai(
    messages: list[dict],
    model: str = "gpt-4o",
    temperature: float = 0.4,
    max_tokens: int = 4096,
    response_format: dict | None = None,
) -> dict:
    """Call OpenAI API asynchronously."""
    import openai

    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

    kwargs = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_tokens,
    }

    # Reasoning models (o1, o3, gpt-5*) don't support custom temperature
    if not _is_reasoning_model(model):
        kwargs["temperature"] = temperature

    if response_format:
        kwargs["response_format"] = response_format

    response = await client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content

    # Try to parse as JSON
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"raw_text": content}


async def call_llm(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 4096,
    response_format: dict | None = None,
    system: str = "",
) -> dict:
    """Call LLM (OpenAI models only)."""
    model = model or WRITER_MODEL

    # Prepend system message if provided (OpenAI uses system role)
    if system:
        messages = [{"role": "system", "content": system}] + messages

    return await _call_openai(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )


# ── SECTION WRITER ────────────────────────────────────────────

async def write_section(
    section_input: dict,
    model: str | None = None,
) -> dict:
    """Write a single memo section using LLM.

    Args:
        section_input: Dict with keys:
            section_number, section_title, company_name, ticker,
            word_target, schema, context, template, qualitative_inputs
        model: Override model name

    Returns:
        Dict with section output (structured JSON from LLM)
    """
    model = model or WRITER_MODEL
    section_num = section_input.get("section_number", 0)
    section_title = section_input.get("section_title", "")
    company_name = section_input.get("company_name", "")
    ticker = section_input.get("ticker", "")
    word_target = section_input.get("word_target", "500-700 words")
    min_words = section_input.get("min_words", 0)
    schema = section_input.get("schema", {})
    template = section_input.get("template", "")

    # Context can come from "context" (synthesis sections) or "facts" (body sections)
    context = section_input.get("context", "")
    facts = section_input.get("facts", {})
    qualitative = section_input.get("qualitative_inputs", "")
    quant_inputs = section_input.get("quant_inputs", "")
    quant_inputs_formatted = section_input.get("quant_inputs_formatted", "")

    # Build the user message
    user_parts = [
        f"## Section {section_num}: {section_title}",
        f"**Company:** {company_name} ({ticker})",
        f"**Target length:** {word_target}",
    ]

    if schema:
        user_parts.append(
            f"\n### Output JSON Schema\n```json\n{json.dumps(schema, indent=2)}\n```"
        )

    if template:
        user_parts.append(f"\n### Writing Template\n{template}")

    # Inject quantitative facts from distributor via the unified sanitation layer.
    # Writers should only see human-readable labels + already-formatted values.
    if facts and isinstance(facts, dict):
        facts_str = json.dumps(_round_floats(sanitize_for_llm(facts)), indent=2, default=str)
        # Limit to 12K chars to stay within context
        if len(facts_str) > 12000:
            facts_str = facts_str[:12000] + "\n... [truncated]"
        user_parts.append(f"\n### Quantitative Facts\n```json\n{facts_str}\n```")

    # Inject any precomputed table data
    precomputed_keys = [
        k for k in section_input
        if k.startswith("precomputed_") and section_input[k]
    ]
    for pk in precomputed_keys:
        label = pk.replace("precomputed_", "").replace("_", " ").title()
        pk_data = section_input[pk]
        if isinstance(pk_data, (list, dict)):
            pk_str = json.dumps(_round_floats(sanitize_for_llm(pk_data)), indent=2, default=str)
            if len(pk_str) > 6000:
                pk_str = pk_str[:6000] + "\n... [truncated]"
            user_parts.append(f"\n### {label}\n```json\n{pk_str}\n```")

    if context:
        ctx_humanized = sanitize_for_llm(context) if isinstance(context, dict) else context
        ctx_str = ctx_humanized if isinstance(ctx_humanized, str) else json.dumps(ctx_humanized, indent=2, default=str)
        if len(ctx_str) > 15000:
            ctx_str = ctx_str[:15000] + "\n... [truncated]"
        user_parts.append(f"\n### Context\n{ctx_str}")

    if qualitative:
        qual_humanized = sanitize_for_llm(qualitative) if isinstance(qualitative, dict) else qualitative
        qual_str = qual_humanized if isinstance(qual_humanized, str) else json.dumps(qual_humanized, indent=2, default=str)
        if len(qual_str) > 8000:
            qual_str = qual_str[:8000] + "\n... [truncated]"
        user_parts.append(f"\n### Qualitative Research\n{qual_str}")

    if quant_inputs_formatted:
        qi_humanized = sanitize_for_llm(quant_inputs_formatted) if isinstance(quant_inputs_formatted, dict) else quant_inputs_formatted
        qi_str = qi_humanized if isinstance(qi_humanized, str) else json.dumps(qi_humanized, indent=2, default=str)
        user_parts.append(f"\n### Additional Quantitative Inputs\n{qi_str}")
    elif quant_inputs:
        qi_humanized = sanitize_for_llm(quant_inputs) if isinstance(quant_inputs, dict) else quant_inputs
        qi_str = qi_humanized if isinstance(qi_humanized, str) else json.dumps(qi_humanized, indent=2, default=str)
        user_parts.append(f"\n### Additional Quantitative Inputs\n{qi_str}")

    user_parts.append(
        "\nRespond with a single JSON object matching the Output JSON Schema above. "
        "Do not include any text outside the JSON."
    )

    user_message = "\n\n".join(user_parts)

    system_prompt = (
        f"You are a senior equity research analyst writing Section {section_num} "
        f"({section_title}) of an investment memo for {company_name} ({ticker}). "
        "Write in a professional, analytical tone. Use specific data and figures. "
        "All financial figures are pre-formatted — use them as-is in prose. "
        f"SECTION LENGTH GUIDE: {word_target}. The full memo targets 12,000-15,000 words total. "
        "Write with analytical depth — go deeper where the data is interesting or differentiated. "
        "Each subsection should be substantive paragraphs with specific numbers and analysis. "
        "Do NOT be terse — this is a sell-side research memo, not a summary. "
        "IMPORTANT: Focus on metrics that are UNIQUELY relevant to this section's topic. "
        "Do not repeat general company stats (total revenue, gross margin, etc.) that belong in other sections. "
        "Return your response as a JSON object matching the provided schema."
    )

    messages = [{"role": "user", "content": user_message}]

    t0 = time.time()
    try:
        result = await call_llm(
            messages=messages,
            model=model,
            temperature=0.4,
            max_tokens=8192,
            system=system_prompt,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        result = {
            "error": f"{type(e).__name__}: {e}",
            "section_number": section_num,
        }

    # ── Minimum word count check with retry ───────────────────
    if min_words and isinstance(result, dict) and "error" not in result:
        def _collect_prose(obj):
            """Recursively collect prose strings from nested dicts/lists."""
            parts = []
            if isinstance(obj, str) and len(obj) > 30:
                parts.append(obj)
            elif isinstance(obj, dict):
                for v in obj.values():
                    parts.extend(_collect_prose(v))
            elif isinstance(obj, list):
                for item in obj:
                    parts.extend(_collect_prose(item))
            return parts

        prose = " ".join(_collect_prose(result))
        actual_words = len(prose.split())
        if actual_words < min_words:
            # Retry once with a stronger length prompt
            retry_msg = (
                f"\n\nYour previous response was only ~{actual_words} words of prose. "
                f"The MINIMUM for this section is {min_words} words. "
                f"Rewrite with significantly more depth, detail, and analysis. "
                f"Expand every subsection — add more data points, comparisons, "
                f"historical context, and forward-looking analysis."
            )
            retry_messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": json.dumps(result, indent=2, default=str)[:2000]},
                {"role": "user", "content": retry_msg},
            ]
            try:
                result = await call_llm(
                    messages=retry_messages,
                    model=model,
                    temperature=0.5,
                    max_tokens=8192,
                    system=system_prompt,
                    response_format={"type": "json_object"},
                )
            except Exception:
                pass  # Keep original result on retry failure

    duration = time.time() - t0

    return {
        "section_number": section_num,
        "section_title": section_title,
        "output": result,
        "duration_s": duration,
        "model": model,
    }


# ── RESEARCH AGENT WRITER ────────────────────────────────────

async def call_research_agent(
    agent_number: int,
    prompt_text: str,
    model: str | None = None,
) -> dict:
    """Call a research agent with 10-K/10-Q context.

    Args:
        agent_number: 1, 2, or 3
        prompt_text: Full rendered prompt (from Jinja2 template)
        model: Override model name

    Returns:
        Dict with agent output
    """
    model = model or RESEARCH_AGENT_MODEL

    messages = [{"role": "user", "content": prompt_text}]

    t0 = time.time()
    try:
        result = await call_llm(
            messages=messages,
            model=model,
            temperature=0.3,
            max_tokens=8192,
            system=(
                f"You are Research Agent {agent_number}, a senior equity research analyst. "
                "Your job is to conduct thorough fundamental analysis using the SEC filing "
                "data provided below. Use the 10-K/10-Q text as your PRIMARY data source. "
                "Only reference external sources for: (a) current events post-filing date, "
                "(b) industry reports not in filings, (c) competitor analysis."
            ),
        )
    except Exception as e:
        result = {
            "error": f"{type(e).__name__}: {e}",
            "agent_number": agent_number,
        }

    return {
        "agent_number": agent_number,
        "output": result,
        "duration_s": time.time() - t0,
        "model": model,
    }


# ── 3-STAGE WRITING PIPELINE ─────────────────────────────────

async def write_all_sections(
    fact_sheet: dict,
    section_inputs: dict,
    filing_text: dict | None = None,
    include_pricing: bool = True,
    writer_model: str | None = None,
    agent_model: str | None = None,
) -> dict:
    """Execute the full 3-stage writing pipeline.

    Stage 3A: Research agents (parallel) — 3 agents
    Stage 3B: Body sections 2-11, 13 (parallel)
    Stage 3C: Synthesis sections 12, 1, 14 (parallel — reads full body)

    Args:
        fact_sheet: Formatted quantitative fact sheet
        section_inputs: Dict of section inputs from distribute_sections()
        filing_text: Filing text dict with 10-K/10-Q for agents
        include_pricing: Include price targets and recommendations
        writer_model: Override writer model
        agent_model: Override research agent model

    Returns:
        Dict with all section outputs and timing data
    """
    timings = {}
    errors = []

    # ── STAGE 3A: RESEARCH AGENTS ─────────────────────────────
    t3a = time.time()
    agent_prompts = section_inputs.get("agent_prompts", {})

    if agent_prompts:
        agent_results = await asyncio.gather(
            call_research_agent(1, agent_prompts.get("agent_1", ""), model=agent_model),
            call_research_agent(2, agent_prompts.get("agent_2", ""), model=agent_model),
            call_research_agent(3, agent_prompts.get("agent_3", ""), model=agent_model),
            return_exceptions=True,
        )

        # Merge qualitative outputs
        qualitative_data = {}
        for result in agent_results:
            if isinstance(result, Exception):
                errors.append(f"Agent error: {result}")
                continue
            if isinstance(result, dict) and "output" in result:
                qualitative_data[f"agent_{result['agent_number']}"] = result["output"]
    else:
        agent_results = []
        qualitative_data = {}

    timings["stage_3a_agents"] = time.time() - t3a

    # ── STAGE 3B: BODY SECTIONS ───────────────────────────────
    t3b = time.time()
    body_section_nums = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13]
    body_inputs = []

    for num in body_section_nums:
        key = f"section_{num}"
        if key in section_inputs:
            inp = section_inputs[key].copy()
            # Inject qualitative data
            if qualitative_data:
                inp["qualitative_inputs"] = json.dumps(sanitize_for_llm(qualitative_data), indent=2)[:8000]

                # Enrich Section 9 with growth_drivers from agent_1 so the
                # writer has seed topics for medium_term_drivers (the fact
                # sheet key s9_growth_prospects is never populated, so
                # without this the writer receives an empty list).
                if num == 9:
                    agent1 = qualitative_data.get("agent_1", {})
                    if isinstance(agent1, dict):
                        gd = agent1.get("growth_drivers", [])
                        if gd and isinstance(gd, list):
                            facts = inp.get("facts", {})
                            qual = facts.get("qualitative", {})
                            if isinstance(qual, dict) and not qual.get("medium_term_drivers"):
                                qual["medium_term_driver_topics"] = [
                                    d for d in gd if isinstance(d, str)
                                ]
                                facts["qualitative"] = qual
                                inp["facts"] = facts
            body_inputs.append(inp)

    # Also include quarterly writer if present
    if "quarterly" in section_inputs:
        body_inputs.append(section_inputs["quarterly"])

    if body_inputs:
        body_results = await asyncio.gather(
            *[write_section(inp, model=writer_model) for inp in body_inputs],
            return_exceptions=True,
        )
    else:
        body_results = []

    timings["stage_3b_body"] = time.time() - t3b

    # ── ASSEMBLE PARTIAL MEMO FOR SYNTHESIS ────────────────────
    section_outputs = {}
    for result in body_results:
        if isinstance(result, Exception):
            errors.append(f"Body section error: {result}")
            continue
        if isinstance(result, dict):
            section_outputs[f"section_{result['section_number']}"] = result

    # Build partial memo body for synthesis sections to read
    partial_memo = _assemble_partial_memo(section_outputs)

    # ── STAGE 3C: SYNTHESIS SECTIONS ──────────────────────────
    t3c = time.time()
    synthesis_nums = [12, 1, 14]
    synthesis_inputs = []

    for num in synthesis_nums:
        key = f"section_{num}"
        if key in section_inputs:
            inp = section_inputs[key].copy()
            inp["context"] = partial_memo
            inp["context_description"] = (
                "Complete memo body — sections 2 through 13. "
                "Read all before writing your section."
            )
            if qualitative_data:
                inp["qualitative_inputs"] = json.dumps(sanitize_for_llm(qualitative_data), indent=2)[:8000]
            synthesis_inputs.append(inp)

    if synthesis_inputs:
        synthesis_results = await asyncio.gather(
            *[write_section(inp, model=writer_model) for inp in synthesis_inputs],
            return_exceptions=True,
        )
    else:
        synthesis_results = []

    for result in synthesis_results:
        if isinstance(result, Exception):
            errors.append(f"Synthesis section error: {result}")
            continue
        if isinstance(result, dict):
            section_outputs[f"section_{result['section_number']}"] = result

    timings["stage_3c_synthesis"] = time.time() - t3c

    return {
        "section_outputs": section_outputs,
        "agent_results": [
            r for r in agent_results
            if isinstance(r, dict)
        ] if agent_results else [],
        "qualitative_data": qualitative_data,
        "timings": timings,
        "errors": errors,
    }


def _assemble_partial_memo(section_outputs: dict) -> str:
    """Combine body section outputs into a single memo string.

    Used as context for synthesis sections (12, 1, 14).
    """
    parts = []
    for num in sorted(
        int(k.replace("section_", ""))
        for k in section_outputs
        if k.startswith("section_")
    ):
        result = section_outputs.get(f"section_{num}", {})
        output = result.get("output", {})
        title = result.get("section_title", f"Section {num}")

        # Extract text from structured output
        if isinstance(output, dict):
            # Try to find the main text content
            text = output.get("raw_text", "")
            if not text:
                text = output.get("section_text", "")
            if not text:
                text = output.get("content", "")
            if not text:
                # Fallback: serialize the whole thing
                text = json.dumps(output, indent=2)
        else:
            text = str(output)

        parts.append(f"## Section {num}: {title}\n\n{text}")

    return "\n\n---\n\n".join(parts)


# ── PROSE FACT-CHECK LAYER (C1) ─────────────────────────────────

_fact_check_logger = logging.getLogger("fundops.memo.writers")

# Regex to find numbers in prose: integers, decimals, with optional commas,
# optional leading $, optional trailing % or B/M suffix.
_NUMBER_PATTERN = re.compile(
    r"(?<!\w)"               # not preceded by a word char
    r"\$?"                   # optional dollar sign
    r"(\d[\d,]*\.?\d*)"     # digits with optional commas and decimal
    r"\s*"                   # optional whitespace
    r"(%|[BbMm]\b)?"        # optional percent or B/M suffix
    r"(?!\w)"               # not followed by a word char
)

# Keyword → fact_sheet key fragments mapping for matching prose context
# to fact_sheet metrics.
_KEYWORD_MAP: dict[str, list[str]] = {
    "revenue":       ["revenue"],
    "gross margin":  ["gross_margin"],
    "gross profit":  ["gross_profit"],
    "operating margin": ["operating_margin"],
    "ebitda margin": ["ebitda_margin"],
    "net margin":    ["net_margin", "net_profit_margin"],
    "roic":          ["roic"],
    "roe":           ["roe", "return_on_equity"],
    "roa":           ["roa", "return_on_assets"],
    "growth":        ["growth"],
    "eps":           ["eps"],
    "fcf":           ["fcf", "free_cash_flow"],
    "free cash flow": ["fcf", "free_cash_flow"],
    "dividend":      ["dividend"],
    "capex":         ["capex"],
    "debt":          ["debt"],
    "interest":      ["interest"],
    "shares":        ["shares", "share_count"],
    "market cap":    ["market_cap"],
    "ev":            ["ev_to", "enterprise_value"],
    "p/e":           ["price_to_earnings"],
    "price to earnings": ["price_to_earnings"],
}


def _flatten_fact_sheet(d: Any, prefix: str = "") -> dict[str, float]:
    """Recursively flatten a fact_sheet dict into {dotted_key: numeric_value}.

    Only includes leaves that are numeric (int or float, not None/NaN).
    """
    result: dict[str, float] = {}
    if d is None:
        return result
    if isinstance(d, dict):
        for k, v in d.items():
            new_key = f"{prefix}.{k}" if prefix else str(k)
            result.update(_flatten_fact_sheet(v, new_key))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            new_key = f"{prefix}[{i}]"
            result.update(_flatten_fact_sheet(v, new_key))
    elif isinstance(d, (int, float)):
        import math as _math
        if not _math.isnan(d) and not _math.isinf(d):
            result[prefix] = float(d)
    return result


def _parse_number(raw: str, suffix: str | None) -> tuple[float | None, bool]:
    """Parse a captured number string into a float.

    Returns (value, is_percentage).
    ``is_percentage`` is True when the number was followed by '%'.
    Large-suffix handling: 'B' → billions, 'M' → millions.
    """
    try:
        cleaned = raw.replace(",", "")
        value = float(cleaned)
    except ValueError:
        return None, False

    is_pct = suffix == "%"
    if suffix and suffix.upper() == "B":
        value *= 1_000_000_000
    elif suffix and suffix.upper() == "M":
        value *= 1_000_000
    return value, is_pct


def _extract_context_words(text: str, match_start: int, match_end: int, window: int = 10) -> str:
    """Return up to *window* words on each side of the match position."""
    before = text[:match_start].split()[-window:]
    after = text[match_end:].split()[:window]
    return " ".join(before + after).lower()


def _find_matching_metric(
    context: str,
    value: float,
    is_pct: bool,
    flat_facts: dict[str, float],
) -> tuple[str, float] | None:
    """Find the best matching fact_sheet metric for a prose number.

    Returns (metric_key, actual_value) or None if no clear match.
    """
    # Determine which keywords appear in the surrounding context
    matched_fragments: list[str] = []
    for keyword, fragments in _KEYWORD_MAP.items():
        if keyword in context:
            matched_fragments.extend(fragments)

    if not matched_fragments:
        return None

    # Search the flat fact_sheet for keys containing any matched fragment
    candidates: list[tuple[str, float]] = []
    for key, fact_value in flat_facts.items():
        key_lower = key.lower()
        for frag in matched_fragments:
            if frag in key_lower:
                candidates.append((key, fact_value))
                break

    if not candidates:
        return None

    # Compare the prose value against each candidate.
    # For percentages: prose "45.2%" means 45.2.  Fact sheet may store
    # as 45.2 (already pct) or 0.452 (decimal).  Try both.
    best: tuple[str, float, float] | None = None  # (key, actual, deviation)

    for key, fact_value in candidates:
        if fact_value == 0:
            continue

        # Direct comparison
        dev = abs(value - fact_value) / abs(fact_value)

        # If prose is a percentage, also try comparing against fact_value * 100
        # (in case fact_sheet stores decimals like 0.452 for 45.2%)
        if is_pct and abs(fact_value) < 1.0:
            alt_dev = abs(value - fact_value * 100) / abs(fact_value * 100)
            if alt_dev < dev:
                dev = alt_dev
                fact_value = fact_value * 100  # normalize for reporting

        # If prose is NOT pct but fact_sheet key has "pct" — compare value vs fact_value
        # (both should be in same unit already from flat sheet)

        if best is None or dev < best[2]:
            best = (key, fact_value, dev)

    if best is None:
        return None

    # Only return if there's a plausible match — allow up to 200% deviation
    # so we can catch large hallucinations (e.g. prose says 15% but actual is 8%).
    # The caller decides whether the deviation exceeds tolerance.
    if best[2] <= 2.0:
        return (best[0], best[1])

    return None


def fact_check_section(
    section_text: str,
    fact_sheet: dict,
    tolerance: float = 0.05,
) -> list[str]:
    """Extract all numbers from prose, cross-check against fact_sheet.

    Args:
        section_text: The prose text of one memo section.
        fact_sheet: The structured quantitative fact sheet from quantitative.py.
        tolerance: Maximum allowed fractional deviation (default 5%).

    Returns:
        List of violation messages.  Empty list means all checks passed.
    """
    if not section_text or not fact_sheet:
        return []

    flat_facts = _flatten_fact_sheet(fact_sheet)
    if not flat_facts:
        return []

    violations: list[str] = []

    for match in _NUMBER_PATTERN.finditer(section_text):
        raw_num = match.group(1)
        suffix = match.group(2)
        value, is_pct = _parse_number(raw_num, suffix)
        if value is None:
            continue

        # Skip year-like numbers (1900-2099) that aren't percentages/dollars
        if not suffix and 1900 <= value <= 2099 and value == int(value):
            continue

        context = _extract_context_words(section_text, match.start(), match.end())
        result = _find_matching_metric(context, value, is_pct, flat_facts)
        if result is None:
            continue

        metric_key, actual_value = result

        # Compute deviation
        if actual_value == 0:
            continue
        deviation = abs(value - actual_value) / abs(actual_value)

        if deviation > tolerance:
            # Build the prose snippet for context
            snippet_start = max(0, match.start() - 30)
            snippet_end = min(len(section_text), match.end() + 30)
            prose_snippet = section_text[snippet_start:snippet_end].replace("\n", " ").strip()

            msg = (
                f"Prose says '{prose_snippet}' ({value}) but fact sheet shows "
                f"{metric_key}: {actual_value} ({deviation:.1%} deviation)"
            )
            violations.append(msg)
            _fact_check_logger.warning("Fact-check violation: %s", msg)

    return violations


def cross_section_coherence_check(sections: dict[str, str]) -> list[str]:
    """Verify that the same metric has the same value across all sections.

    Args:
        sections: Dict mapping section name/id to its prose text.

    Returns:
        List of warning messages for cross-section inconsistencies.
    """
    if not sections or len(sections) < 2:
        return []

    # Build per-section index: {section_name: {metric_keyword: [values]}}
    section_metrics: dict[str, dict[str, list[float]]] = {}

    for section_name, text in sections.items():
        if not text:
            continue
        metrics: dict[str, list[float]] = {}

        for match in _NUMBER_PATTERN.finditer(text):
            raw_num = match.group(1)
            suffix = match.group(2)
            value, is_pct = _parse_number(raw_num, suffix)
            if value is None:
                continue

            context = _extract_context_words(text, match.start(), match.end())

            # Identify which metric keyword this number relates to
            for keyword in _KEYWORD_MAP:
                if keyword in context:
                    # Normalize: store percentage values as-is (e.g. 45.2 for "45.2%")
                    key = keyword + ("_pct" if is_pct else "")
                    metrics.setdefault(key, []).append(value)

        section_metrics[section_name] = metrics

    # Cross-compare: find metrics that appear in multiple sections with
    # different values
    warnings: list[str] = []
    all_metric_keys: set[str] = set()
    for m in section_metrics.values():
        all_metric_keys.update(m.keys())

    for metric_key in sorted(all_metric_keys):
        # Collect (section_name, value) pairs across all sections
        appearances: list[tuple[str, float]] = []
        for section_name, metrics in section_metrics.items():
            for v in metrics.get(metric_key, []):
                appearances.append((section_name, v))

        if len(appearances) < 2:
            continue

        # Check all pairs across different sections
        seen_pairs: set[tuple[str, str]] = set()
        for i, (sec_a, val_a) in enumerate(appearances):
            for j, (sec_b, val_b) in enumerate(appearances):
                if i >= j:
                    continue
                if sec_a == sec_b:
                    continue
                pair_key = (min(sec_a, sec_b), max(sec_a, sec_b))
                if pair_key in seen_pairs:
                    continue
                if val_a != val_b:
                    # Use display-friendly metric name
                    display_name = metric_key.replace("_pct", "").replace("_", " ")
                    suffix = "%" if metric_key.endswith("_pct") else ""
                    msg = (
                        f"Inconsistency: '{display_name}' is "
                        f"{val_a}{suffix} in {sec_a} but "
                        f"{val_b}{suffix} in {sec_b}"
                    )
                    warnings.append(msg)
                    seen_pairs.add(pair_key)
                    _fact_check_logger.warning("Cross-section: %s", msg)

    return warnings
