"""Configuration routes."""

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from backend.api.deps import get_config, get_fmp, get_yfinance, get_sec, get_llm

router = APIRouter()


@router.get("/config")
async def get_current_config():
    """Get current config (sanitized, no API keys)."""
    import copy
    config = get_config()
    resolved = copy.deepcopy(config.resolved)

    # Sanitize API keys (on the deep copy, not the original)
    connectors = resolved.get("connectors", {})
    for key in connectors:
        if isinstance(connectors[key], dict) and "api_key" in connectors[key]:
            val = connectors[key]["api_key"]
            connectors[key]["api_key"] = "****" if val else ""

    return resolved


@router.post("/config/test-connection")
async def test_connection(source: str = "fmp"):
    """Test data source connection."""
    if source == "fmp":
        fmp = get_fmp()
        if not fmp:
            return {"connected": False, "error": "No FMP API key configured"}
        ok = await fmp.health_check()
        if not ok:
            return {"connected": False, "source": "fmp"}
        # Probe premium endpoints to determine tier
        tier = "free"
        tier_features: list[str] = []
        missing_features: list[str] = []
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                # price-target-consensus is available on paid plans
                r1 = await client.get(
                    "https://financialmodelingprep.com/stable/price-target-consensus",
                    params={"symbol": "AAPL", "apikey": fmp.api_key},
                )
                if r1.status_code == 200 and isinstance(r1.json(), list) and len(r1.json()) > 0:
                    tier_features.append("Price targets")
                else:
                    missing_features.append("Price targets")

                # earnings-surprises requires paid
                r2 = await client.get(
                    "https://financialmodelingprep.com/stable/earnings-surprises",
                    params={"symbol": "AAPL", "apikey": fmp.api_key},
                )
                data2 = r2.json() if r2.status_code == 200 else []
                if isinstance(data2, list) and len(data2) > 0:
                    tier_features.append("Earnings surprises")
                    tier = "paid"
                else:
                    missing_features.append("Earnings surprises")

                # key-metrics is available broadly
                r3 = await client.get(
                    "https://financialmodelingprep.com/stable/key-metrics",
                    params={"symbol": "AAPL", "limit": "1", "apikey": fmp.api_key},
                )
                if r3.status_code == 200 and isinstance(r3.json(), list) and len(r3.json()) > 0:
                    tier_features.append("Key metrics")
                else:
                    missing_features.append("Key metrics")

            if len(tier_features) >= 2:
                tier = "paid"
        except Exception:
            pass

        return {
            "connected": True,
            "source": "fmp",
            "tier": tier,
            "tier_features": tier_features,
            "missing_features": missing_features,
        }
    elif source == "sec":
        sec = get_sec()
        ok = await sec.health_check()
        return {"connected": ok, "source": "sec_edgar"}
    elif source == "yfinance":
        yf = get_yfinance()
        ok = await yf.health_check()
        return {"connected": ok, "source": "yfinance"}
    elif source == "ai":
        llm = get_llm()
        try:
            result = await llm.generate("Say OK", agent="test", reasoning_effort="low")
            return {"connected": bool(result.text), "source": "ai_model"}
        except Exception as e:
            return {"connected": False, "source": "ai_model", "error": str(e)}
    elif source == "web_search":
        try:
            from backend.api.deps import get_web_search
            ws = get_web_search()
            result = await ws.search(
                "What is Apple's current stock price?",
                context={"agent": "test"},
            )
            if result.error:
                return {"connected": False, "source": "web_search", "error": result.error}
            preview = result.text[:200].strip() if result.text else ""
            return {"connected": bool(result.text), "source": "web_search", "preview": preview}
        except Exception as e:
            return {"connected": False, "source": "web_search", "error": str(e)}
    else:
        return {"connected": False, "error": f"Unknown source: {source}"}


@router.get("/config/presets")
async def get_presets():
    """Get strategy presets."""
    from backend.core.config import STRATEGY_PRESETS
    return {"presets": STRATEGY_PRESETS}


@router.get("/config/universes")
async def get_universes():
    """Get available stock universe presets."""
    from backend.data.universes import list_presets
    return {"presets": list_presets()}


@router.get("/config/universe/{name}")
async def get_universe_tickers(name: str):
    """Get ticker list for a specific universe preset."""
    from backend.data.universes import load_preset
    try:
        tickers = load_preset(name)
        return {"name": name, "count": len(tickers), "tickers": tickers}
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(400, str(e))


class SaveConfigRequest(BaseModel):
    """Save arbitrary config key-value pairs."""
    section: str  # "connectors.market_data", "connectors.ai_model", etc.
    values: dict


@router.post("/config/save")
async def save_config(body: SaveConfigRequest):
    """Save config values. Handles API keys specially (writes to .env)."""
    import os
    config = get_config()

    # Navigate to the right section
    parts = body.section.split(".")
    target = config.resolved
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    section_name = parts[-1]
    section = target.setdefault(section_name, {})

    # Update values
    for key, val in body.values.items():
        if key == "api_key" and val and not val.startswith("****"):
            # Real key provided, update env var and config
            section[key] = val
            # Also set in environment so connectors pick it up
            if body.section == "connectors.market_data":
                os.environ["FMP_API_KEY"] = val
            elif body.section == "connectors.ai_model":
                os.environ["OPENAI_API_KEY"] = val
        elif key == "api_key" and val and val.startswith("****"):
            pass  # Masked value, don't overwrite
        else:
            section[key] = val

    # Clear cached LLM whenever AI config changes so it picks up new key/base_url/model
    if body.section == "connectors.ai_model":
        from backend.api.deps import get_llm
        get_llm.cache_clear()

    # Update SEC EDGAR user agent when filings config changes
    if body.section == "connectors.filings":
        user_agent = body.values.get("user_agent")
        if user_agent:
            from backend.core.sec.client import set_user_agent
            set_user_agent(user_agent)

    # Persist to disk
    try:
        config.save_to_disk()
    except Exception as e:
        return {"saved": True, "section": body.section, "persisted": False, "error": str(e)}

    return {"saved": True, "section": body.section, "persisted": True}


@router.get("/config/screener-filters")
async def get_screener_filters():
    """Get all available screener filter definitions + presets."""
    from backend.data.screener_filters import get_filter_categories, SCREENER_PRESETS
    config = get_config()
    active_filters = config.resolved.get("agents", {}).get("screener", {}).get("config", {}).get("filters", {})
    return {
        "categories": get_filter_categories(),
        "presets": SCREENER_PRESETS,
        "active_filters": active_filters,
    }


class SaveScreenerFilters(BaseModel):
    filters: dict
    preset: Optional[str] = None

@router.post("/config/screener-filters")
async def save_screener_filters(body: SaveScreenerFilters):
    """Save screener filter configuration."""
    config = get_config()
    scout_config = config.resolved.setdefault("agents", {}).setdefault("screener", {}).setdefault("config", {})
    scout_config["filters"] = body.filters
    if body.preset:
        scout_config["active_preset"] = body.preset
    config.save_to_disk()
    return {"saved": True, "filter_count": len(body.filters)}


@router.get("/config/export")
async def export_data(format: str = "json"):
    """Export all system data as JSON or SQLite file download."""
    import json, copy, sqlite3, shutil, tempfile, os, datetime
    from pathlib import Path

    db_path = Path(str(Path.home() / ".fundops" / "fundops.db"))
    main_db_path = Path(str(Path.home() / ".fundops" / "fundops.db"))

    if format == "sqlite":
        # Return the raw SQLite file
        src = db_path if db_path.exists() else main_db_path
        if not src.exists():
            return JSONResponse({"error": "No database found"}, status_code=404)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        shutil.copy2(str(src), tmp.name)
        tmp.close()
        headers = {"Content-Disposition": "attachment; filename=fundops-export.db"}
        return FileResponse(tmp.name, media_type="application/octet-stream", headers=headers)

    # JSON export: read all tables from both DBs
    export: dict = {"exported_at": datetime.datetime.utcnow().isoformat(), "tables": {}}
    for path in [main_db_path, db_path]:
        if not path.exists():
            continue
        try:
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for tbl in tables:
                try:
                    rows = [dict(r) for r in conn.execute(f"SELECT * FROM {tbl}").fetchall()]
                    export["tables"][tbl] = rows
                except Exception:
                    pass
            conn.close()
        except Exception:
            pass

    resp = JSONResponse(export)
    resp.headers["Content-Disposition"] = "attachment; filename=fundops-export.json"
    return resp


@router.get("/costs")
async def get_costs():
    """Get LLM cost tracking data (in-memory, resets on server restart)."""
    llm = get_llm()
    summary = llm.get_cost_summary()

    # Transform by_agent into the frontend's CostEntry format
    agent_labels = {
        "screener": "Screener",
        "thesis": "Thesis",
        "ic_review": "IC Review",
        "memo": "Memo",
        "research_report": "Research Report",
        "investment_memo": "Investment Memo",
        "portfolio": "Portfolio",
        "allocator": "Allocator",
        "strategy": "Strategy Chat",
        "test": "Connection Test",
    }
    cost_breakdown = []
    for agent, stats in sorted(summary["by_agent"].items(), key=lambda x: x[1]["cost"], reverse=True):
        label = agent_labels.get(agent, agent.replace("_", " ").title())
        cost_breakdown.append({
            "label": f"{label} ({stats['calls']} calls)",
            "amount": f"${stats['cost']:.4f}",
            "cost": stats["cost"],
        })

    return {
        "total_cost": summary["total_cost"],
        "total_calls": summary["total_calls"],
        "total_tokens": summary["total_tokens"],
        "by_agent": summary["by_agent"],
        "cost_breakdown": cost_breakdown,
    }


class UniverseUpdate(BaseModel):
    preset: Optional[str] = None
    custom_tickers: Optional[str] = None


@router.post("/config/universe")
async def set_universe(body: UniverseUpdate):
    """Update the screener universe setting."""
    config = get_config()

    scout_config = config.resolved.setdefault("agents", {}).setdefault("screener", {}).setdefault("config", {})

    if body.custom_tickers:
        from backend.data.universes import load_custom
        tickers = load_custom(body.custom_tickers)
        scout_config["custom_tickers"] = body.custom_tickers
        scout_config.pop("universe", None)
        return {"mode": "custom", "count": len(tickers), "tickers": tickers[:20]}
    elif body.preset:
        from backend.data.universes import load_preset
        tickers = load_preset(body.preset)
        scout_config["universe"] = body.preset
        scout_config.pop("custom_tickers", None)
        return {"mode": "preset", "preset": body.preset, "count": len(tickers)}
    else:
        return {"error": "Provide preset or custom_tickers"}


@router.post("/config/clear-pipeline")
async def clear_pipeline_data():
    """Clear all agent run data (screener, thesis, IC, memo results).

    Preserves: portfolio positions, strategy/constitution, library entries.
    """
    from backend.api.deps import get_db, get_v2db

    db = get_db()
    deleted = db.clear_pipeline_data()

    # Also clear v2 screener_runs and workflow_events
    db2 = get_v2db()
    for tbl in ("screener_runs", "workflow_events"):
        try:
            cur = db2.conn.execute(f"DELETE FROM {tbl}")
            deleted[tbl] = cur.rowcount
        except Exception:
            deleted[tbl] = 0
    db2.conn.commit()

    total = sum(deleted.values())
    return {"cleared": True, "total_rows": total, "details": deleted}
