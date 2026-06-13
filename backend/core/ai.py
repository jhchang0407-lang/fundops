"""AI gateway: bounded, recorded, tiered model calls.

Every call goes through `AIGateway.complete_json`, which:
- picks the model tier (fast = extraction/classification/summaries,
  deep = thesis/IC/memo/strategy/learning),
- forces structured JSON output against a caller-supplied shape hint,
- records an AI Usage Record and Execution Provenance Record (ADR-0034),
- caches identical calls in-process so re-renders never re-spend,
- falls back to a deterministic stub when no API key is configured, so the
  product remains usable offline; stub outputs are marked in provenance.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from backend.core import opconfig

PROMPT_VERSION = "2026.06-1"

# Rough public price table for *estimated* cost only (not billing truth).
_PRICES_PER_MTOK = {
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5.2": (1.25, 10.0),
    "gpt-5": (1.25, 10.0),
}


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    for prefix, (pin, pout) in _PRICES_PER_MTOK.items():
        if model.startswith(prefix):
            return round(tokens_in / 1e6 * pin + tokens_out / 1e6 * pout, 6)
    return None


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"[\[{].*[\]}]", text, re.S)
        if match:
            return json.loads(match.group(0))
        raise


class AIError(RuntimeError):
    pass


# Harness CLI presets (ADR-0060): the user's coding-agent session in headless
# mode acts as the model provider, using its own subscription auth. Output is
# normalized by the same JSON shape contract + deterministic validation that
# governs every other provider.
AGENT_CLI_PRESETS = {
    "claude": ["claude", "-p", "{prompt}", "--output-format", "json"],
    "codex": ["codex", "exec", "{prompt}"],
}


class AIGateway:
    def __init__(self, stores=None):
        self._stores = stores
        self._client = None
        self._cache: dict[str, Any] = {}

    @property
    def stores(self):
        if self._stores is None:
            from backend.stores import get_stores
            self._stores = get_stores()
        return self._stores

    @staticmethod
    def _agent_cli_command() -> list[str] | None:
        import shutil
        cfg = opconfig.load()["ai"]["agent_cli"]
        cmd = cfg.get("command") or AGENT_CLI_PRESETS.get(cfg.get("preset", "claude"))
        if not cmd or shutil.which(cmd[0]) is None:
            return None
        return cmd

    @property
    def provider(self) -> str:
        """Resolved provider: the explicitly configured choice when its
        prerequisite (API key / CLI binary) is present, else 'stub'.

        agent_cli is strictly opt-in — FundOps must never silently spend the
        user's coding-agent subscription just because the binary is on PATH.
        FUNDOPS_AI_PROVIDER overrides everything (tests force 'stub')."""
        override = os.environ.get("FUNDOPS_AI_PROVIDER")
        if override:
            if override == "agent_cli" and not self._agent_cli_command():
                return "stub"
            if override in ("openai", "api") and not opconfig.ai_ready():
                return "stub"
            return "openai" if override == "api" else override
        choice = opconfig.load()["ai"].get("provider", "openai")
        if choice == "agent_cli" and self._agent_cli_command():
            return "agent_cli"
        # "openai" here is the OpenAI-compatible HTTP transport for any preset
        # (OpenAI/Anthropic/Gemini/OpenRouter/Groq/Ollama/custom); ai_ready()
        # allows keyless local endpoints as well as key-bearing ones.
        if choice in ("openai", "api") and opconfig.ai_ready():
            return "openai"
        return "stub"

    @property
    def configured(self) -> bool:
        return self.provider != "stub"

    def _openai(self):
        if self._client is None:
            from openai import AsyncOpenAI
            cfg = opconfig.ai_settings()
            # Keyless local endpoints (Ollama) still need a non-empty key for the
            # SDK; the server ignores it.
            kwargs: dict = {
                "api_key": cfg["api_key"] or "not-needed",
                "timeout": cfg.get("timeout_s", 180),
            }
            if cfg.get("base_url"):
                kwargs["base_url"] = cfg["base_url"]
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def invalidate(self) -> None:
        """Drop the cached HTTP client and the in-process response cache so a
        provider / key / model / base-URL change takes effect on the next call."""
        self._client = None
        self._cache.clear()

    async def complete_json(
        self,
        capability: str,
        system: str,
        user: str,
        shape_hint: str,
        tier: str = "fast",
        run_id: str | None = None,
        max_output_tokens: int = 4000,
        stub: Any | None = None,
    ) -> Any:
        """One bounded structured call. `shape_hint` describes the exact JSON
        to return; `stub` is the deterministic offline fallback payload (a value
        or a callable taking the cache seed int)."""
        cfg = opconfig.ai_settings()
        model = cfg["model_deep"] if tier == "deep" else cfg["model_fast"]
        cache_key = hashlib.sha256(
            f"{model}|{PROMPT_VERSION}|{system}|{user}|{shape_hint}".encode()
        ).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        provider = self.provider
        if provider == "stub":
            result = self._stub_result(stub, cache_key)
            self.stores.ops.record_provenance(
                step=capability, kind="model", run_id=run_id, model="stub",
                prompt_version=PROMPT_VERSION,
                validation={"ok": True, "note": "no model provider configured; deterministic stub"},
            )
            self._cache[cache_key] = result
            return result

        prompt = (
            f"{user}\n\nReturn ONLY valid JSON matching exactly this shape "
            f"(no prose, no markdown fences):\n{shape_hint}"
        )

        if provider == "agent_cli":
            result = await self._complete_agent_cli(capability, system, prompt, run_id)
            self._cache[cache_key] = result
            return result
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                resp = await self._openai().chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": prompt}],
                    max_completion_tokens=max_output_tokens,
                )
                text = resp.choices[0].message.content or ""
                tokens_in = getattr(resp.usage, "prompt_tokens", 0) or 0
                tokens_out = getattr(resp.usage, "completion_tokens", 0) or 0
                self.stores.ops.record_ai_usage(
                    capability, model, tokens_in, tokens_out,
                    _estimate_cost(model, tokens_in, tokens_out), run_id,
                )
                result = _extract_json(text)
                self.stores.ops.record_provenance(
                    step=capability, kind="model", run_id=run_id, model=model,
                    prompt_version=PROMPT_VERSION,
                    usage={"tokens_in": tokens_in, "tokens_out": tokens_out},
                    validation={"ok": True},
                )
                self._cache[cache_key] = result
                return result
            except json.JSONDecodeError as exc:
                last_err = exc
                self.stores.ops.record_provenance(
                    step=capability, kind="model", run_id=run_id, model=model,
                    prompt_version=PROMPT_VERSION,
                    validation={"ok": False, "error": f"invalid JSON: {exc}"},
                    rejected_output=(text[:4000] if "text" in dir() else None),
                )
            except Exception as exc:  # provider/network errors
                last_err = exc
        raise AIError(f"{capability}: model call failed after retries: {last_err}")

    async def _complete_agent_cli(self, capability: str, system: str, prompt: str,
                                  run_id: str | None) -> Any:
        """One bounded structured call through the user's coding-agent harness
        in headless mode (ADR-0060). The harness's own auth is used; output is
        held to the same JSON contract as any other provider."""
        import asyncio

        cmd_template = self._agent_cli_command()
        if not cmd_template:
            raise AIError(f"{capability}: agent CLI not available")
        cfg = opconfig.load()["ai"]["agent_cli"]
        full_prompt = f"{system}\n\n{prompt}"
        cmd = [part.replace("{prompt}", full_prompt) for part in cmd_template]
        label = f"agent_cli:{cfg.get('preset', 'custom')}"
        last_err: Exception | None = None
        for _attempt in range(2):
            text = ""
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                try:
                    out, err = await asyncio.wait_for(
                        proc.communicate(), timeout=cfg.get("timeout_s", 300)
                    )
                except asyncio.TimeoutError:
                    proc.kill()  # don't leave a hung CLI running while we retry
                    try:
                        await proc.wait()
                    except Exception:
                        pass
                    raise
                if proc.returncode != 0:
                    raise AIError(f"agent CLI exited {proc.returncode}: {err.decode()[:300]}")
                text = out.decode()
                tokens_in = tokens_out = 0
                # Claude headless --output-format json wraps the answer in an
                # envelope with `result` + usage metadata; unwrap when present.
                try:
                    envelope = json.loads(text)
                    if isinstance(envelope, dict) and "result" in envelope:
                        usage = envelope.get("usage") or {}
                        tokens_in = int(usage.get("input_tokens", 0) or 0)
                        tokens_out = int(usage.get("output_tokens", 0) or 0)
                        text = envelope["result"]
                except json.JSONDecodeError:
                    pass
                result = _extract_json(text)
                self.stores.ops.record_ai_usage(capability, label, tokens_in, tokens_out, None, run_id)
                self.stores.ops.record_provenance(
                    step=capability, kind="model", run_id=run_id, model=label,
                    prompt_version=PROMPT_VERSION,
                    usage={"tokens_in": tokens_in, "tokens_out": tokens_out},
                    validation={"ok": True},
                )
                return result
            except json.JSONDecodeError as exc:
                last_err = exc
                self.stores.ops.record_provenance(
                    step=capability, kind="model", run_id=run_id, model=label,
                    prompt_version=PROMPT_VERSION,
                    validation={"ok": False, "error": f"invalid JSON: {exc}"},
                    rejected_output=text[:4000] if text else None,
                )
            except (OSError, asyncio.TimeoutError, AIError) as exc:
                last_err = exc
        raise AIError(f"{capability}: agent CLI call failed after retries: {last_err}")

    @staticmethod
    def _stub_result(stub: Any, cache_key: str) -> Any:
        seed = int(cache_key[:8], 16)
        if callable(stub):
            return stub(seed)
        if stub is not None:
            return stub
        return {}


_gateway: AIGateway | None = None


def get_ai() -> AIGateway:
    global _gateway
    if _gateway is None:
        _gateway = AIGateway()
    return _gateway


def set_ai(gateway: AIGateway | None) -> None:
    global _gateway
    _gateway = gateway
