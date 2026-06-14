"""AI provider presets.

FundOps talks to models over the OpenAI-compatible Chat Completions API, so any
endpoint that speaks it works with the same client — only the base URL, model
names, and key change. These presets prefill those for the common providers; the
user can edit the model names (and base URL, for Custom) freely. The actual model
work always flows through `AIGateway.complete_json`, unchanged.

`requires_key=False` means a local/keyless endpoint (e.g. Ollama) — the gateway
sends a placeholder key the OpenAI SDK accepts but the server ignores.
"""

from __future__ import annotations

# Order here is the order shown in the Settings dropdown.
AI_PROVIDERS: dict[str, dict] = {
    "openai": {
        "label": "OpenAI",
        "base_url": None,  # SDK default (api.openai.com)
        "model_fast": "gpt-5-mini",
        "model_deep": "gpt-5.2",
        "requires_key": True,
        "env": "OPENAI_API_KEY",
        "key_hint": "sk-…",
        "console_url": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "base_url": "https://api.anthropic.com/v1/",
        "model_fast": "claude-haiku-4-5",
        "model_deep": "claude-sonnet-4-6",
        "requires_key": True,
        "env": "ANTHROPIC_API_KEY",
        "key_hint": "sk-ant-…",
        "console_url": "https://console.anthropic.com/settings/keys",
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model_fast": "gemini-2.5-flash",
        "model_deep": "gemini-2.5-pro",
        "requires_key": True,
        "env": "GEMINI_API_KEY",
        "key_hint": "AIza…",
        "console_url": "https://aistudio.google.com/apikey",
    },
    "openrouter": {
        "label": "OpenRouter (any model)",
        "base_url": "https://openrouter.ai/api/v1",
        "model_fast": "openai/gpt-5-mini",
        "model_deep": "anthropic/claude-sonnet-4-6",
        "requires_key": True,
        "env": "OPENROUTER_API_KEY",
        "key_hint": "sk-or-…",
        "console_url": "https://openrouter.ai/keys",
    },
    "groq": {
        "label": "Groq (fast inference)",
        "base_url": "https://api.groq.com/openai/v1",
        "model_fast": "llama-3.3-70b-versatile",
        "model_deep": "llama-3.3-70b-versatile",
        "requires_key": True,
        "env": "GROQ_API_KEY",
        "key_hint": "gsk_…",
        "console_url": "https://console.groq.com/keys",
    },
    "ollama": {
        "label": "Local (Ollama)",
        "base_url": "http://localhost:11434/v1",
        "model_fast": "llama3.1",
        "model_deep": "llama3.1:70b",
        "requires_key": False,
        "env": None,
        "key_hint": "not required — runs on your machine",
        "console_url": "https://ollama.com/library",
    },
    "custom": {
        "label": "Custom (OpenAI-compatible)",
        "base_url": "",  # user supplies
        "model_fast": "",
        "model_deep": "",
        "requires_key": False,  # optional — some local gateways need none
        "env": None,
        "key_hint": "optional, depends on the endpoint",
        "console_url": None,
    },
}

DEFAULT_PROVIDER_ID = "openai"


def get_preset(provider_id: str | None) -> dict:
    return AI_PROVIDERS.get(provider_id or DEFAULT_PROVIDER_ID, AI_PROVIDERS[DEFAULT_PROVIDER_ID])


def public_registry() -> list[dict]:
    """Preset metadata for the Settings UI (no secrets)."""
    return [{"id": pid, **{k: v for k, v in spec.items()}} for pid, spec in AI_PROVIDERS.items()]
