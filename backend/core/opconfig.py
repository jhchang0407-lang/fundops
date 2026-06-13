"""Operational configuration (Settings/Config domain).

Operational resources only — providers, credentials, models, schedules. Strategy
behavior never lives here; it belongs to the Constitution. Secrets resolve from
the environment first (Local Credential Store stand-in, ADR-0051); the YAML file
holds non-secret choices and is safe to back up.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(os.environ.get("FUNDOPS_CONFIG", Path.home() / ".fundops" / "config.yaml"))

DEFAULTS: dict[str, Any] = {
    "ai": {
        # provider = transport: "openai" is the OpenAI-compatible HTTP API (works
        # for OpenAI, Anthropic, Gemini, OpenRouter, Groq, local Ollama — only the
        # base_url/model/key differ, set by provider_id); "agent_cli" is the user's
        # coding-agent harness in headless mode (its own auth — ADR-0060). No key
        # and no CLI -> deterministic stub mode.
        "provider": "openai",
        "provider_id": "openai",      # which preset (ai_presets.AI_PROVIDERS) supplies base_url/models/key
        "model_fast": "gpt-5-mini",   # extraction, classification, routing, summaries
        "model_deep": "gpt-5.2",      # thesis, IC review, memo writing, strategy, learning
        "base_url": None,             # override; falls back to the preset's base_url
        "timeout_s": 180,
        "agent_cli": {
            "preset": "claude",        # claude | codex | custom
            "command": None,           # custom command template list; {prompt} placeholder
            "timeout_s": 300,
        },
    },
    "providers": {
        "sec_user_agent": "FundOps research workspace (contact: user@example.com)",
        "web_search": False,
    },
    "data": {
        # Bulk-first ingestion (ADR-0059): one bootstrap download, then daily
        # index-file ticks. Live provider calls are reserved for interactive
        # work and targeted top-ups.
        "universe_default": "russell2000",
        # 5y daily bars for the whole universe: momentum/volatility/dollar-
        # volume metrics and long-range charts need the depth, and the batch
        # download cost is a one-time bootstrap concern (~2.5M rows at
        # Russell 2000 scope), not a recurring one — daily ticks stay tiny.
        "price_history_years": 5,
        "holdings_price_history_years": 5,
        "cache_dir": None,             # default ~/.fundops/cache
        "ownership_ingest": True,
        # Calendar-event scope is holdings + watchlists by default (one network
        # call per ticker). Enable to widen to the whole configured universe so
        # screened/research names also get earnings/dividend dates — opt-in
        # because it makes every sync a multi-minute, many-call live pass.
        "events_full_universe": False,
    },
    "schedules": {
        "data_sync": "daily",          # one tick: filings index + prices + affected recalcs
        "bulk_refresh": "weekly",      # full companyfacts re-extract
        "screener": "manual",
    },
    "usage": {
        "monthly_token_warning": 20_000_000,
    },
}


def cache_dir() -> "Path":
    cfg = load()
    base = cfg["data"].get("cache_dir") or os.environ.get("FUNDOPS_CACHE")
    path = Path(base) if base else Path.home() / ".fundops" / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


_cache: dict | None = None


def load(refresh: bool = False) -> dict:
    global _cache
    if _cache is not None and not refresh:
        return _cache
    data: dict = {}
    if CONFIG_PATH.exists():
        try:
            data = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        except yaml.YAMLError:
            data = {}
    _cache = _deep_merge(DEFAULTS, data)
    # The SEC user agent goes into an HTTP header: stray leading whitespace or
    # an embedded newline (easy to paste into Settings) makes requests reject
    # the header and silently kills every SEC fetch. Normalize on read so a
    # malformed stored value can never take the ingestion pipeline down.
    ua = _cache["providers"].get("sec_user_agent")
    if isinstance(ua, str):
        _cache["providers"]["sec_user_agent"] = (
            " ".join(ua.split()) or DEFAULTS["providers"]["sec_user_agent"])
    return _cache


def save(updates: dict) -> dict:
    current = {}
    if CONFIG_PATH.exists():
        try:
            current = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        except yaml.YAMLError:
            current = {}
    merged = _deep_merge(current, updates)
    # Never persist secrets into the config file.
    merged.get("ai", {}).pop("api_key", None)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(yaml.safe_dump(merged, sort_keys=False))
    return load(refresh=True)


# --- local credential store (ADR-0051) -------------------------------------------
# Keys entered in the UI live here, NEVER in the workspace DB (so they can't leak
# via "Export workspace data") and NEVER in config.yaml (safe to back up). Env
# vars take precedence, so power users can keep keys out of any file entirely.
SECRETS_PATH = Path(
    os.environ.get("FUNDOPS_SECRETS", Path.home() / ".fundops" / "credentials.yaml")
)


def _load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    try:
        return yaml.safe_load(SECRETS_PATH.read_text()) or {}
    except yaml.YAMLError:
        return {}


def current_provider_id() -> str:
    return load()["ai"].get("provider_id") or "openai"


def _preset(provider_id: str | None) -> dict:
    from backend.core.ai_presets import get_preset
    return get_preset(provider_id or current_provider_id())


def api_key(provider_id: str | None = None) -> str | None:
    """Resolved key for a provider: its environment variable first (e.g.
    OPENAI_API_KEY / ANTHROPIC_API_KEY), then the local credential store."""
    pid = provider_id or current_provider_id()
    env_name = _preset(pid).get("env")
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    val = _load_secrets().get(pid)
    return str(val) if val else None


def set_api_key(provider_id: str, key: str | None) -> None:
    """Persist (or clear, when key is falsy) a provider key in the local
    credential store with owner-only permissions."""
    secrets = _load_secrets()
    if key:
        secrets[provider_id] = key.strip()
    else:
        secrets.pop(provider_id, None)
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(yaml.safe_dump(secrets, sort_keys=True))
    try:
        os.chmod(SECRETS_PATH, 0o600)
    except OSError:
        pass


def api_key_present(provider_id: str | None = None) -> bool:
    return bool(api_key(provider_id))


def secret(name: str, env: str | None = None) -> str | None:
    """A named secret from the environment (when `env` given) or the local
    credential store. Unlike api_key(), never falls back to AI-preset env
    vars — used for non-AI services (web search providers)."""
    if env and os.environ.get(env):
        return os.environ[env]
    val = _load_secrets().get(name)
    return str(val) if val else None


def ai_ready() -> bool:
    """Whether the HTTP provider can run: a keyless local endpoint, or a key is
    present for the selected provider. (agent_cli readiness is resolved by the
    gateway, which knows whether the CLI binary is on PATH.)"""
    pid = current_provider_id()
    if not _preset(pid).get("requires_key", True):
        return True
    return api_key_present(pid)


def resolved_base_url(provider_id: str | None = None) -> str | None:
    cfg = load()["ai"]
    pid = provider_id or cfg.get("provider_id") or "openai"
    return cfg.get("base_url") or _preset(pid).get("base_url")


def ai_settings() -> dict:
    cfg = load()["ai"]
    pid = cfg.get("provider_id") or "openai"
    return {
        **cfg,
        "provider_id": pid,
        "base_url": resolved_base_url(pid),
        "api_key": api_key(pid),
    }


def key_presence_map() -> dict[str, bool]:
    """Which providers have a usable key right now (env or stored) — for the UI;
    never returns the keys themselves."""
    from backend.core.ai_presets import AI_PROVIDERS
    return {pid: api_key_present(pid) for pid in AI_PROVIDERS}


def health() -> dict:
    cfg = load()
    return {
        "ai_configured": ai_ready(),
        "ai_provider_id": cfg["ai"].get("provider_id", "openai"),
        "ai_models": {"fast": cfg["ai"]["model_fast"], "deep": cfg["ai"]["model_deep"]},
        "sec_user_agent_set": "example.com" not in cfg["providers"]["sec_user_agent"],
        "web_search": cfg["providers"]["web_search"],
        "schedules": cfg["schedules"],
    }
