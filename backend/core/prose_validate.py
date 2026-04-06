"""Prose Validation Pipeline — clean, validate, and fact-check AI-generated text.

Consolidates web_grounding.clean_web_research(), frontend chatter patterns,
and fact-checking into a single pipeline driven by ProseSpec.

Usage:
    from backend.core.prose_validate import validate_prose
    from backend.core.prose_spec import THESIS_SPEC

    result = validate_prose(raw_text, THESIS_SPEC, fact_sheet=financial_data)
    cleaned_text = result.cleaned_text
    violations = result.violations
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from backend.core.prose_spec import ProseSpec

log = logging.getLogger("fundops.prose_validate")


@dataclass
class ProseResult:
    """Result of prose validation."""
    cleaned_text: str
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fact_check_violations: list[str] = field(default_factory=list)
    words_removed: int = 0
    patterns_cleaned: int = 0


def validate_prose(
    text: str,
    spec: ProseSpec,
    fact_sheet: dict | None = None,
) -> ProseResult:
    """Run the full prose validation pipeline.

    Steps:
        1. Strip forbidden phrases and regex patterns
        2. Remove conversational lines (entire lines that are offers/meta)
        3. Word count check
        4. Fact-check if fact_sheet provided
        5. Return cleaned text + metadata

    Args:
        text: Raw AI-generated text.
        spec: ProseSpec defining quality requirements.
        fact_sheet: Optional financial data dict for fact-checking.

    Returns:
        ProseResult with cleaned_text, violations, warnings.
    """
    if not text or not isinstance(text, str):
        return ProseResult(cleaned_text=text or "")

    result = ProseResult(cleaned_text=text)
    original_word_count = len(text.split())

    # ── Step 1: Strip forbidden phrases ──
    cleaned = text
    for phrase in spec.forbidden_phrases:
        if phrase.lower() in cleaned.lower():
            # Case-insensitive line removal: remove entire lines containing the phrase
            lines = cleaned.split("\n")
            new_lines = []
            for line in lines:
                if phrase.lower() in line.lower():
                    result.patterns_cleaned += 1
                else:
                    new_lines.append(line)
            cleaned = "\n".join(new_lines)

    # ── Step 2: Strip regex patterns (entire lines) ──
    for pattern_str in spec.forbidden_regexes:
        try:
            pattern = re.compile(pattern_str, re.MULTILINE | re.IGNORECASE)
            matches = pattern.findall(cleaned)
            if matches:
                result.patterns_cleaned += len(matches)
                cleaned = pattern.sub("", cleaned)
        except re.error:
            pass

    # ── Step 3: Clean blank lines ──
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    # ── Step 4: Word count validation ──
    final_word_count = len(cleaned.split())
    result.words_removed = original_word_count - final_word_count

    if final_word_count < spec.min_words:
        result.warnings.append(
            f"Prose is short ({final_word_count} words, minimum {spec.min_words})"
        )
    if spec.max_words > 0 and final_word_count > spec.max_words:
        result.warnings.append(
            f"Prose is long ({final_word_count} words, maximum {spec.max_words})"
        )

    # ── Step 5: Fact-check if data available ──
    if fact_sheet:
        try:
            from backend.memo.fact_check import fact_check_section
            fc_violations = fact_check_section(cleaned, fact_sheet)
            result.fact_check_violations = fc_violations
            if fc_violations:
                log.info(f"Prose fact-check: {len(fc_violations)} violation(s)")
        except Exception as e:
            log.debug(f"Fact-check skipped: {e}")

    result.cleaned_text = cleaned

    if result.patterns_cleaned > 0:
        log.info(
            f"Prose cleaning ({spec.name}): removed {result.patterns_cleaned} anti-patterns, "
            f"{result.words_removed} words"
        )

    return result


def clean_prose(text: str, spec: ProseSpec) -> str:
    """Quick-clean prose without full validation. Returns cleaned text only."""
    return validate_prose(text, spec).cleaned_text
