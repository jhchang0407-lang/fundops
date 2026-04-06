"""
Shared LLM client for FundOps.

Model-agnostic async client that all agents share. Supports OpenAI Responses API
(with optional web search), cost tracking per agent, and retry logic.

Usage:
    from backend.core.llm import LLMClient

    llm = LLMClient(config)
    result = await llm.generate(
        prompt="Analyze this company...",
        agent="thesis",
        reasoning_effort="high",
    )
    # result.text, result.tokens_in, result.tokens_out, result.cost, result.duration_s
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("fundops.llm")


class BudgetExceededError(Exception):
    """Raised when an agent's LLM cost exceeds its budget."""
    def __init__(self, agent: str, spent: float, budget: float):
        self.agent = agent
        self.spent = spent
        self.budget = budget
        super().__init__(
            f"Agent '{agent}' exceeded cost budget: "
            f"${spent:.4f} spent, ${budget:.2f} limit"
        )


# Default per-agent budgets (USD per pipeline run)
_DEFAULT_BUDGETS = {
    "codegen": 0.50,
    "thesis": 2.00,
    "ic_review": 1.00,
    "memo": 5.00,
    "screener": 1.00,
    "allocator": 1.00,
    "strategy_conversation_extract": 0.10,
    "default": 3.00,
}


@dataclass
class LLMResult:
    """Result from an LLM call."""
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    duration_s: float = 0.0
    model: str = ""
    agent: str = ""
    cached: bool = False


@dataclass
class TwoPassResult:
    """Result from a two-pass LLM call (conversation + extraction)."""
    raw_text: str            # Pass 1 unconstrained output
    extracted: dict          # Pass 2 parsed JSON
    pass1: LLMResult         # Full result from pass 1
    pass2: Optional[LLMResult]  # Full result from pass 2 (None if skipped)
    total_cost: float        # Sum of both passes
    total_duration_s: float  # Sum of both durations


# Rough per-token costs (USD) — updated as pricing changes
_MODEL_COSTS = {
    "gpt-5-mini": {"input": 0.40 / 1_000_000, "output": 1.60 / 1_000_000},
    "gpt-4.1-mini": {"input": 0.40 / 1_000_000, "output": 1.60 / 1_000_000},
    "gpt-4.1": {"input": 2.00 / 1_000_000, "output": 8.00 / 1_000_000},
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.0 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
}


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    costs = _MODEL_COSTS.get(model, {"input": 1.0 / 1_000_000, "output": 3.0 / 1_000_000})
    return tokens_in * costs["input"] + tokens_out * costs["output"]


def _sanitize_llm_output(text: str) -> str:
    """Strip HTML tags from LLM output to prevent stored XSS."""
    import re
    return re.sub(r'<[^>]+>', '', text)


def _extract_text(response) -> str:
    """Extract text from an OpenAI Responses API response object."""
    text = ""
    for block in (response.output or []):
        content = getattr(block, "content", None)
        if content:
            for c in content:
                t = getattr(c, "text", None)
                if t:
                    text += t
        t = getattr(block, "text", None)
        if t and isinstance(t, str):
            text += t
    if not text and hasattr(response, "output_text"):
        text = response.output_text or ""
    return _sanitize_llm_output(text)


def _extract_usage(response) -> tuple[int, int]:
    """Extract token counts from response."""
    usage = getattr(response, "usage", None)
    if usage:
        return (
            getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0,
        )
    return 0, 0


class LLMClient:
    """Shared LLM client with retry logic and cost tracking."""

    def __init__(self, config: dict | None = None):
        """
        Args:
            config: ai_model section from workflow.yaml. Keys:
                provider, model, api_key, max_retries, timeout_s
        """
        config = config or {}
        self.provider = config.get("provider", "openai")
        self.model = config.get("model", "gpt-5-mini")
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", None)
        self.max_retries = config.get("max_retries", 2)
        self.timeout_s = config.get("timeout_s", 120)
        self._client = None
        self._cost_log: list[dict] = []
        self._agent_budgets: dict[str, float] = {
            **_DEFAULT_BUDGETS,
            **config.get("agent_budgets", {}),
        }
        self._prompt_db_path: str = config.get("db_path", str(Path.home() / ".fundops" / "fundops.db"))
        self._track_prompts: bool = config.get("track_prompts", True)

    def _get_client(self):
        """Lazy-init the OpenAI-compatible client."""
        if self._client is None:
            from openai import AsyncOpenAI
            kwargs = {
                "api_key": self.api_key,
                "timeout": self.timeout_s,
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def generate(
        self,
        prompt: str,
        agent: str = "",
        model: str | None = None,
        reasoning_effort: str = "medium",
        system: str | None = None,
        response_format: dict | None = None,
    ) -> LLMResult:
        """
        Generate text using the configured LLM.

        Args:
            prompt: The input prompt.
            agent: Agent name for cost tracking (e.g., "thesis", "ic_review").
            model: Override model for this call.
            reasoning_effort: "low", "medium", or "high".
            system: Optional system message prepended to input.
            response_format: OpenAI structured output spec. E.g.:
                {"type": "json_schema", "name": "my_schema",
                 "schema": {...}, "strict": True}
        """
        use_model = model or self.model
        client = self._get_client()

        full_input = prompt
        if system:
            full_input = f"{system}\n\n{prompt}"

        kwargs: dict[str, Any] = {
            "model": use_model,
            "input": full_input,
        }
        # reasoning.effort is only supported on o-series models (o1, o3, o4, etc.)
        if reasoning_effort and use_model.startswith(("o1", "o3", "o4")):
            kwargs["reasoning"] = {"effort": reasoning_effort}

        # Structured output enforcement via OpenAI text.format
        if response_format:
            kwargs["text"] = {"format": response_format}

        return await self._call_with_retry(client, kwargs, agent, use_model)

    async def generate_chat(
        self,
        messages: list[dict],
        agent: str = "",
        model: str | None = None,
        reasoning_effort: str = "medium",
        response_format: dict | None = None,
    ) -> LLMResult:
        """Multi-turn chat. messages = [{"role": "system"|"user"|"assistant", "content": "..."}].

        Uses the OpenAI Responses API with messages as input.
        """
        use_model = model or self.model
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": use_model,
            "input": messages,
        }
        # reasoning.effort is only supported on o-series models (o1, o3, o4, etc.)
        if reasoning_effort and use_model.startswith(("o1", "o3", "o4")):
            kwargs["reasoning"] = {"effort": reasoning_effort}

        if response_format:
            kwargs["text"] = {"format": response_format}

        return await self._call_with_retry(client, kwargs, agent, use_model)

    @classmethod
    def _fix_extracted_multiples(cls, data: Any) -> Any:
        """Recursively fix multiples notation in extracted dict/list/string values.

        This ensures that strategy dimensions, agent configs, and all structured
        data flowing into scoring code, IC review, and thesis never contain
        "P/E = 40%" — they always get "P/E = 40x".
        """
        if isinstance(data, str):
            return cls.fix_multiples_notation(data)
        elif isinstance(data, dict):
            return {k: cls._fix_extracted_multiples(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls._fix_extracted_multiples(item) for item in data]
        return data

    @staticmethod
    def fix_multiples_notation(text: str) -> str:
        """Deterministic post-processing: fix valuation multiples expressed as percentages.

        Models frequently write "P/E = 40%" when they mean "P/E = 40x".
        This is a hard rule: ratios (P/E, EV/Sales, EV/EBITDA, P/B, P/FCF, P/S)
        NEVER use % — they always use "x". This regex catches and fixes the error.
        """
        import re
        # Pattern: (multiple_name)(optional spaces)(operator)(optional spaces)(number)(%)
        # Multiple names: P/E, PE, EV/Sales, EV/EBITDA, EV/EBIT, P/B, PB, P/S, PS, P/FCF, EV/Revenue
        multiple_pattern = r'(?:P/?E|EV/?(?:Sales|EBITDA|EBIT|Revenue|FCF)|P/?B|P/?S|P/?FCF|PEG)\b'

        def _fix_match(m):
            prefix = m.group(1)  # The multiple name
            middle = m.group(2)  # operator + number
            # Replace trailing % with x
            return prefix + middle + 'x'

        # Match: multiple_name ... number%  (where % should be x)
        # e.g. "P/E = 40%" → "P/E = 40x", "EV/Sales < 10%" → "EV/Sales < 10x"
        fixed = re.sub(
            rf'({multiple_pattern})'           # Group 1: the multiple name
            rf'(\s*(?:[=<>≤≥]=?\s*)?'          # Group 2: optional operator
            rf'\d+(?:\.\d+)?)'                 # number
            r'%',                              # the wrong % sign
            _fix_match,
            text,
            flags=re.IGNORECASE,
        )

        return fixed

    async def generate_then_extract(
        self,
        messages: list[dict],
        extraction_system: str,
        extraction_schema: dict,
        agent: str = "",
        model: str | None = None,
        extraction_model: str | None = None,
        reasoning_effort: str = "medium",
        extraction_reasoning_effort: str = "low",
    ) -> TwoPassResult:
        """Two-pass LLM call: unconstrained conversation + structured extraction.

        Pass 1: generate_chat with no response_format (model thinks freely).
        Pass 2: generate with json_schema (cheap model extracts structure).
        """
        import json as _json

        # Pass 1: Unconstrained conversation
        pass1_result = await self.generate_chat(
            messages=messages,
            agent=agent,
            model=model,
            reasoning_effort=reasoning_effort,
        )

        # Deterministic fix: correct multiples expressed as percentages
        pass1_result = LLMResult(
            text=self.fix_multiples_notation(pass1_result.text),
            tokens_in=pass1_result.tokens_in,
            tokens_out=pass1_result.tokens_out,
            cost=pass1_result.cost,
            duration_s=pass1_result.duration_s,
            model=pass1_result.model,
        )

        # If Pass 1 returned nothing, skip Pass 2
        if not pass1_result.text.strip():
            empty_extracted = {
                "message": "",
                "options": [],
                "extracted": {},
                "dimensions_complete": [],
                "is_complete": False,
                "strategy_profile": None,
                "agent_actions": [],
                "memory_updates": [],
            }
            return TwoPassResult(
                raw_text="",
                extracted=empty_extracted,
                pass1=pass1_result,
                pass2=None,
                total_cost=pass1_result.cost,
                total_duration_s=pass1_result.duration_s,
            )

        # Pass 2: Structured extraction
        # Include the last user message so the extractor can detect corrections
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg["content"]
                break

        extraction_prompt = (
            f"Extract structured data from this conversation turn.\n\n"
            f"---\nUSER MESSAGE:\n---\n{last_user_msg}\n\n"
            f"---\nASSISTANT RESPONSE:\n---\n{pass1_result.text}"
        )

        extraction_response_format = {
            "type": "json_schema",
            "name": "strategy_extraction",
            "schema": extraction_schema,
            "strict": False,
        }

        try:
            pass2_result = await self.generate(
                prompt=extraction_prompt,
                agent=agent + "_extract",
                model=extraction_model or "gpt-4.1-mini",
                reasoning_effort=extraction_reasoning_effort,
                system=extraction_system,
                response_format=extraction_response_format,
            )
            extracted = _json.loads(pass2_result.text)
        except Exception as e:
            log.warning(f"Pass 2 extraction failed ({e}), falling back to raw text")
            extracted = {
                "message": pass1_result.text,
                "options": [],
                "extracted": {},
                "dimensions_complete": [],
                "is_complete": False,
                "strategy_profile": None,
                "agent_actions": [],
                "memory_updates": [],
            }
            pass2_result = None

        # Deterministic fix on extracted data too — multiples in strategy
        # dimensions, agent configs, etc. must never be percentages
        extracted = self._fix_extracted_multiples(extracted)

        total_cost = pass1_result.cost + (pass2_result.cost if pass2_result else 0)
        total_duration = pass1_result.duration_s + (pass2_result.duration_s if pass2_result else 0)

        return TwoPassResult(
            raw_text=pass1_result.text,
            extracted=extracted,
            pass1=pass1_result,
            pass2=pass2_result,
            total_cost=total_cost,
            total_duration_s=total_duration,
        )

    async def generate_with_search(
        self,
        prompt: str,
        agent: str = "",
        model: str | None = None,
        reasoning_effort: str = "medium",
        search_context_size: str = "medium",
    ) -> LLMResult:
        """
        Generate text with web search enabled (OpenAI web_search_preview tool).

        Args:
            prompt: The search/analysis prompt.
            agent: Agent name for cost tracking.
            model: Override model.
            reasoning_effort: "low", "medium", or "high".
            search_context_size: "low", "medium", or "high".
        """
        use_model = model or self.model
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": use_model,
            "input": prompt,
            "tools": [{"type": "web_search_preview", "search_context_size": search_context_size}],
        }
        # reasoning.effort is only supported on o-series models (o1, o3, o4, etc.)
        if reasoning_effort and use_model.startswith(("o1", "o3", "o4")):
            kwargs["reasoning"] = {"effort": reasoning_effort}

        return await self._call_with_retry(client, kwargs, agent, use_model)

    async def _call_with_retry(
        self, client, kwargs: dict, agent: str, model: str
    ) -> LLMResult:
        """Execute API call with retry logic and budget enforcement."""
        # Check budget before calling
        budget = self._agent_budgets.get(agent, self._agent_budgets.get("default", 3.0))
        spent = sum(e["cost"] for e in self._cost_log if e["agent"] == agent)
        if spent >= budget:
            raise BudgetExceededError(agent, spent, budget)

        last_error = None
        for attempt in range(self.max_retries + 1):
            t0 = time.time()
            try:
                response = await client.responses.create(**kwargs)
                elapsed = time.time() - t0

                text = _extract_text(response)
                tokens_in, tokens_out = _extract_usage(response)
                cost = _estimate_cost(model, tokens_in, tokens_out)

                result = LLMResult(
                    text=text,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost=cost,
                    duration_s=elapsed,
                    model=model,
                    agent=agent,
                )

                # Track prompt version if enabled
                prompt_hash = ""
                if self._track_prompts and agent:
                    try:
                        import hashlib
                        prompt_text = str(kwargs.get("input", ""))
                        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:16]
                        # Persist to DB (best-effort, non-blocking)
                        from backend.core.evidence import version_prompt
                        import sqlite3
                        pconn = sqlite3.connect(str(self._prompt_db_path), timeout=10)
                        version_prompt(pconn, agent, prompt_text)
                        pconn.close()
                    except Exception:
                        pass  # Non-critical

                self._cost_log.append({
                    "agent": agent,
                    "model": model,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost": cost,
                    "duration_s": elapsed,
                    "timestamp": time.time(),
                    "prompt_hash": prompt_hash,
                })

                log.info(
                    f"[{agent}] LLM call: {elapsed:.1f}s, "
                    f"{tokens_in}+{tokens_out} tokens, ${cost:.4f}"
                )
                return result

            except Exception as e:
                elapsed = time.time() - t0
                last_error = e
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    log.warning(
                        f"[{agent}] LLM retry {attempt+1}/{self.max_retries} "
                        f"after {elapsed:.1f}s: {e}"
                    )
                    await asyncio.sleep(wait)
                else:
                    log.error(f"[{agent}] LLM failed after {self.max_retries+1} attempts: {e}")

        return LLMResult(
            text="",
            duration_s=time.time() - t0,
            model=model,
            agent=agent,
        )

    def get_cost_summary(self, agent: str | None = None) -> dict:
        """Get cost summary, optionally filtered by agent."""
        entries = self._cost_log
        if agent:
            entries = [e for e in entries if e["agent"] == agent]

        total_cost = sum(e["cost"] for e in entries)
        total_calls = len(entries)
        total_tokens = sum(e["tokens_in"] + e["tokens_out"] for e in entries)

        by_agent: dict[str, dict] = {}
        for e in self._cost_log:
            a = e["agent"]
            if a not in by_agent:
                by_agent[a] = {"calls": 0, "tokens": 0, "cost": 0.0}
            by_agent[a]["calls"] += 1
            by_agent[a]["tokens"] += e["tokens_in"] + e["tokens_out"]
            by_agent[a]["cost"] += e["cost"]

        return {
            "total_cost": round(total_cost, 4),
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "by_agent": by_agent,
        }

    def reset_cost_log(self):
        """Clear cost tracking (e.g., weekly reset)."""
        self._cost_log.clear()

    def reset_agent_budget(self, agent: str):
        """Clear cost entries for a specific agent, resetting its budget."""
        self._cost_log = [e for e in self._cost_log if e["agent"] != agent]

    def reset_all_budgets(self):
        """Clear all cost entries, resetting all agent budgets."""
        self._cost_log.clear()
