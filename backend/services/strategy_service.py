"""Strategy service: proposal acceptance/rejection and Constitution wiring.

Acceptance is the only path from a Strategy Change Proposal to an active
Constitution Version: guardrails re-validate (defense in depth), criteria are
parsed, settings projections compile deterministically, and the version
activates atomically. Approval, decision-register, and dashboard records are
written so the change is auditable (ADR-0007, ADR-0009, ADR-0033).
"""

from __future__ import annotations

from backend.domain import guardrails, wiring
from backend.domain.criteria import Criterion

_DIFF_FIELDS = ("kind", "metric", "operator", "value", "weight", "data_support_level")


def resolve_universe(universe: dict | None) -> dict | None:
    """Resolve a Universe Selection into a Universe Version snapshot (ADR-0006).

    A named preset ("Russell 2000", "S&P 500", ...) is expanded to its actual
    constituents so the stored version is a resolved list, the rail/wiring show
    a real count, and Screener replay is exact. Explicit ticker lists pass
    through; an unresolvable name keeps the name (Screener still resolves it at
    run time) but records source 'name_only'."""
    if not universe:
        return None
    name = universe.get("name") or "custom"
    tickers = universe.get("tickers")
    if tickers:
        return {"name": name, "tickers": [t.upper() for t in tickers],
                "source": universe.get("source") or "custom_list"}
    try:
        from backend.data.universes import load_preset
        resolved = [t.upper() for t in load_preset(name.lower().replace(" ", "_"))]
        if resolved:
            return {"name": name, "tickers": resolved, "source": "preset"}
    except (ValueError, OSError):
        pass
    return {"name": name, "tickers": [], "source": "name_only"}


def accept_proposal(stores, proposal_id: str) -> dict:
    """Accept a pending Strategy Change Proposal: activate a new Constitution
    Version and wire settings. Returns the version dict with a short
    `activation_confirmation` text attached."""
    proposal = stores.constitution.get_proposal(proposal_id)
    if not proposal:
        raise LookupError(f"unknown proposal {proposal_id}")
    if proposal["status"] != "pending":
        raise ValueError(
            f"proposal {proposal_id} is {proposal['status']}, not pending — "
            "only the current pending draft can be accepted"
        )
    payload = proposal["payload"]
    result = guardrails.validate_proposal(payload)  # defense in depth
    if not result.ok:
        raise ValueError("guardrails rejected the proposal: " + "; ".join(result.errors))

    criteria = [Criterion.from_dict(r) for r in payload.get("rules") or []]
    universe = resolve_universe(payload.get("universe"))
    projections = wiring.project_settings(
        criteria, payload.get("north_star"),
        ic_config=payload.get("ic") or {}, universe=universe,
    )
    prev = stores.constitution.active_version()
    summary = payload.get("summary") or "Strategy change accepted via FundOps Chat"
    version = stores.constitution.activate_version(
        north_star=payload.get("north_star"),
        style_blend=payload.get("style_blend"),
        narrative=payload.get("narrative"),
        version_rationale=summary,
        criteria=criteria,
        projections=projections,
        source_proposal_id=proposal_id,
        universe=universe,
    )
    stores.constitution.decide_proposal(proposal_id, "accepted", version["id"])
    stores.dashboard.record_approval(
        "strategy_proposal", proposal_id, "accept",
        target_version=version["id"],
        effect=f"constitution v{version['version_number']}",
    )
    stores.learning.add_decision(
        kind="strategy_change",
        title=f"Activated Constitution v{version['version_number']}",
        rationale=summary,
        links={"proposal_id": proposal_id, "version_id": version["id"]},
    )
    stores.dashboard.resolve_source("strategy_proposal", proposal_id)
    version["activation_confirmation"] = _confirmation(version, prev)
    return version


def reject_proposal(stores, proposal_id: str) -> None:
    proposal = stores.constitution.get_proposal(proposal_id)
    if not proposal:
        raise LookupError(f"unknown proposal {proposal_id}")
    if proposal["status"] != "pending":
        raise ValueError(f"proposal {proposal_id} is {proposal['status']}, not pending")
    stores.constitution.decide_proposal(proposal_id, "rejected")
    stores.dashboard.record_approval("strategy_proposal", proposal_id, "reject",
                                     effect="proposal rejected; nothing wired")
    stores.dashboard.resolve_source("strategy_proposal", proposal_id)


def _confirmation(version: dict, prev: dict | None) -> str:
    n = version["version_number"]
    if prev is None:
        return (
            f"Constitution v{n} is now active: {len(version.get('criteria', []))} rules "
            "wired across Screener, Thesis, IC Review, Memo, and Portfolio Review."
        )
    diff = diff_criteria(prev.get("criteria", []), version.get("criteria", []))
    parts = []
    if diff["added"]:
        parts.append(f"added {', '.join(c['criterion_id'] for c in diff['added'])}")
    if diff["removed"]:
        parts.append(f"removed {', '.join(c['criterion_id'] for c in diff['removed'])}")
    if diff["changed"]:
        parts.append(f"changed {', '.join(c['criterion_id'] for c in diff['changed'])}")
    change_text = "; ".join(parts) or "criteria unchanged (narrative/emphasis update)"
    return (
        f"Constitution v{n} is now active (supersedes v{prev['version_number']}): "
        f"{change_text}. No other workflow settings changed."
    )


def _criterion_fields(c: dict) -> dict:
    return {f: c.get(f) for f in _DIFF_FIELDS}


def diff_criteria(from_criteria: list[dict], to_criteria: list[dict]) -> dict:
    """Criteria-level diff between two rule sets, keyed by criterion_id."""
    before = {c["criterion_id"]: c for c in from_criteria if c.get("criterion_id")}
    after = {c["criterion_id"]: c for c in to_criteria if c.get("criterion_id")}
    added = [_criterion_fields(after[k]) | {"criterion_id": k}
             for k in after if k not in before]
    removed = [_criterion_fields(before[k]) | {"criterion_id": k}
               for k in before if k not in after]
    changed = []
    for k in after:
        if k in before and _criterion_fields(before[k]) != _criterion_fields(after[k]):
            changed.append({
                "criterion_id": k,
                "from": _criterion_fields(before[k]),
                "to": _criterion_fields(after[k]),
            })
    return {"added": added, "removed": removed, "changed": changed}


def version_diff(stores, from_id: str, to_id: str) -> dict:
    """Criteria-level diff between two Constitution Versions."""
    from_version = stores.constitution.get_version(from_id)
    to_version = stores.constitution.get_version(to_id)
    if not from_version:
        raise LookupError(f"unknown constitution version {from_id}")
    if not to_version:
        raise LookupError(f"unknown constitution version {to_id}")
    return diff_criteria(from_version.get("criteria", []), to_version.get("criteria", []))
