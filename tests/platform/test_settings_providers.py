"""Settings: multi-provider AI config, the local credential store, and editable
schedules — the operational surface the user drives from the UI.

Pins the security-relevant invariants: API keys live in a local credential file
(never the workspace DB, never config.yaml, never the JSON export), env vars win
over the stored file, keyless local providers are usable without a key, and the
gateway re-resolves after a change.
"""

from __future__ import annotations

import os
import stat

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.core import ai, opconfig


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """Point opconfig at throwaway config + credential files and reset its
    module cache so no test touches the real ~/.fundops."""
    monkeypatch.setattr(opconfig, "CONFIG_PATH", tmp_path / "config.yaml")
    monkeypatch.setattr(opconfig, "SECRETS_PATH", tmp_path / "credentials.yaml")
    monkeypatch.setattr(opconfig, "_cache", None)
    # No provider keys in the environment by default.
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
                "OPENROUTER_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("FUNDOPS_AI_PROVIDER", raising=False)
    yield
    monkeypatch.setattr(opconfig, "_cache", None)


@pytest.fixture
def client(stores, isolated_config):
    with TestClient(create_app()) as c:
        yield c


# --- credential store ---------------------------------------------------------------

def test_api_key_roundtrip_and_isolation(isolated_config):
    assert opconfig.api_key_present("anthropic") is False
    opconfig.set_api_key("anthropic", "sk-ant-secret")
    assert opconfig.api_key("anthropic") == "sk-ant-secret"
    assert opconfig.api_key_present("anthropic") is True

    # Stored only in the credential file, with owner-only perms.
    assert opconfig.SECRETS_PATH.exists()
    mode = stat.S_IMODE(os.stat(opconfig.SECRETS_PATH).st_mode)
    assert mode == 0o600
    assert "sk-ant-secret" in opconfig.SECRETS_PATH.read_text()

    # Clearing removes it; a different provider is unaffected.
    opconfig.set_api_key("openai", "sk-openai")
    opconfig.set_api_key("anthropic", "")
    assert opconfig.api_key_present("anthropic") is False
    assert opconfig.api_key("openai") == "sk-openai"


def test_env_var_takes_precedence(isolated_config, monkeypatch):
    opconfig.set_api_key("openai", "stored-key")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assert opconfig.api_key("openai") == "env-key"


def test_key_never_leaks_into_config_or_export(client):
    client.post("/api/settings/api-key", json={"provider_id": "openai", "key": "sk-leaky"})
    # Not in the (backup-safe) config file …
    if opconfig.CONFIG_PATH.exists():
        assert "sk-leaky" not in opconfig.CONFIG_PATH.read_text()
    # … not surfaced by the settings payload …
    payload = client.get("/api/settings").json()
    assert "sk-leaky" not in str(payload)
    assert payload["ai_key_present"]["openai"] is True
    # … and not in the workspace export.
    dump = client.get("/api/settings/export").text
    assert "sk-leaky" not in dump


# --- provider resolution ------------------------------------------------------------

def test_ai_ready_keyless_local_provider(client):
    # Ollama needs no key — selecting it makes the gateway ready immediately.
    client.post("/api/settings", json={"updates": {"ai": {
        "provider": "openai", "provider_id": "ollama",
    }}})
    assert opconfig.ai_ready() is True
    health = client.get("/api/settings").json()["health"]
    assert health["ai_configured"] is True


def test_key_required_provider_needs_a_key(client):
    client.post("/api/settings", json={"updates": {"ai": {
        "provider": "openai", "provider_id": "anthropic",
    }}})
    assert opconfig.ai_ready() is False
    client.post("/api/settings/api-key", json={"provider_id": "anthropic", "key": "sk-ant-x"})
    assert opconfig.ai_ready() is True


def test_provider_id_resolves_base_url(client):
    client.post("/api/settings", json={"updates": {"ai": {
        "provider": "openai", "provider_id": "anthropic",
        "base_url": "https://api.anthropic.com/v1/",
    }}})
    assert opconfig.resolved_base_url() == "https://api.anthropic.com/v1/"
    # A blank override falls back to the preset default for the provider.
    client.post("/api/settings", json={"updates": {"ai": {"base_url": None}}})
    assert opconfig.resolved_base_url("gemini").startswith("https://generativelanguage")


def test_providers_registry_exposed(client):
    body = client.get("/api/settings").json()
    ids = {p["id"] for p in body["ai_providers"]}
    assert {"openai", "anthropic", "gemini", "openrouter", "groq", "ollama", "custom"} <= ids
    ollama = next(p for p in body["ai_providers"] if p["id"] == "ollama")
    assert ollama["requires_key"] is False


# --- schedules ----------------------------------------------------------------------

def test_schedules_are_editable(client):
    client.post("/api/settings", json={"updates": {"schedules": {"bulk_refresh": "monthly"}}})
    schedules = client.get("/api/settings").json()["config"]["schedules"]
    assert schedules["bulk_refresh"] == "monthly"
    # Other cadences untouched by a single-key update.
    assert schedules["data_sync"] == "daily"


def test_automation_hint_present(client):
    auto = client.get("/api/settings").json()["automation"]
    assert auto["command"] == "npm run sync"
    assert "daily" in auto["cron"] and "weekly" in auto["cron"]


# --- gateway re-resolution ----------------------------------------------------------

def test_gateway_invalidates_on_provider_change(client, stores):
    gateway = ai.AIGateway(stores)
    ai.set_ai(gateway)
    try:
        client.post("/api/settings", json={"updates": {"ai": {
            "provider": "openai", "provider_id": "ollama",
        }}})
        # The save route invalidates the shared gateway; a keyless local
        # provider resolves to the live HTTP path, not stub.
        assert gateway.provider == "openai"
    finally:
        ai.set_ai(None)


def test_settings_health_carries_strip_fields(client, stores):
    """The Settings health strip reads ok/has_constitution/schema from THIS
    payload — they were missing, leaving three chips permanently blank."""
    h = client.get("/api/settings").json()["health"]
    assert h["ok"] is True
    assert h["has_constitution"] is False          # fresh test workspace
    assert isinstance(h["workspace_schema_version"], int)
    assert "ai_provider" in h


def test_test_ai_reports_forced_stub_honestly(client, monkeypatch):
    monkeypatch.setenv("FUNDOPS_AI_PROVIDER", "stub")
    out = client.post("/api/settings/test-ai").json()
    assert out["ok"] is False
    assert "offline stub mode" in out["error"]
    assert "PATH" not in out["error"]  # never blame the CLI for an env override
