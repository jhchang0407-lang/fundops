"""Settings routes (api-contract): operational config, AI usage, destructive
actions, workspace export.

Operational resources only — strategy behavior lives in the Constitution.
Destructive actions use explicit per-table DELETE lists so retained truth
(constitution, portfolio ledger, chat evidence, learning, approvals) is never
collateral damage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response

from backend.core import opconfig
from backend.core.ai import get_ai
from backend.core.ai_presets import AI_PROVIDERS, public_registry
from backend.stores import get_stores

router = APIRouter()

# Only operational keys may be saved; secrets never touch the config file.
# "data" covers bulk-first ingestion knobs (ADR-0059): universe preset, price
# history depth, cache dir, ownership ingest toggle.
_ALLOWED_SECTIONS = {"ai", "providers", "schedules", "usage", "data"}
_ALLOWED_AI_KEYS = {
    "provider", "provider_id", "model_fast", "model_deep", "base_url", "timeout_s", "agent_cli",
}

# OS-level automation for days FundOps isn't open: `npm run sync` from the repo
# root. The repo root is four parents up from this file (backend/api/routes/…).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CRON_EXPR = {"daily": "0 7 * * *", "weekly": "0 7 * * 1", "monthly": "0 7 1 * *"}


def _automation_hint() -> dict:
    return {"command": "npm run sync", "cwd": str(_REPO_ROOT), "cron": _CRON_EXPR}
# agent_cli (ADR-0060) holds only non-secret harness choices — auth stays with
# the harness itself.
_ALLOWED_AGENT_CLI_KEYS = {"preset", "command", "timeout_s"}

# Workflow outputs cleared by clear-pipeline, in FK-safe order. PRESERVED:
# constitution*, strategy*, universe*, chat*, portfolio*, holdings (rows),
# learning*, decision_register, approval_records, dashboard*, ai_usage,
# execution_provenance, identity tables, financial data.
_CLEAR_PIPELINE_STATEMENTS = (
    "DELETE FROM thesis_health_checks",
    "DELETE FROM thesis_watch_items",
    "DELETE FROM thesis_health_plans",
    "DELETE FROM thesis_health_refreshes",
    "DELETE FROM screener_results",
    "DELETE FROM ic_verdicts",
    "DELETE FROM selection_events",
    "DELETE FROM workbench_state",
    "DELETE FROM evidence_bundles",
    "DELETE FROM artifacts",
    "DELETE FROM workflow_steps",
    "DELETE FROM workflow_runs",
    # Coverage pointed at deleted memo artifacts; positions themselves persist.
    "UPDATE holdings SET coverage_state = 'none', coverage_memo_artifact_id = NULL",
)

_RESET_CONSTITUTION_STATEMENTS = (
    "DELETE FROM strategy_criteria",
    "DELETE FROM settings_projections",
    "DELETE FROM constitution_versions",
    "DELETE FROM strategy_proposals",
    "DELETE FROM universe_versions",
    "DELETE FROM strategy_memory",
)


def _config_without_secrets() -> dict:
    cfg = json.loads(json.dumps(opconfig.load()))  # deep copy
    cfg.get("ai", {}).pop("api_key", None)
    return cfg


@router.get("/settings")
async def get_settings():
    gateway = get_ai()
    stores = get_stores()
    health = opconfig.health()
    # The gateway is the authority on what will actually run (it also knows
    # whether the agent CLI binary is on PATH); reflect its resolved truth.
    health["ai_configured"] = gateway.configured
    health["ai_provider"] = gateway.provider
    # The Settings health strip reads these — they must come from the same
    # payload (they previously only existed on /api/health, leaving the
    # Backend/Constitution/Schema chips permanently blank).
    health["ok"] = True
    active = stores.constitution.active_version()
    health["has_constitution"] = active is not None
    health["constitution_version"] = active.get("version_number") if active else None
    row = stores.ws.query_one(
        "SELECT value FROM workspace_meta WHERE key = 'schema_version'")
    health["workspace_schema_version"] = int(row["value"]) if row else None
    from backend.core import web_research

    return {
        "config": _config_without_secrets(),
        "health": health,
        "ai_providers": public_registry(),
        "ai_key_present": opconfig.key_presence_map(),
        "web_search": {
            "enabled": web_research.enabled(),
            "active_provider": web_research.active_provider(),
            "providers": [
                {"id": pid, "label": spec["label"], "env": spec["env"],
                 "console_url": spec["console_url"],
                 "key_present": bool(opconfig.secret(pid, spec["env"]))}
                for pid, spec in web_research.WEB_PROVIDERS.items()
            ],
        },
        "automation": _automation_hint(),
        "ai_usage": get_stores().ops.ai_usage_summary(),
    }


@router.post("/settings")
async def save_settings(body: dict = Body(...)):
    updates = body.get("updates") if set(body.keys()) == {"updates"} else body
    filtered: dict = {}
    for section, values in (updates or {}).items():
        if section not in _ALLOWED_SECTIONS or not isinstance(values, dict):
            continue
        if section == "ai":
            values = {k: v for k, v in values.items() if k in _ALLOWED_AI_KEYS}
            if isinstance(values.get("agent_cli"), dict):
                values["agent_cli"] = {
                    k: v for k, v in values["agent_cli"].items()
                    if k in _ALLOWED_AGENT_CLI_KEYS
                }
        filtered[section] = values
    if filtered:
        opconfig.save(filtered)
        # Provider / model / base-URL changes must take effect immediately.
        get_ai().invalidate()
    return {"config": _config_without_secrets()}


@router.post("/settings/api-key")
async def set_api_key(body: dict = Body(...)):
    """Store (or clear, with an empty key) a provider's API key in the local
    credential store — never the workspace DB, never config.yaml, never the
    JSON export. Env vars still take precedence. Accepts AI providers and web
    search providers (tavily, brave)."""
    from backend.core.web_research import WEB_PROVIDERS

    provider_id = str(body.get("provider_id") or "").strip()
    if provider_id not in AI_PROVIDERS and provider_id not in WEB_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"unknown provider '{provider_id}'")
    key = body.get("key")
    opconfig.set_api_key(provider_id, key if isinstance(key, str) else None)
    get_ai().invalidate()
    present = (opconfig.api_key_present(provider_id) if provider_id in AI_PROVIDERS
               else bool(opconfig.secret(provider_id, WEB_PROVIDERS[provider_id]["env"])))
    return {"ok": True, "provider_id": provider_id, "key_present": present}


@router.post("/settings/test-ai")
async def test_ai():
    import os

    gateway = get_ai()
    cfg = opconfig.load()["ai"]
    if not gateway.configured:
        # Report the ACTUAL reason, in precedence order — a server forced into
        # stub mode must say so, not blame the user's PATH or keys.
        if os.environ.get("FUNDOPS_AI_PROVIDER") == "stub":
            return {"ok": False, "error": (
                "this server is forced into offline stub mode "
                "(FUNDOPS_AI_PROVIDER=stub — sandbox/test servers run this way "
                "on purpose); connect from your main FundOps server")}
        if cfg.get("provider") == "agent_cli":
            return {"ok": False, "error": (
                "agent CLI not found on this server's PATH — it may differ from "
                "your terminal's. Install Claude Code or Codex, or pick an API "
                "provider above")}
        return {"ok": False, "error": (
            "no API key configured for the selected provider — paste one above "
            "or set its environment variable")}
    try:
        await gateway.complete_json(
            "settings_test_ai",
            "You verify connectivity for FundOps.",
            'Reply with exactly the JSON {"ok": true}.',
            '{"ok": true}',
            tier="fast",
            max_output_tokens=20,
        )
        model = (
            f"agent_cli:{cfg['agent_cli'].get('preset', 'custom')}"
            if gateway.provider == "agent_cli"
            else cfg["model_fast"]
        )
        return {"ok": True, "model": model}
    except Exception as exc:  # provider/network errors surface, never crash
        return {"ok": False, "error": str(exc)}


@router.post("/settings/clear-pipeline")
async def clear_pipeline():
    ws = get_stores().ws
    with ws.transaction() as conn:
        for stmt in _CLEAR_PIPELINE_STATEMENTS:
            conn.execute(stmt)
    return {"ok": True}


@router.post("/settings/reset-constitution")
async def reset_constitution():
    ws = get_stores().ws
    with ws.transaction() as conn:
        for stmt in _RESET_CONSTITUTION_STATEMENTS:
            conn.execute(stmt)
    return {"ok": True}


# Bulk + rebuildable derived data stays out of workspace exports: each of these
# is millions of rows at universe scope (materializing them can OOM the process
# and bloated a single "Export JSON" click to ~365 MB), and all rebuild from
# official sources via sync (ADR-0049 archive ≠ artifact export, ADR-0047/0059).
# User-meaningful state — constitution, portfolio, artifacts, dashboard, chat,
# learning, thesis-health — is retained.
_EXPORT_SKIP_TABLES = {
    "price_history", "filing_sections", "macro_series",
    "reported_financial_facts", "financial_observations", "latest_financials",
}

# Large text columns whose total length dominates the export size — summed for a
# cheap pre-download estimate so a big archive can warn before it downloads.
_EXPORT_SIZE_COLUMNS = {
    "artifacts": ("payload", "rendered_md"),
    "evidence_sources": ("snapshot",),
    "chat_messages": ("content",),
    "execution_provenance": ("inputs_ref", "outputs_ref", "rejected_output"),
}


def _export_tables(ws) -> list[str]:
    return [
        r["name"] for r in ws.query(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ) if r["name"] not in _EXPORT_SKIP_TABLES
    ]


@router.get("/settings/export/estimate")
async def export_estimate():
    """Approximate export size + row count so the UI can warn before a large
    download (ISSUE-004). Cheap aggregate scan — no row materialization."""
    ws = get_stores().ws
    approx, rows = 0, 0
    for t in _export_tables(ws):
        cnt = ws.query_one(f"SELECT COUNT(*) AS n FROM {t}")
        n = (cnt["n"] if cnt else 0) or 0
        rows += n
        cols = _EXPORT_SIZE_COLUMNS.get(t)
        if cols:
            expr = " + ".join(f"COALESCE(SUM(LENGTH({c})), 0)" for c in cols)
            try:  # estimate only — a schema drift must never break the warning
                sz = ws.query_one(f"SELECT {expr} AS b FROM {t}")
                approx += (sz["b"] if sz else 0) or 0
            except Exception:
                pass
        approx += n * 200  # rough JSON overhead for the unmeasured columns
    return {"approx_bytes": approx, "total_rows": rows,
            "excluded_tables": sorted(_EXPORT_SKIP_TABLES)}


@router.get("/settings/export")
async def export_workspace():
    ws = get_stores().ws
    dump = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "excluded_resyncable_tables": sorted(_EXPORT_SKIP_TABLES),
        "tables": {t: [dict(r) for r in ws.query(f"SELECT * FROM {t}")]
                   for t in _export_tables(ws)},
    }
    filename = f"fundops-export-{dump['exported_at'][:10]}.json"
    return Response(
        content=json.dumps(dump, ensure_ascii=False, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
