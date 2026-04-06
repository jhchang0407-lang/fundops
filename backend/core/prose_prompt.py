"""Prose System Prompt Builder — converts ProseSpec into LLM system prompts.

Single function that replaces all hardcoded system prompt strings across agents.

Usage:
    from backend.core.prose_prompt import build_prose_system_prompt
    from backend.core.prose_spec import THESIS_SPEC

    system = build_prose_system_prompt(THESIS_SPEC, company="Apollo", ticker="APO")
    result = await llm.generate(prompt=..., system=system)
"""

from __future__ import annotations

from backend.core.prose_spec import ProseSpec


def build_prose_system_prompt(
    spec: ProseSpec,
    company: str = "",
    ticker: str = "",
    data_constraints: str = "",
    strategy_lens: str = "",
    memory_context: str = "",
) -> str:
    """Convert a ProseSpec into a complete system prompt string.

    Args:
        spec: The prose quality specification.
        company: Company name (injected into persona).
        ticker: Stock ticker (injected into persona).
        data_constraints: Data availability block (from _build_data_constraints).
        strategy_lens: Strategy emphasis block (from _build_strategy_lens).
        memory_context: Persistent memory block (from MemoryStore.format_for_injection).

    Returns:
        Complete system prompt string for LLMClient.generate(system=...).
    """
    sections: list[str] = []

    # ── 1. ROLE & PERSONA ──
    persona = spec.persona
    if company and ticker:
        persona = persona.replace("a structured", f"a structured {company} ({ticker})")
        if "{company}" in persona:
            persona = persona.replace("{company}", company)
        if "{ticker}" in persona:
            persona = persona.replace("{ticker}", ticker)
    sections.append(persona)

    # ── 2. WRITING RULES ──
    rules: list[str] = []
    if spec.require_markdown:
        rules.append("Use markdown formatting throughout.")
    if spec.require_section_headers:
        rules.append("Structure content with ### subsection headers. Each section must have 2-4 distinct subsections.")
    if spec.require_bold_for_key_metrics:
        rules.append("Use **bold** for company names, key metrics, and important figures.")
    if spec.require_bullet_lists:
        rules.append("Use bullet lists (- item) when listing 3+ items of the same type.")
    if spec.require_tables_for_comparisons:
        rules.append(
            "Use markdown tables for comparisons of 3+ items across 2+ dimensions. "
            "Format: | Col1 | Col2 | Col3 |\\n|---|---|---|\\n| val | val | val |"
        )
    if spec.max_paragraph_sentences > 0:
        rules.append(
            f"Keep paragraphs to {spec.max_paragraph_sentences} sentences max. "
            f"Break long analysis into multiple paragraphs separated by blank lines."
        )

    if rules:
        sections.append("FORMATTING RULES:\n" + "\n".join(f"- {r}" for r in rules))

    # ── 3. FORBIDDEN PATTERNS ──
    if spec.forbidden_phrases:
        # Group for readability — show representative examples, not all 40+
        examples = list(spec.forbidden_phrases[:12])
        sections.append(
            "STRICTLY FORBIDDEN in your output:\n"
            + "\n".join(f'- "{p}"' for p in examples)
            + "\n- Any variant of addressing the reader as 'you' or referencing yourself as 'I'"
            + "\n- Any offer to do further analysis or provide additional output"
            + "\n- Any meta-commentary about the research process or data sources"
            + "\n- Generic filler phrases ('it is worth noting', 'going forward', 'remains to be seen')"
            + "\nWrite in third-person analytical voice ONLY. Never break character."
        )

    # ── 4. CITATION STYLE ──
    if spec.citation_style == "footnote":
        sections.append(
            "CITATION STYLE: When citing sources, use markdown links: [source_name](url). "
            "The rendering system will automatically convert these to footnote-style [1] markers. "
            "Cite specific sources for specific claims. Do not list URLs without context."
        )
    elif spec.citation_style == "none":
        sections.append(
            "CITATIONS: Do not include URLs or source links. "
            "All data comes from the provided financial context — cite by reference "
            "(e.g., 'per the latest 10-K filing' or 'based on FY2024 results')."
        )

    # ── 5. OUT OF SCOPE ──
    if spec.out_of_scope:
        sections.append(
            "DO NOT include:\n"
            + "\n".join(f"- {item}" for item in spec.out_of_scope)
        )

    # ── 6. SCOPE ──
    if spec.scope_description:
        sections.append(f"SCOPE: {spec.scope_description}")

    # ── 7. DATA CONSTRAINTS (injected per-call) ──
    if data_constraints:
        sections.append(data_constraints)

    # ── 8. STRATEGY LENS (injected per-call) ──
    if strategy_lens:
        sections.append(strategy_lens)

    # ── 9. PERSISTENT MEMORY (user preferences, feedback, project context) ──
    if memory_context:
        sections.append(memory_context)

    return "\n\n".join(sections)
