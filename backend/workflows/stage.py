"""Shared workflow stage-selection helpers (CONTEXT workflow lifecycle, ADR-0036).

Every stage partitions its output into a selected block and a remaining block,
expressed purely by row order. Promote appends to the end of the selection and
expands the count; dismiss reflows the default ranking without stigma — the
next-ranked eligible candidate moves in only when the dismissal removed a
member of the default selection (a dismissed manual promotion simply shrinks
the count). Selection feedback is recorded via stores.runs.record_selection;
ranking math and completed artifacts never change.
"""

from __future__ import annotations

ACTIONS = ("promote", "dismiss")


def new_state(default_count: int) -> dict:
    """Fresh selection state for one stage run: default block size + user deltas."""
    return {"default_count": int(default_count), "promoted": [], "dismissed": []}


def compute_selection(
    rank_order: list[str], state: dict, eligible: set[str] | None = None
) -> list[str]:
    """Selection = default block + manual promotions appended at the end.

    Default block = rank order minus dismissed/promoted tickers, restricted to
    `eligible` (e.g. uncapped theses), capped at default_count. Promotions are
    user judgment and bypass the eligibility restriction.
    """
    promoted = [t for t in state.get("promoted", []) if t not in state.get("dismissed", [])]
    dismissed = set(state.get("dismissed", []))
    pool = [
        t for t in rank_order
        if t not in dismissed and t not in promoted
        and (eligible is None or t in eligible)
    ]
    default = pool[: max(0, int(state.get("default_count", 0)))]
    return default + [t for t in promoted if t in rank_order]


def apply_action(
    stores,
    capability: str,
    run_id: str | None,
    state: dict,
    rank_order: list[str],
    ticker: str,
    action: str,
    eligible: set[str] | None = None,
    promotable: set[str] | None = None,
) -> tuple[dict, list[str]]:
    """Apply one promote/dismiss to selection state and record the selection
    event for learning. Returns (state, new selection)."""
    ticker = ticker.upper()
    if action not in ACTIONS:
        raise ValueError(f"unknown selection action {action!r} (expected promote|dismiss)")
    if ticker not in rank_order:
        raise ValueError(f"{ticker} is not part of this stage output")
    current = compute_selection(rank_order, state, eligible)
    if action == "promote":
        if promotable is not None and ticker not in promotable:
            raise ValueError(f"{ticker} is not eligible for promotion")
        if ticker not in current:
            state["dismissed"] = [t for t in state.get("dismissed", []) if t != ticker]
            if ticker not in state.get("promoted", []):
                state.setdefault("promoted", []).append(ticker)
    else:
        # A dismissed promotion shrinks the count (no refill); a dismissed
        # default member lets the next-ranked eligible candidate move in.
        # Either way the ticker stays out until promoted again.
        if ticker in state.get("promoted", []):
            state["promoted"] = [t for t in state["promoted"] if t != ticker]
        if ticker not in state.get("dismissed", []):
            state.setdefault("dismissed", []).append(ticker)
    stores.runs.record_selection(capability, run_id, ticker, action)
    return state, compute_selection(rank_order, state, eligible)


def partition(rank_order: list[str], selection: list[str]) -> tuple[list[str], list[str]]:
    """Selected block (selection order) + remaining block (rank order)."""
    sel = set(selection)
    return list(selection), [t for t in rank_order if t not in sel]


def stage_status(workbench: dict | None) -> str:
    """Stage status for */current endpoints: idle|running|completed|failed."""
    if not workbench:
        return "idle"
    return workbench.get("status") or "idle"
