"""Chat analyst (data-question) behavior tests — offline, deterministic stub AI.

The analyst answers quantitative questions from retained local data through a
read-only tool loop. These tests pin the contract: data mode classification,
table/chart blocks, citations, tool provenance, history replay, the session
anchor, and the hard invariant that a data conversation never mutates
strategy, portfolio, or artifact state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.chat import service, strategy_chat, tools
from backend.services.portfolio_service import PortfolioService

from tests.platform.conftest import FAKE_METRICS, _persist


@pytest.fixture
def client(stores, offline_ai):
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def seeded(stores):
    """Persist the deterministic metric fixtures (entities + observations +
    price marks) the way the real ingestion would."""
    return {t: _persist(stores, t, m) for t, m in FAKE_METRICS.items()}


def _send(client, message, session_id=None, context=None):
    body = {"message": message}
    if session_id:
        body["session_id"] = session_id
    if context:
        body["context"] = context
    resp = client.post("/api/chat/message", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _table_counts(stores, tables=("artifacts", "constitution_versions", "portfolio_lots",
                                  "financial_observations", "strategy_proposals",
                                  "screener_results")):
    return {t: stores.ws.query_one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in tables}


# --- 1. metric question -> data mode, table block, ticker citation -------------

def test_data_question_returns_table_and_citation(client, stores, seeded):
    out = _send(client, "What is AAA's roic right now?")
    assert out["mode"] == "data"
    blocks = out.get("blocks") or []
    assert blocks and blocks[0]["type"] == "table"
    assert any(c.get("ticker") == "AAA" for c in out.get("citations") or [])
    assert "25.0%" in str(blocks[0]["rows"])  # roic 0.25 formatted


# --- 2. full financials -> period-column table ---------------------------------

def test_company_financials_table(client, stores, seeded):
    out = _send(client, "Show AAA financials")
    assert out["mode"] == "data"
    block = (out.get("blocks") or [])[0]
    assert block["type"] == "table"
    assert block["columns"][0]["key"] == "metric"
    assert len(block["columns"]) >= 2  # metric + at least one period
    assert any("Revenue" in str(r.get("metric")) for r in block["rows"])


# --- 3. price history -> chart block --------------------------------------------

def test_price_history_returns_chart_block(client, stores, seeded):
    today = datetime.now(timezone.utc).date()
    rows = [{"ticker": "AAA", "date": (today - timedelta(days=d)).isoformat(),
             "close": 100.0 + d} for d in range(5, 0, -1)]
    stores.bulk.upsert_prices(rows)
    out = _send(client, "Show AAA price chart")
    assert out["mode"] == "data"
    block = (out.get("blocks") or [])[0]
    assert block["type"] == "chart"
    assert block["ticker"] == "AAA"
    assert len(block["points"]) == 5
    assert any(c.get("kind") == "price_history" for c in out.get("citations") or [])


# --- 4. comparison -> one row per ticker -----------------------------------------

def test_compare_companies_table(client, stores, seeded):
    out = _send(client, "Compare AAA and BBB on roic and gross margin")
    assert out["mode"] == "data"
    block = (out.get("blocks") or [])[0]
    assert block["type"] == "table"
    tickers = [r["ticker"] for r in block["rows"]]
    assert tickers == ["AAA", "BBB"]
    aaa = block["rows"][0]
    assert aaa["roic"] == "25.0%"
    assert aaa["gross_margin"] == "55.0%"


# --- 5. ad-hoc screen: results without any Constitution/run mutation -------------

def test_adhoc_screen_is_not_constitution_mutating(client, stores, seeded, constitution):
    before = _table_counts(stores)
    pending_before = stores.constitution.pending_proposal()
    out = _send(client, "Screen for roic above 15% right now")
    assert out["mode"] == "data"
    block = (out.get("blocks") or [])[0]
    passed = [r["ticker"] for r in block["rows"]]
    assert set(passed) == {"AAA", "BBB"}  # roic 0.25 / 0.18 pass, rest fail or no data
    assert "unchanged" in out["reply"].lower()
    assert _table_counts(stores) == before
    assert stores.constitution.pending_proposal() == pending_before is None


# --- 6. portfolio summary after a recorded lot -----------------------------------

def test_portfolio_summary_after_lot(client, stores, seeded):
    PortfolioService(stores).add_lot("AAA", 10, 90.0, "2026-01-15")
    out = _send(client, "What are my holdings?")
    assert out["mode"] == "data"
    block = (out.get("blocks") or [])[0]
    row = next(r for r in block["rows"] if r["ticker"] == "AAA")
    assert row["shares"] == "10"
    assert any(c.get("kind") == "portfolio" for c in out.get("citations") or [])
    assert "1" in out["reply"]  # 1 position in totals line


# --- 7. tool calls recorded as Execution Provenance (kind="tool") -----------------

def test_tool_calls_recorded_in_provenance(client, stores, seeded):
    out = _send(client, "What is AAA's roic right now?")
    sid = out["session_id"]
    prov = stores.ops.provenance_for_run(sid)
    tool_rows = [p for p in prov if p["kind"] == "tool"]
    assert tool_rows, prov
    assert tool_rows[0]["step"].startswith("chat_tool:")
    assert tool_rows[0]["validation"]["ok"] is True
    # The loop's model iterations are recorded too (stub provider).
    assert any(p["kind"] == "model" for p in prov)


# --- 8. a whole data conversation is read-only ------------------------------------

def test_data_conversation_is_read_only(client, stores, seeded, constitution):
    PortfolioService(stores).add_lot("BBB", 5, 40.0, "2026-02-01")
    before = _table_counts(stores)
    sid = None
    for q in ("What is AAA's roic right now?",
              "Compare AAA and BBB on gross margin",
              "Screen for roic above 15% right now"):
        out = _send(client, q, session_id=sid)
        sid = out["session_id"]
        assert out["mode"] == "data"
    assert _table_counts(stores) == before


# --- 9. session anchor: server remembers the latest session -----------------------

def test_session_anchor_endpoint(client, stores):
    assert client.get("/api/chat/session").json()["session_id"] is None
    out = _send(client, "hello there")
    sid = out["session_id"]
    assert client.get("/api/chat/session").json()["session_id"] == sid
    _send(client, "and again", session_id=sid)
    history = client.get("/api/chat/history", params={"session_id": sid}).json()
    assert len(history["messages"]) == 4  # 2 user + 2 assistant


# --- 10. blocks replay from retained history ---------------------------------------

def test_blocks_replay_from_history(client, stores, seeded):
    out = _send(client, "What is AAA's roic right now?")
    sid = out["session_id"]
    history = client.get("/api/chat/history", params={"session_id": sid}).json()
    assistant = [m for m in history["messages"] if m["role"] == "assistant"][-1]
    blocks = (assistant["refs"] or {}).get("blocks") or []
    assert blocks and blocks[0]["type"] == "table"
    assert (assistant["refs"] or {}).get("citations")


# --- 11. unknown ticker degrades to a plain no-data answer -------------------------

def test_unknown_ticker_is_graceful(client, stores):
    out = _send(client, "What is XYZQ's revenue right now?")
    assert out["mode"] == "data"
    reply = out["reply"].lower()
    assert "couldn't" in reply or "no retained" in reply
    assert not out.get("blocks")


# --- 12. preference memory is read back into strategy prompts ----------------------

def test_preference_memory_read_back(client, stores, offline_ai):
    stores.constitution.remember("preference", {"text": "avoid tobacco companies"},
                                 source="test")
    text = strategy_chat.preference_text(stores)
    assert "avoid tobacco companies" in text

    captured: dict[str, str] = {}
    orig = offline_ai.complete_json

    async def spy(capability, system, user, shape_hint, **kw):
        captured[capability] = user
        return await orig(capability, system, user, shape_hint, **kw)

    offline_ai.complete_json = spy
    _send(client, "I'm wondering whether we should care about moats")
    assert "avoid tobacco companies" in captured.get("strategy_exploration", "")


# --- 13. page context resolves "this company" in the drawer ------------------------

def test_page_context_resolves_ticker(client, stores, seeded):
    out = _send(client, "Show me the financials right now",
                context={"page": "company", "ticker": "BBB"})
    assert out["mode"] == "data"
    assert any(c.get("ticker") == "BBB" for c in out.get("citations") or [])


# --- 14. "compare this with X" merges the context ticker into the comparison -------

def test_page_context_joins_comparison(client, stores, seeded):
    out = _send(client, "Compare this with BBB on roic",
                context={"page": "company", "ticker": "AAA"})
    assert out["mode"] == "data"
    block = (out.get("blocks") or [])[0]
    assert [r["ticker"] for r in block["rows"]] == ["AAA", "BBB"]


# --- 15. threads are durable, browsable objects -------------------------------------

def test_chat_threads_listing(client, stores):
    assert client.get("/api/chat/threads").json()["threads"] == []
    first = _send(client, "what data do we have")
    _send(client, "and a follow-up", session_id=first["session_id"])
    second = _send(client, "a separate conversation")  # no session_id → new thread
    threads = client.get("/api/chat/threads").json()["threads"]
    assert [t["id"] for t in threads] == [second["session_id"], first["session_id"]]
    by_id = {t["id"]: t for t in threads}
    assert by_id[first["session_id"]]["message_count"] == 4
    assert by_id[first["session_id"]]["first_user_message"] == "what data do we have"
    assert by_id[second["session_id"]]["message_count"] == 2


# --- 16. memory is readable and forgettable (append-only) ---------------------------

def test_memory_read_and_forget(client, stores):
    mid = stores.constitution.remember(
        "preference", {"text": "avoid leverage above 3x"}, source="chat")
    listed = client.get("/api/chat/memory").json()["memory"]
    assert [m["id"] for m in listed] == [mid]
    assert listed[0]["content"]["text"] == "avoid leverage above 3x"

    assert client.post(f"/api/chat/memory/{mid}/forget").status_code == 200
    assert client.get("/api/chat/memory").json()["memory"] == []
    # read-back into prompts also drops it
    assert "avoid leverage" not in strategy_chat.preference_text(stores)
    # append-only: the row is retained, only marked
    row = stores.ws.query_one("SELECT superseded_by FROM strategy_memory WHERE id = ?", (mid,))
    assert str(row["superseded_by"]).startswith("forgotten:")
    # double-forget is a 404, not a silent success
    assert client.post(f"/api/chat/memory/{mid}/forget").status_code == 404


# --- 17. thesis-health questions reach the monitoring records (Briefing parity) -----

def _seed_health_plan(stores, ticker: str) -> str:
    """A minimal active monitoring plan: one breached + one intact watch item,
    the shape the Briefing's 'broken on X' line is composed from."""
    from backend.core.workspace import new_id, now_iso
    ent = stores.identity.ensure_entity(ticker)
    pid = new_id("plan")
    with stores.ws.transaction() as conn:
        conn.execute(
            "INSERT INTO thesis_health_plans (id, memo_artifact_id, entity_id, ticker, active, raw_plan, created_at) "
            "VALUES (?,?,?,?,?,?,?)", (pid, new_id("art"), ent["id"], ticker, 1, "{}", now_iso()))
        for title, itype, metric, comp, thr, cur, status in (
            ("Revenue growth turns negative", "kill_criterion", "revenue_growth", "<", 0.0, 0.04, "broken"),
            ("ROIC stays above 12%", "return_driver", "roic", ">=", 0.12, 0.25, "intact"),
        ):
            conn.execute(
                "INSERT INTO thesis_watch_items (id, plan_id, item_type, title, tracking_mode, "
                "metric, comparator, threshold, status, current_value, last_checked_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (new_id("watch"), pid, itype, title, "quantitative", metric, comp, thr,
                 status, cur, now_iso()))
    return pid


def test_thesis_health_tool_explains_break(stores, seeded):
    _seed_health_plan(stores, "AAA")
    out = tools.get_thesis_health(stores, {"ticker": "AAA"})
    assert out["error"] is None
    assert "BROKEN" in out["summary"]
    assert "Revenue growth turns negative" in out["summary"]
    assert out["block"]["type"] == "table" and len(out["block"]["rows"]) == 2
    assert out["citations"][0]["ticker"] == "AAA"


def test_thesis_health_question_routes_to_data(client, stores, seeded):
    # The exact failure the user hit: a monitoring question must NOT fall through
    # to the artifact archive (which has no record of a held, monitored name).
    assert service.keyword_mode("why did AAA thesis health break", False) == "data_question"
    _seed_health_plan(stores, "AAA")
    out = _send(client, "why did AAA thesis health break")
    assert out["mode"] == "data"
    assert "broken" in out["reply"].lower()
    assert any(c.get("ticker") == "AAA" for c in out.get("citations") or [])


def test_thesis_health_unmonitored_ticker_is_graceful(client, stores, seeded):
    out = tools.get_thesis_health(stores, {"ticker": "BBB"})
    assert out["error"] and "monitored position" in out["error"]


# --- 18. reading a document: the analyst can open the artifact being viewed ---------

def _save_note(stores) -> str:
    return stores.artifacts.save_artifact(
        "industry_note",
        {"schema_version": "1.0",
         "body": {"title": "Widget Market Landscape", "kind": "thematic_report",
                  "theme": "widgets", "tickers": ["AAA"]}},
        rendered_md=("## Key players\n\nAlpha Corp (AAA) leads the widget market "
                     "with a 40% share; Beta Industries (BBB) is the challenger."),
    )


def test_get_artifact_tool_reads_content(stores, seeded):
    aid = _save_note(stores)
    out = tools.get_artifact(stores, {"artifact_id": aid})
    assert out["error"] is None
    assert "Widget Market Landscape" in out["summary"]
    assert "40% share" in out["summary"]          # content, not just metadata
    assert out["citations"][0]["artifact_id"] == aid
    assert tools.get_artifact(stores, {"artifact_id": "art_nope"})["error"]


def test_artifact_context_grounds_the_conversation(client, stores, seeded):
    """The exact failure the user hit: asking about the open report sent the
    question to archive search (title matching), which knows nothing. With the
    artifact id in context the analyst must read THE DOCUMENT and answer."""
    aid = _save_note(stores)
    out = _send(client, "who are the largest players in this market",
                context={"page": "artifact", "artifact_id": aid})
    assert out["mode"] == "data"
    assert "Widget Market Landscape" in out["reply"] or "40% share" in out["reply"]
    assert any(c.get("artifact_id") == aid for c in out.get("citations") or [])


def test_selected_passage_rides_with_the_question(client, stores, seeded):
    aid = _save_note(stores)
    out = _send(client,
                'What evidence supports this claim?\n\nSelected passage (from the '
                'document I\'m reading): "Alpha Corp (AAA) leads the widget market"',
                context={"page": "artifact", "artifact_id": aid})
    assert out["mode"] == "data"
    assert any(c.get("artifact_id") == aid for c in out.get("citations") or [])


# --- 19. the product explains itself (guide mode) -----------------------------------

def test_product_questions_route_to_guide(client, stores):
    assert service.keyword_mode("how does ic review work", False) == "product_question"
    assert service.keyword_mode("what is thesis health", False) == "product_question"
    assert service.keyword_mode("where do memos come from", False) == "product_question"
    # …without stealing strategy status or ticker-status questions.
    assert service.keyword_mode("what is my roic requirement", False) == "strategy_status"
    assert service.keyword_mode("why did AAA thesis health break", False) == "data_question"


def test_guide_answer_is_honest_and_actionable(client, stores):
    out = _send(client, "how does ic review decide pass or fail")
    assert out["mode"] == "guide"
    reply = out["reply"].lower()
    assert "deterministic" in reply and "override" in reply
    actions = out.get("actions") or []
    assert any(a.get("route") == "/ic-review" for a in actions)


def test_guide_thesis_health_concept_vs_status(client, stores):
    out = _send(client, "what is thesis health")
    assert out["mode"] == "guide"
    assert "healthy" in out["reply"].lower() or "monitor" in out["reply"].lower()


# --- 20. action requests: chat offers the run, the click confirms -------------------

def test_action_request_routing(client, stores):
    km = service.keyword_mode
    assert km("can you run thesis on TSLA", False) == "action_request"
    assert km("start the pipeline", False) == "action_request"
    assert km("generate a memo for KO", False) == "action_request"
    # Retrospective / conceptual phrasing must NOT become an action.
    assert km("what did the screener run show?", False) == "archive_question"
    assert km("how does the screener work", False) == "product_question"


def test_action_request_directed_thesis(client, stores, seeded):
    out = _send(client, "can you run thesis on TSLA")
    assert out["mode"] == "action"
    acts = out.get("actions") or []
    assert any(a["type"] == "run_directed" and a["ticker"] == "TSLA"
               and a["capability"] == "thesis" for a in acts)
    # Honest provider note in offline mode — never the generic menu.
    assert "stub" in out["reply"].lower() or "provider" in out["reply"].lower()
    assert "What would you like to do?" not in out["reply"]


def test_action_request_pipeline_and_screener(client, stores):
    out = _send(client, "run the full pipeline")
    assert out["mode"] == "action"
    assert any(a["type"] == "run_workflow" and a["kind"] == "pipeline"
               for a in out.get("actions") or [])
    out = _send(client, "please run the screener now")
    assert any(a["type"] == "run_workflow" and a["kind"] == "screener"
               for a in out.get("actions") or [])


def test_action_request_never_writes_silently(client, stores):
    """The action reply itself must not start a run — only the user's click on
    the chip does (via the run endpoints)."""
    before = stores.ws.query("SELECT COUNT(*) AS n FROM workflow_runs")[0]["n"]
    _send(client, "run thesis on TSLA")
    after = stores.ws.query("SELECT COUNT(*) AS n FROM workflow_runs")[0]["n"]
    assert after == before


# --- 21. RC1: price + growth metrics are derived for chat, never stored -------------

def _seed_enrichable(stores, ticker, price, shares, net_income, fcf, eps,
                     rev_prev=1.0e10, rev_now=1.2e10):
    """An entity with the raw inputs for derived metrics but NONE of the derived
    metrics (market_cap/pe/fcf_yield/earnings_yield/revenue_growth) stored — the
    real-world shape, since those are computed at read time (ADR-0017)."""
    ent = stores.identity.ensure_entity(ticker, name=f"{ticker} Co", sector="Technology")
    stores.financial.store_metrics_snapshot(
        ent["id"], {"revenue": rev_prev}, "2024-12-31", "annual")
    stores.financial.store_metrics_snapshot(
        ent["id"], {"revenue": rev_now, "shares_outstanding": shares,
                    "net_income": net_income, "free_cash_flow": fcf, "eps": eps},
        "2025-12-31", "annual")
    stores.portfolio.mark_price(ticker, price)
    return ent


def test_chat_derives_price_and_growth_metrics(stores):
    ent = _seed_enrichable(stores, "ENR", 20.0, 1.0e9, 2.0e9, 1.5e9, 2.0)
    # None of these were stored — they must be derived at read time.
    assert stores.financial.latest_value(ent["id"], "market_cap") is None
    assert stores.financial.latest_value(ent["id"], "pe") is None

    enr = tools._enriched_latest(stores, "ENR", ent)
    assert enr["market_cap"] == pytest.approx(2.0e10)    # 20 * 1e9 shares
    assert enr["pe"] == pytest.approx(10.0)              # 20 / 2 eps
    assert enr["fcf_yield"] == pytest.approx(0.075)      # 1.5e9 / 2e10
    assert enr["earnings_yield"] == pytest.approx(0.10)  # 2e9 / 2e10
    assert enr["revenue_growth"] == pytest.approx(0.20)  # 1.2e10 / 1.0e10 - 1

    # get_metric resolves a derived metric instead of erroring "no observations".
    out = tools.get_metric(stores, {"ticker": "ENR", "metric": "market_cap"})
    assert out["error"] is None
    assert out["data"]["observations"][0]["value"] == pytest.approx(2.0e10)


def test_chat_compare_and_screen_use_derived_metrics(stores):
    _seed_enrichable(stores, "ENR", 20.0, 1.0e9, 2.0e9, 1.5e9, 2.0)   # fcf_yield 7.5%
    _seed_enrichable(stores, "LOW", 10.0, 1.0e9, 1.0e8, 1.0e8, 1.0,
                     rev_prev=1.0e10, rev_now=1.0e10)                  # fcf_yield 1.0%

    cmp = tools.compare_companies(
        stores, {"tickers": ["ENR", "LOW"], "metrics": ["market_cap", "fcf_yield"]})
    assert cmp["error"] is None
    enr_row = next(r for r in cmp["block"]["rows"] if r["ticker"] == "ENR")
    assert enr_row["market_cap"] == "$20.0B"   # derived, not an em-dash
    assert enr_row["fcf_yield"] == "7.5%"

    scr = tools.screen_universe(
        stores, {"criteria": [{"metric": "fcf_yield", "operator": ">", "value": 0.05}]})
    assert scr["error"] is None
    assert "ENR" in scr["data"]["tickers"]
    assert "LOW" not in scr["data"]["tickers"]
