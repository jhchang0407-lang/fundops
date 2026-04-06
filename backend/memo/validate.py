"""Schema validation for memo pipeline structured JSON output.

Validates LLM-generated JSON against section schemas before rendering.
Also validates AI-generated section adaptation plans for investment memos.

Usage:
    from backend.memo.validate import validate_section_json, build_retry_prompt

    is_valid, errors = validate_section_json(structured, schema["fields"])
    if not is_valid:
        retry_prompt = build_retry_prompt(original_prompt, errors)
"""

from __future__ import annotations

from typing import Any

from backend.memo.schemas import HIDDEN_FIELDS


# ─────────────────────────────────────────────────────────────
# Word count helpers
# ─────────────────────────────────────────────────────────────

def _word_count(text: str) -> int:
    """Count words in a string."""
    if not isinstance(text, str):
        return 0
    return len(text.split())


# Minimum word counts by field type
_MIN_WORDS_STR = 50        # Regular prose fields
_MIN_WORDS_HIDDEN = 5      # Hidden fields (section_thesis, etc.)
_MIN_WORDS_TABLE_PART = 30 # Table section intro or analysis
_MIN_WORDS_BLOCK = 20      # Each labeled_block content


# ─────────────────────────────────────────────────────────────
# Section JSON validation
# ─────────────────────────────────────────────────────────────

def validate_section_json(
    structured: dict,
    fields: list[dict],
    section_title: str = "",
) -> tuple[bool, list[str]]:
    """Validate a structured JSON section output against its schema fields.

    Args:
        structured: Parsed JSON dict from LLM output.
        fields: List of field descriptors from the schema (schema["fields"]).
        section_title: Section name for error messages.

    Returns:
        Tuple of (is_valid, error_messages).
        is_valid is True only if all required fields pass type and word count checks.
    """
    if not isinstance(structured, dict):
        return False, [f"Section '{section_title}': expected JSON object, got {type(structured).__name__}"]

    errors: list[str] = []

    for field in fields:
        name = field["name"]
        ftype = field.get("type", "str")
        required = field.get("required", True)

        value = structured.get(name)

        # ── Missing field ──
        if value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, list) and len(value) == 0):
            if required:
                errors.append(f"Required field '{name}' is missing or empty.")
            continue

        # ── Type: str ──
        if ftype == "str":
            if not isinstance(value, str):
                errors.append(f"Field '{name}' must be a string, got {type(value).__name__}.")
                continue
            min_words = _MIN_WORDS_HIDDEN if name in HIDDEN_FIELDS else _MIN_WORDS_STR
            wc = _word_count(value)
            if wc < min_words:
                errors.append(
                    f"Field '{name}' is too short ({wc} words, minimum {min_words}). "
                    f"Write substantive analytical prose with specific data."
                )

        # ── Type: labeled_blocks / list ──
        elif ftype in ("labeled_blocks", "list"):
            if not isinstance(value, list):
                errors.append(f"Field '{name}' must be a list of {{label, content}} objects, got {type(value).__name__}.")
                continue
            for i, item in enumerate(value):
                if not isinstance(item, dict):
                    errors.append(f"Field '{name}[{i}]' must be a dict with 'label' and 'content' keys.")
                    continue
                content = item.get("content") or item.get("paragraph") or ""
                if not isinstance(content, str) or not content.strip():
                    errors.append(f"Field '{name}[{i}]' has missing or empty content.")
                    continue
                wc = _word_count(content)
                if wc < _MIN_WORDS_BLOCK:
                    label = item.get("label", f"item {i}")
                    errors.append(
                        f"Field '{name}[{i}]' ('{label}') is too short ({wc} words, minimum {_MIN_WORDS_BLOCK}). "
                        f"Each block should be 4-6 substantive sentences."
                    )

        # ── Type: table_section ──
        elif ftype == "table_section":
            if not isinstance(value, dict):
                errors.append(f"Field '{name}' must be an object with 'intro' and 'analysis' keys, got {type(value).__name__}.")
                continue
            for part_key in ("intro", "analysis"):
                part = value.get(part_key)
                if not isinstance(part, str) or not part.strip():
                    errors.append(f"Field '{name}.{part_key}' is missing or empty.")
                    continue
                wc = _word_count(part)
                if wc < _MIN_WORDS_TABLE_PART:
                    errors.append(
                        f"Field '{name}.{part_key}' is too short ({wc} words, minimum {_MIN_WORDS_TABLE_PART}). "
                        f"Write substantive analytical prose."
                    )

    is_valid = len(errors) == 0
    return is_valid, errors


# ─────────────────────────────────────────────────────────────
# Investment memo adaptation validation
# ─────────────────────────────────────────────────────────────

def validate_investment_adaptation(plan: Any) -> tuple[bool, list[str]]:
    """Validate an AI-generated section adaptation plan for investment memos.

    The plan must be a list of exactly 4 dicts, each with:
        title (str), key_focus (str), subsections (list of ≥2 strings).

    Args:
        plan: The parsed JSON from the adaptation LLM call.

    Returns:
        Tuple of (is_valid, error_messages).
    """
    errors: list[str] = []

    if not isinstance(plan, list):
        return False, [f"Adaptation plan must be a list, got {type(plan).__name__}."]

    if len(plan) != 4:
        errors.append(f"Adaptation plan must have exactly 4 sections, got {len(plan)}.")

    for i, item in enumerate(plan[:4]):
        if not isinstance(item, dict):
            errors.append(f"Section {i} must be a dict, got {type(item).__name__}.")
            continue

        if not isinstance(item.get("title"), str) or not item["title"].strip():
            errors.append(f"Section {i} missing or empty 'title'.")

        if not isinstance(item.get("key_focus"), str) or not item["key_focus"].strip():
            errors.append(f"Section {i} missing or empty 'key_focus'.")

        subs = item.get("subsections")
        if not isinstance(subs, list):
            errors.append(f"Section {i} 'subsections' must be a list.")
        elif len(subs) < 2:
            errors.append(f"Section {i} needs at least 2 subsections, got {len(subs)}.")
        else:
            for j, sub in enumerate(subs):
                if not isinstance(sub, str) or not sub.strip():
                    errors.append(f"Section {i}, subsection {j} must be a non-empty string.")

    is_valid = len(errors) == 0
    return is_valid, errors


# ─────────────────────────────────────────────────────────────
# Retry prompt builder
# ─────────────────────────────────────────────────────────────

def build_retry_prompt(original_prompt: str, errors: list[str]) -> str:
    """Build an augmented prompt that includes validation errors for retry.

    Embeds the original prompt + specific error messages so the LLM
    knows exactly what to fix.

    Args:
        original_prompt: The original section generation prompt.
        errors: List of validation error messages from validate_section_json.

    Returns:
        Augmented prompt string.
    """
    error_block = "\n".join(f"  {i+1}. {err}" for i, err in enumerate(errors))

    return (
        f"{original_prompt}\n\n"
        f"--- VALIDATION FAILED ---\n"
        f"Your previous response had the following errors:\n"
        f"{error_block}\n\n"
        f"Fix ALL errors above. Ensure:\n"
        f"- Every required field is present and non-empty\n"
        f"- String fields have substantive analytical prose (minimum ~50 words)\n"
        f"- labeled_blocks fields are arrays of {{\"label\": \"...\", \"content\": \"...\"}} objects\n"
        f"- table_section fields are objects with {{\"intro\": \"...\", \"analysis\": \"...\"}}\n"
        f"- Each block/paragraph has specific data and analysis\n\n"
        f"Return ONLY the corrected JSON object. No markdown fences."
    )
