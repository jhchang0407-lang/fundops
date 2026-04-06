"""Prose Quality Specification — the meta-schema for AI-generated text.

Defines what good prose looks like for each agent. The AI follows this spec;
it doesn't invent its own quality rules per-call.

Usage:
    from backend.core.prose_spec import THESIS_SPEC, IC_REVIEW_SPEC, MEMO_RESEARCH_SPEC

    system = build_prose_system_prompt(THESIS_SPEC, company="Apollo", ticker="APO")
    result = await llm.generate(prompt=..., system=system)
    cleaned = validate_prose(result.text, THESIS_SPEC)
"""

from __future__ import annotations

from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────
# Anti-patterns: forbidden in ALL AI-generated prose
# ─────────────────────────────────────────────────────────────

ANTI_PATTERNS_CONVERSATIONAL = (
    # Addressing the reader
    "You told me",
    "You supplied",
    "You provided",
    "you mentioned",
    "you asked",
    "your numbers",
    "your data",
    "your verified",
    "your audited",
    # Self-referential offers
    "If you want",
    "If you'd like",
    "Would you like me to",
    "Want me to",
    "Let me know if",
    "I can also",
    "I can produce",
    "I could also",
    "Which would you prefer",
    "shall I",
    # Self-referential meta
    "I will treat",
    "I won't repeat",
    "I will not repeat",
    "I'll treat",
    "I checked live",
    "I found that",
    "I noticed that",
    "Below I focus",
    "Here's what I found",
    "Here is what I found",
    # Notes about the process
    "Quick note on",
    "Important note about",
    "A note on",
    "Note about the",
    "Caveat:",
    "Disclaimer:",
)

ANTI_PATTERNS_GENERIC = (
    # Filler phrases
    "It is worth noting that",
    "It should be noted that",
    "It is important to note",
    "In conclusion,",
    "In summary,",
    "Overall,",
    "To summarize,",
    "As mentioned above",
    "As previously discussed",
    "As noted earlier",
    # Generic padding
    "The company is well-positioned",
    "significant opportunity",
    "going forward",
    "remains to be seen",
    "time will tell",
    "only time will tell",
)

# Regex patterns for post-generation cleaning
ANTI_PATTERN_REGEXES = (
    # Lines starting with conversational offers
    r"^-?\s*(?:If you want|Want me to|I can also|Would you like|Let me know).*$",
    # Lines about verified/supplied numbers
    r"^-?\s*(?:You told me|I will treat|I won't repeat|I checked).*$",
    # Meta-notes sections
    r"^(?:Quick note|Important note|A note on).*(?:verified|numbers|data|supplied).*$",
    # "References (selected)" and similar meta-sections at the end
    r"^References? \(selected\).*$",
)


# ─────────────────────────────────────────────────────────────
# ProseSpec dataclass
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProseSpec:
    """Specification for AI-generated prose quality.

    This is the 'meta-schema' — it tells the AI HOW to write,
    while section schemas tell it WHAT to write.
    """

    # Identity
    name: str

    # Tone & voice
    tone: str               # "analytical" | "evaluative" | "investigative"
    voice: str              # "third_person_analyst" | "committee_reviewer" | "research_analyst"
    audience: str           # "institutional_investor" | "portfolio_manager" | "research_consumer"
    persona: str            # One-line role description for the system prompt

    # Anti-patterns (what NOT to do)
    forbidden_phrases: tuple[str, ...] = ANTI_PATTERNS_CONVERSATIONAL + ANTI_PATTERNS_GENERIC
    forbidden_regexes: tuple[str, ...] = ANTI_PATTERN_REGEXES

    # Citation style
    citation_style: str = "footnote"  # "footnote" | "inline" | "none"

    # Formatting requirements
    require_markdown: bool = True
    require_section_headers: bool = True
    require_tables_for_comparisons: bool = True
    require_bold_for_key_metrics: bool = True
    require_bullet_lists: bool = True
    max_paragraph_sentences: int = 6  # Prevent wall-of-text; 0 = no limit

    # Data discipline
    data_constraint_mode: str = "strict"  # "strict" | "anchored" | "none"
    #   strict:   inject explicit data allowlist/denylist (memo sections)
    #   anchored: inject fact anchor for grounding (thesis, outcome checker)
    #   none:     no data constraints (IC review — uses thesis data)

    # Validation thresholds
    min_words: int = 100
    max_words: int = 5000

    # Content boundaries
    scope_description: str = ""  # What this output covers (injected into prompt)
    out_of_scope: tuple[str, ...] = ()  # What NOT to cover


# ─────────────────────────────────────────────────────────────
# Pre-built specs for each agent
# ─────────────────────────────────────────────────────────────

MEMO_RESEARCH_SPEC = ProseSpec(
    name="memo_research",
    tone="analytical",
    voice="third_person_analyst",
    audience="institutional_investor",
    persona=(
        "You are a senior sell-side equity research analyst writing a structured "
        "research report. Write in a factual, evidence-based analytical tone. "
        "Use specific numbers from the data provided."
    ),
    citation_style="none",  # Memo uses structured data, not web citations
    data_constraint_mode="strict",
    min_words=300,
    max_words=1500,
    out_of_scope=(
        "investment recommendations",
        "price targets",
        "buy/sell/hold advice",
        "personal strategy or portfolio references",
    ),
)

MEMO_INVESTMENT_SPEC = ProseSpec(
    name="memo_investment",
    tone="evaluative",
    voice="third_person_analyst",
    audience="portfolio_manager",
    persona=(
        "You are a senior investment analyst writing an investment memo. "
        "Write with conviction — take a clear position on whether this is a "
        "good investment. Use specific numbers and be falsifiable."
    ),
    citation_style="none",
    data_constraint_mode="strict",
    min_words=200,
    max_words=2000,
    require_tables_for_comparisons=True,
)

THESIS_SPEC = ProseSpec(
    name="thesis",
    tone="investigative",
    voice="third_person_analyst",
    audience="portfolio_manager",
    persona=(
        "You are a hedge fund research analyst writing an investment thesis. "
        "Write in third-person analytical tone. Be specific with dates, numbers, "
        "and sources. Never address the reader directly."
    ),
    citation_style="footnote",
    data_constraint_mode="anchored",
    min_words=200,
    max_words=3000,
    require_section_headers=False,  # Thesis is 3-4 flowing paragraphs
    scope_description="Why this stock is mispriced, what the market misunderstands, and key catalysts.",
    out_of_scope=(
        "repeating the anchoring financial data as findings",
        "offering to do further analysis",
        "meta-commentary about the research process",
    ),
)

IC_REVIEW_SPEC = ProseSpec(
    name="ic_review",
    tone="evaluative",
    voice="committee_reviewer",
    audience="portfolio_manager",
    persona=(
        "You are an investment committee member reviewing a thesis. "
        "Be direct and opinionated. Challenge assumptions. "
        "State your verdict clearly with specific reasoning."
    ),
    citation_style="none",
    data_constraint_mode="none",
    require_tables_for_comparisons=False,
    min_words=150,
    max_words=1500,
    scope_description="Evaluate style fit, return credibility, key risk, conviction level, and verdict.",
)

OUTCOME_CHECKER_SPEC = ProseSpec(
    name="outcome_checker",
    tone="investigative",
    voice="third_person_analyst",
    audience="portfolio_manager",
    persona=(
        "You are a performance attribution analyst explaining what drove a "
        "stock's return since the original thesis was written. "
        "Focus on business events, earnings, and catalysts — not market noise."
    ),
    citation_style="footnote",
    data_constraint_mode="anchored",
    min_words=100,
    max_words=2000,
    scope_description="What drove the return: business developments, earnings, sector/macro catalysts, thesis confirmation/refutation.",
)
