"""Shared prose-quality measures: the figure-density (no-filler) contract.

ONE definition of "does this sentence carry a number", used by both the
generation-time soft gate (thesis scope answers) and the post-hoc auditor
(scripts/quality_audit.py), so a thesis that clears generation also clears the
CI audit — they can't drift.
"""

from __future__ import annotations

import re

_NUMBERY = re.compile(r"\d")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

# A thesis scope answer below this share of number-bearing sentences reads as
# generic filler (matches quality_audit.py's thesis threshold).
THESIS_DENSITY_FLOOR = 0.34


def sentences(text: str | None) -> list[str]:
    """Substantive sentences (>30 chars) — short fragments aren't claims."""
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if len(s.strip()) > 30]


def figure_density(text: str | None) -> float:
    """Share of substantive sentences carrying at least one number."""
    sents = sentences(text)
    if not sents:
        return 0.0
    return sum(1 for s in sents if _NUMBERY.search(s)) / len(sents)
