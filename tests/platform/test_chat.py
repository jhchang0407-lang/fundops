"""FundOps Chat behavior tests (offline, deterministic stub AI).

Covers the Strategy Chat eval surface: readiness check, draft-before-approval,
natural approval, stale-session approval, cancellation, archive Q&A, and
multi-version diffing — all through the public API where convenient.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.domain import guardrails

VAGUE = "I want to invest in good companies at a fair price."
DETAILED = (
    "I want quality compounders: revenue growth of at least 10% a year, "
    "ROIC above 15%, gross margins over 40%, reasonable valuations below "
    "25 times earnings, and low debt."
)
DIVIDEND = (
    "Change my strategy: focus on dividend income — dividend yield of at "
    "least 2% and a payout ratio under 60%, and keep low debt."
)


@pytest.fixture
def client(stores, offline_ai):
    with TestClient(create_app()) as c:
        yield c


def _send(client, message, session_id=None):
    body = {"message": message}
    if session_id:
        body["session_id"] = session_id
    resp = client.post("/api/chat/message", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _draft(client, stores, message=DETAILED, session_id=None):
    out = _send(client, message, session_id)
    assert out.get("draft"), out["reply"]
    pending = stores.constitution.pending_proposal()
    assert pending is not None
    return out, pending


# --- 1. vague message -> one clarifying question, no draft --------------------

def test_vague_message_asks_clarifying_question(client, stores):
    out = _send(client, VAGUE)
    assert out["mode"] == "strategy"
    assert "?" in out["reply"]
    # Observable-signal examples, drawn from the metric catalog.
    reply = out["reply"].lower()
    assert sum(sig in reply for sig in
               ("revenue growth", "roic", "gross margin", "free-cash-flow",
                "debt", "stock-based compensation")) >= 2
    assert out.get("draft") is None
    assert stores.constitution.pending_proposal() is None
    assert stores.constitution.active_version() is None


# --- 2. detailed message -> valid draft with wiring preview + approval prompt --

def test_detailed_message_creates_pending_draft(client, stores):
    out, pending = _draft(client, stores)
    draft = out["draft"]
    assert draft["rules"]
    # The draft must carry the proposal id so the UI can approve it directly
    # (regression: a missing id caused "unknown proposal undefined" on approve).
    assert draft.get("id") == pending["id"]
    result = guardrails.validate_proposal(draft)
    assert result.ok, result.errors
    assert pending["payload"]["summary"] == draft["summary"]
    # Reply shows wiring preview and explicit approval consequences.
    assert "Wiring preview" in out["reply"]
    assert "Constitution Version 1" in out["reply"]
    assert "approve" in out["reply"].lower()
    # Nothing wired before approval.
    assert stores.constitution.active_version() is None
    assert stores.constitution.projection("screener") is None


# --- 3. natural approval activates the live draft ------------------------------

def test_yes_activates_live_draft(client, stores):
    out, pending = _draft(client, stores)
    confirm = _send(client, "yes", out["session_id"])

    active = stores.constitution.active_version()
    assert active is not None and active["version_number"] == 1
    assert active["criteria"]
    assert stores.constitution.projections_for(active["id"])
    assert stores.constitution.pending_proposal() is None
    assert stores.constitution.get_proposal(pending["id"])["status"] == "accepted"
    # Short confirmation that identifies the version; not a re-dump of the draft.
    assert "v1" in confirm["reply"]
    assert "Wiring preview" not in confirm["reply"]
    # Approval record retained.
    approvals = stores.dashboard.approvals()
    assert any(a["target_type"] == "strategy_proposal" and a["action"] == "accept"
               and a["target_id"] == pending["id"] for a in approvals)


# --- 4. approval language with no pending draft never guesses ------------------

def test_yes_without_pending_draft_asks_what_to_approve(client, stores):
    out = _send(client, "yes")
    assert stores.constitution.active_version() is None
    assert "approve" in out["reply"].lower()
    assert "?" in out["reply"]


# --- 4b. approval after restart re-shows the draft instead of activating -------

def test_yes_in_new_session_reshows_draft_before_activating(client, stores):
    _draft(client, stores)  # draft created in session A
    # New session (app restart): pending draft exists in DB but was never
    # shown in this session.
    out_b = _send(client, "yes")  # no session_id -> fresh session B
    assert stores.constitution.active_version() is None
    assert "new chat session" in out_b["reply"].lower()
    assert out_b.get("draft"), "draft must be re-shown for confirmation"
    # Now the draft is live in session B; the next yes activates it.
    confirm = _send(client, "yes", out_b["session_id"])
    active = stores.constitution.active_version()
    assert active is not None and active["version_number"] == 1
    assert "v1" in confirm["reply"]


# --- 5. cancellation drops the draft; later yes does not resurrect it ----------

def test_cancellation_flow(client, stores):
    out, pending = _draft(client, stores)
    sid = out["session_id"]
    cancel = _send(client, "Never mind, do not save this.", sid)
    assert "nothing was saved" in cancel["reply"].lower()
    assert stores.constitution.pending_proposal() is None
    assert stores.constitution.get_proposal(pending["id"])["status"] == "cancelled"
    # Later approval language has no target and never activates the cancelled draft.
    later = _send(client, "yes", sid)
    assert stores.constitution.active_version() is None
    assert "approve" in later["reply"].lower()


# --- 5b. vague rejection asks what's wrong; specific rejection revises ---------

def test_rejection_paths(client, stores):
    out, first_pending = _draft(client, stores)
    sid = out["session_id"]
    vague = _send(client, "No, that is not what I meant.", sid)
    assert "what part" in vague["reply"].lower()
    assert vague.get("draft") is None
    # Draft survives a vague correction (nothing was wired either way).
    assert stores.constitution.pending_proposal()["id"] == first_pending["id"]

    specific = _send(client, "No — drop the valuation cap, I care about "
                             "dividend yield of at least 2% instead.", sid)
    assert specific.get("draft"), specific["reply"]
    new_pending = stores.constitution.pending_proposal()
    assert new_pending["id"] != first_pending["id"]
    assert stores.constitution.get_proposal(first_pending["id"])["status"] == "cancelled"
    assert stores.constitution.active_version() is None


# --- 6. archive Q&A: cited answers from retained history -----------------------

def test_archive_question_with_seeded_artifact(client, stores):
    entity = stores.identity.ensure_entity("AAPL", name="Apple Inc.")
    artifact_id = stores.artifacts.save_artifact(
        "thesis", {"summary": "Durable ecosystem economics"},
        ticker="AAPL", entity_id=entity["id"], rendered_md="# Apple thesis",
    )
    out = _send(client, "What research do we have on AAPL?")
    assert out["mode"] == "archive"
    citations = out.get("citations") or []
    assert any(c.get("artifact_id") == artifact_id for c in citations)
    actions = out.get("actions") or []
    assert any(a["type"] == "open_artifact" and a["id"] == artifact_id for a in actions)
    assert any(a["type"] == "open_company" and a["ticker"] == "AAPL" for a in actions)
    # Read-only: nothing was drafted or changed.
    assert stores.constitution.pending_proposal() is None


def test_archive_question_unknown_ticker(client, stores):
    out = _send(client, "What do we know about ZZZZ?")
    assert out["mode"] == "archive"
    assert "no retained" in out["reply"].lower()
    assert not out.get("citations")


# --- 7. second accepted proposal -> version 2 + criteria-level diff -------------

def test_second_acceptance_creates_v2_and_diff(client, stores):
    out, _ = _draft(client, stores)
    sid = out["session_id"]
    _send(client, "yes", sid)
    assert stores.constitution.active_version()["version_number"] == 1

    out2, pending2 = _draft(client, stores, DIVIDEND, sid)
    # Post-setup approval prompt is a focused change, version-aware.
    assert "Constitution Version 2" in out2["reply"]
    confirm = _send(client, "yes", sid)
    active = stores.constitution.active_version()
    assert active["version_number"] == 2
    assert "v2" in confirm["reply"]

    versions = {v["version_number"]: v["id"]
                for v in stores.constitution.list_versions()}
    resp = client.get("/api/strategy/diff",
                      params={"from_id": versions[1], "to_id": versions[2]})
    assert resp.status_code == 200
    diff = resp.json()
    assert diff["added"] or diff["removed"] or diff["changed"]
    added_ids = {c["criterion_id"] for c in diff["added"]}
    assert "screen.dividend_yield_min" in added_ids


# --- supporting surfaces --------------------------------------------------------

def test_chat_history_endpoint(client, stores):
    out = _send(client, VAGUE)
    resp = client.get("/api/chat/history", params={"session_id": out["session_id"]})
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert all(m["mode"] == "strategy" for m in messages)


def test_status_question_answers_from_constitution(client, stores):
    out, _ = _draft(client, stores)
    sid = out["session_id"]
    _send(client, "yes", sid)
    status = _send(client, "What is my current ROIC requirement?", sid)
    assert status["mode"] == "status"
    assert "ROIC" in status["reply"]
    # Humanized — never raw ids/operators in the reply.
    assert ">= 0.15" not in status["reply"] and "roic >=" not in status["reply"].lower()
    assert "[screen]" not in status["reply"] and "[rank]" not in status["reply"]
    # No new draft from a read-only question.
    assert stores.constitution.pending_proposal() is None


def test_exploration_discusses_without_drafting(client, stores):
    out = _send(client, "I am wondering if I should care more about dividends.")
    assert out["mode"] == "exploration"
    assert out.get("draft") is None
    assert stores.constitution.pending_proposal() is None
    assert "draft" in out["reply"].lower()  # offers to draft


def test_strategy_endpoint_shapes(client, stores):
    resp = client.get("/api/strategy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_version"] is None and body["pending_proposal"] is None

    out, pending = _draft(client, stores)
    _send(client, "yes", out["session_id"])
    body = client.get("/api/strategy").json()
    assert body["active_version"]["version_number"] == 1
    assert body["active_version"]["criteria_count"] > 0
    caps = {p["capability"] for p in body["projections"]}
    assert {"screener", "thesis", "ic_review", "memo", "portfolio_review"} <= caps
    assert body["universe"]["name"]

    wiring_resp = client.get("/api/strategy/wiring/screener")
    assert wiring_resp.status_code == 200
    assert wiring_resp.json()["summary_text"]

    health = client.get("/api/health").json()
    assert health["ok"] is True
    assert health["has_constitution"] is True
    assert health["ai_configured"] is False
    assert health["workspace_schema_version"] >= 2


def test_chat_humanizes_internal_tokens():
    """No internal tokens (kind tags, capability keys, criterion ids, raw metric
    ids, raw operators) leak into chat replies; plain prose is untouched."""
    from backend.domain import labels
    leaked = ("1. [rank] fcf_yield > 0.0\n- ic_review: gate score\n"
              "screen.roic_min: roic >= 0.15; gross_margin >= 0.4")
    out = labels.humanize_chat_text(leaked)
    for bad in ("[rank]", "ic_review:", "screen.roic_min", "fcf_yield", "gross_margin", ">="):
        assert bad not in out, f"leaked token survived: {bad}\n{out}"
    assert "FCF Yield" in out and "IC Review:" in out and "≥" in out
    plain = "I want durable compounders with rising free cash flow."
    assert labels.humanize_chat_text(plain) == plain


def test_universe_resolves_and_wiring_panel(client, stores):
    """Accepting a strategy with a named preset universe stores resolved
    constituents (not just a name), and the universe wiring panel returns them
    (regression: Universe chip showed 'No wiring available')."""
    from fastapi.testclient import TestClient
    from backend.api import create_app

    # Draft + accept a strategy whose universe is the S&P 500 preset by name.
    out, pending = _draft(client, stores)
    payload = dict(pending["payload"])
    payload["universe"] = {"name": "S&P 500", "tickers": None}
    stores.ws.execute(
        "UPDATE strategy_proposals SET payload = ? WHERE id = ?",
        (__import__("json").dumps(payload), pending["id"]))
    stores.ws.conn.commit()
    client.post(f"/api/strategy/proposals/{pending['id']}/accept")

    uni = stores.constitution.active_universe()
    assert uni and len(uni["tickers"]) > 100 and uni["source"] == "preset"

    wiring = client.get("/api/strategy/wiring/universe")
    assert wiring.status_code == 200, wiring.text
    body = wiring.json()
    assert body["settings"]["constituents"] == len(uni["tickers"])
    assert body["settings"]["sample_tickers"]
    assert "resolved constituents" in body["summary_text"]
