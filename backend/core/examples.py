"""Golden example loader for few-shot prompting.

Loads exemplar agent outputs from data/golden_examples/ and formats
them for injection into LLM prompts. Sector-aware selection picks
the most relevant examples for each stock.
"""

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("fundops.examples")

_EXAMPLES_DIR = Path(__file__).parent.parent / "data" / "golden_examples"

_CACHE: dict[str, list[dict]] = {}


def load_examples(agent: str, n: int = 3) -> list[dict]:
    """Load golden examples for an agent.

    Args:
        agent: "thesis", "ic_review", or "scoring_intent"
        n: Maximum number of examples to return

    Returns:
        List of example dicts from the JSON file.
    """
    if agent in _CACHE:
        return _CACHE[agent][:n]

    filename = f"{agent}_examples.json"
    path = _EXAMPLES_DIR / filename
    if not path.exists():
        log.debug(f"No golden examples found at {path}")
        return []

    try:
        with open(path) as f:
            examples = json.load(f)
        _CACHE[agent] = examples
        return examples[:n]
    except (json.JSONDecodeError, IOError) as e:
        log.warning(f"Failed to load golden examples from {path}: {e}")
        return []


def select_relevant_examples(
    examples: list[dict],
    sector: str = "",
    n: int = 2,
) -> list[dict]:
    """Pick the most relevant examples by sector match.

    Prioritizes same-sector examples, then fills with others.
    """
    if not examples:
        return []

    sector_lower = (sector or "").lower()

    # Score each example by relevance
    scored = []
    for ex in examples:
        ex_sector = (ex.get("sector", "") or "").lower()
        relevance = 2 if sector_lower and sector_lower in ex_sector else 0
        scored.append((relevance, ex))

    # Sort by relevance desc, take top n
    scored.sort(key=lambda x: x[0], reverse=True)
    return [ex for _, ex in scored[:n]]


def format_examples_for_prompt(
    examples: list[dict],
    agent: str,
) -> str:
    """Format golden examples into a few-shot prompt section.

    Returns a string ready to append to an LLM prompt.
    """
    if not examples:
        return ""

    parts = ["\n--- REFERENCE EXAMPLES (follow this format and quality) ---\n"]

    for i, ex in enumerate(examples, 1):
        if agent == "thesis":
            parts.append(f"Example {i} ({ex.get('sector', 'N/A')}):")
            parts.append(f"  Expected return: {ex.get('expected_return', 'N/A')}%")
            parts.append(f"  Conviction: {ex.get('conviction', 'N/A')}")
            parts.append(f"  Narrative: {ex.get('thesis_narrative', '')}")
            parts.append("")

        elif agent == "ic_review":
            parts.append(f"Example {i} ({ex.get('verdict', 'N/A')}, {ex.get('sector', '')}):")
            parts.append(f"  Base return: {ex.get('base_return', 'N/A')}%")
            parts.append(f"  Bear return: {ex.get('bear_return', 'N/A')}%")
            parts.append(f"  Conviction: {ex.get('conviction', 'N/A')}/5")
            parts.append(f"  Reasoning: {ex.get('reasoning', '')}")
            parts.append("")

        else:
            # Generic format
            parts.append(f"Example {i}:")
            parts.append(json.dumps(ex, indent=2, default=str))
            parts.append("")

    parts.append("--- END EXAMPLES ---\n")
    return "\n".join(parts)
