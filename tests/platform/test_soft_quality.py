"""Soft-quality gates: thesis figure-density regeneration + thematic citation
validation. Both are best-effort (never reject an artifact) and model-path only.
"""

from __future__ import annotations

import asyncio

from backend.domain import prose_quality
from backend.domain.artifact_schemas import THESIS_SCOPE_FIELDS
from backend.workflows import research_runs, thesis


def _thesis_result(scope_text: str) -> dict:
    return {
        "summary": "Summary citing a 12% figure and a $5B level.",
        "scope": {f: scope_text for f in THESIS_SCOPE_FIELDS},
        "return_potential": {"expected_return_pct": 15.0, "components": {"growth": 15.0},
                             "fair_value": 100.0, "valuation_method": "DCF"},
        "evidence_notes": [],
    }


def test_figure_density():
    assert prose_quality.figure_density("A long generic sentence with no numbers in it.") == 0.0
    assert prose_quality.figure_density("Revenue grew 12% to $5B over the shown period.") == 1.0
    assert prose_quality.figure_density("") == 0.0


def test_validate_citations_drops_dangling():
    sources = ["[1] 10-K filed 2026-01-01 — risk", "[2] 10-Q filed 2026-02-01 — mdna",
               "[W1] web source"]
    body = "Strong moat [1]. Growth [2] and a claim [3]. Web note [W1] and [W2]."
    clean, dangling = research_runs._validate_citations(body, sources)
    assert dangling == ["3", "W2"]
    assert "[3]" not in clean and "[W2]" not in clean
    assert "[1]" in clean and "[2]" in clean and "[W1]" in clean


def test_validate_citations_no_mangle_and_clean():
    # All declared -> unchanged.
    clean, dangling = research_runs._validate_citations("Ref [1] and [11].", ["[1] a", "[11] b"])
    assert dangling == [] and clean == "Ref [1] and [11]."
    # Dangling [1] removed without corrupting the valid [11].
    clean2, dangling2 = research_runs._validate_citations("[1] and [11]", ["[11] b"])
    assert dangling2 == ["1"] and "[11]" in clean2 and "[1] " not in clean2


def test_thesis_density_gate_replaces_low_density_scope(stores, offline_ai, monkeypatch):
    low_text = "This company is strong and well managed with good long-term prospects ahead."
    high_text = "Revenue grew 12% to $5B and ROIC of 25% ranks above 6 of 8 peers cited here."
    payload = thesis._build_payload(
        "T", {"id": "e"}, {"cv_id": None}, "b", _thesis_result(low_text), 50.0, {})
    assert prose_quality.figure_density(
        payload["body"]["scope"]["why_opportunity_exists"]) < prose_quality.THESIS_DENSITY_FLOOR

    async def fake(capability, system, user, shape, **kw):
        return _thesis_result(high_text)

    monkeypatch.setattr(offline_ai, "complete_json", fake)
    out = asyncio.run(thesis._densify_scope(
        stores, "T", {"id": "e"}, {"cv_id": None}, "b", "base prompt", None, 50.0, {},
        [], ["why_opportunity_exists"], None, payload))
    assert out["body"]["scope"]["why_opportunity_exists"] == high_text
    # A field NOT in the low set is left untouched.
    assert out["body"]["scope"]["key_risk"] == low_text
