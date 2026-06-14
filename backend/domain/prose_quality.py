"""Shared prose-quality measures: the figure-density (no-filler) contract.

ONE definition of "does this sentence carry a number", used by generation-time
soft gates so thesis and memo prose quality checks cannot drift across call
sites.
"""

from __future__ import annotations

import re

_NUMBERY = re.compile(r"\d")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

# A thesis scope answer below this share of number-bearing sentences reads as
# generic filler.
THESIS_DENSITY_FLOOR = 0.34

# Investment memo subsection floor. Memo generation treats this as a pre-save
# quality warning, and the model path gets one targeted repair attempt before
# the artifact is retained.
MEMO_DENSITY_FLOOR = 0.25


def sentences(text: str | None) -> list[str]:
    """Substantive sentences (>30 chars) — short fragments aren't claims."""
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if len(s.strip()) > 30]


def figure_density(text: str | None) -> float:
    """Share of substantive sentences carrying at least one number."""
    sents = sentences(text)
    if not sents:
        return 0.0
    return sum(1 for s in sents if _NUMBERY.search(s)) / len(sents)
