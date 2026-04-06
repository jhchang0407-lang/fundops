"""FundOps Configuration System.

Loads workflow.yaml, resolves ${ENV_VAR} references, and provides typed access.
The dashboard setup wizard generates this config via from_wizard().

Auto-validates on init and logs warnings for missing env vars.
"""

from __future__ import annotations

import logging
import os
import re

log = logging.getLogger("fundops.config")
import yaml
from pathlib import Path
from typing import Any, Optional


DEFAULT_CONFIG_PATH = Path("config/workflow.yaml")

# Default values for a new installation
DEFAULT_WORKFLOW = {
    "name": "My Investment Pipeline",
    "description": "Customize this to match your investment strategy",
    "connectors": {
        "market_data": {
            "provider": "fmp",
            "api_key": "${FMP_API_KEY}",
            "rate_limit": {"requests_per_batch": 10, "delay_between_batches_s": 2},
        },
        "filings": {
            "provider": "sec_edgar",
            "user_agent": "${SEC_USER_AGENT}",
        },
        "ai_model": {
            "provider": "openai",
            "model": "gpt-5-mini",
            "api_key": "${OPENAI_API_KEY}",
        },
    },
    "agents": {
        "screener": {
            "schedule": "weekly",
            "config": {
                "hurdle_pct": 15,
                "lenses": [
                    {"name": "dislocation", "weights": {"cheapness": 0.70, "quality": 0.15, "health": 0.10, "growth": 0.05}},
                    {"name": "compounder", "weights": {"quality": 0.50, "cheapness": 0.30, "growth_durability": 0.20}},
                ],
                "handoff": {
                    "min_expected_return_pct": 20,
                    "min_gross_margin_pct": 30,
                    "must_be_profitable": True,
                    "max_debt_equity": 3.0,
                    "max_candidates": 20,
                },
            },
        },
        "thesis": {
            "config": {
                "web_search": True,
                "web_search_intensity": "high",
                "condense_research": True,
                "max_research_words": 2000,
            },
        },
        "ic_review": {
            "config": {
                "hurdle_base_pct": 20,
                "hurdle_bear_pct": 15,
                "ai_review": True,
                "style_profile": "concentrated, quality-at-a-discount, anti-value-trap, 3-5yr compounder",
                "growth_aware_discounts": {
                    "high_growth": {"min_growth": 15, "min_gm": 60, "min_discount": 15},
                    "moderate": {"min_growth": 10, "min_gm": 50, "min_discount": 20},
                    "steady_state": {"min_discount": 30},
                },
            },
        },
        "memo": {
            "config": {"cost_limit_per_week": 5.0, "sector_specific_valuation": True},
        },
        "library": {
            "schedule": "daily",
            "config": {"track_performance_vs": "SPY"},
        },
        "portfolio": {
            "schedule": "daily",
            "config": {
                "held_only": True,
                "thesis_health_check": True,
                "alert_on": {
                    "concentration_above_pct": 20,
                    "drawdown_below_pct": -15,
                },
            },
        },
        "allocator": {
            "config": {
                "position_types": {
                    "tactical": {"weight_range": [3, 5], "hold_years": "1-2"},
                    "core_compounder": {"weight_range": [5, 10], "hold_years": "3-5"},
                    "balanced": {"weight_range": [4, 7], "hold_years": "2-4"},
                },
                "concentration_limit_pct": 25,
            },
        },
    },
}

# Strategy presets for the setup wizard
STRATEGY_PRESETS = {
    "value": {
        "name": "Value Investing",
        "description": "Quality businesses at a discount, 3-5 year horizon, targeting 20% returns",
        "screener": {
            "hurdle_pct": 15,
            "lenses": [
                {"name": "dislocation", "weights": {"cheapness": 0.70, "quality": 0.15, "health": 0.10, "growth": 0.05}},
                {"name": "compounder", "weights": {"quality": 0.50, "cheapness": 0.30, "growth_durability": 0.20}},
            ],
            "handoff": {"min_expected_return_pct": 20, "min_gross_margin_pct": 30},
        },
        "ic_review": {"hurdle_base_pct": 20, "hurdle_bear_pct": 15},
    },
    "growth": {
        "name": "Growth Investing",
        "description": "High-growth businesses, lower discount requirement, targeting 25% returns",
        "screener": {
            "hurdle_pct": 12,
            "lenses": [
                {"name": "compounder", "weights": {"quality": 0.40, "cheapness": 0.20, "growth_durability": 0.40}},
                {"name": "dislocation", "weights": {"cheapness": 0.50, "quality": 0.25, "health": 0.10, "growth": 0.15}},
            ],
            "handoff": {"min_expected_return_pct": 18, "min_gross_margin_pct": 40},
        },
        "ic_review": {"hurdle_base_pct": 18, "hurdle_bear_pct": 12},
    },
    "dividend": {
        "name": "Dividend Income",
        "description": "Stable income, dividend safety, targeting 8-12% total return",
        "screener": {
            "hurdle_pct": 8,
            "lenses": [
                {"name": "dislocation", "weights": {"cheapness": 0.50, "quality": 0.30, "health": 0.15, "growth": 0.05}},
            ],
            "handoff": {"min_expected_return_pct": 10, "min_gross_margin_pct": 20},
        },
        "ic_review": {"hurdle_base_pct": 10, "hurdle_bear_pct": 6},
    },
}


def _resolve_env_vars(obj: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in config values."""
    if isinstance(obj, str):
        def _replace(match):
            var_name = match.group(1)
            return os.environ.get(var_name, "")
        return re.sub(r'\$\{(\w+)\}', _replace, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


class FundOpsConfig:
    """Configuration manager for FundOps.

    Loads workflow.yaml, resolves environment variables, and provides
    typed access to agent and connector configurations.
    """

    def __init__(self, config_path: Path | str = None, env_path: Path | str = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.raw: dict = {}
        self.resolved: dict = {}

        # Load .env if provided
        if env_path:
            self._load_dotenv(Path(env_path))

        # Load config
        if self.config_path.exists():
            with open(self.config_path) as f:
                self.raw = yaml.safe_load(f) or {}
        else:
            self.raw = dict(DEFAULT_WORKFLOW)

        self.resolved = _resolve_env_vars(self.raw)

        # Auto-validate and warn on missing config
        warnings = self.validate()
        for w in warnings:
            log.warning(f"Config: {w}")

    def _load_dotenv(self, path: Path) -> None:
        """Load a .env file into os.environ."""
        if not path.exists():
            return
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

    @property
    def name(self) -> str:
        return self.resolved.get("name", "FundOps Pipeline")

    @property
    def db_path(self) -> Path:
        return Path(self.resolved.get("db_path", str(Path.home() / ".fundops" / "fundops.db")))

    @property
    def data_dir(self) -> Path:
        return Path(self.resolved.get("data_dir", "data"))

    def get_connector_config(self, name: str) -> dict:
        """Get resolved config for a data connector."""
        connectors = self.resolved.get("connectors", {})
        return connectors.get(name, {})

    def get_agent_config(self, name: str) -> dict:
        """Get resolved config for an agent."""
        agents = self.resolved.get("agents", {})
        agent = agents.get(name, {})
        return agent.get("config", {})

    def get_agent_trigger(self, name: str) -> str:
        """Get the trigger expression for an agent."""
        agents = self.resolved.get("agents", {})
        agent = agents.get(name, {})
        return agent.get("trigger", agent.get("schedule", "manual"))

    def get_all_agent_names(self) -> list[str]:
        """List all configured agent names."""
        return list(self.resolved.get("agents", {}).keys())

    def validate(self) -> list[str]:
        """Validate the configuration. Returns list of error messages."""
        errors = []

        # Check connectors
        connectors = self.resolved.get("connectors", {})
        market_data = connectors.get("market_data", {})
        if not market_data.get("api_key"):
            errors.append("Missing market data API key (FMP_API_KEY)")

        ai_model = connectors.get("ai_model", {})
        if not ai_model.get("api_key"):
            errors.append("Missing AI model API key (OPENAI_API_KEY)")

        # Check agents
        agents = self.resolved.get("agents", {})
        if not agents:
            errors.append("No agents configured")

        for name, agent in agents.items():
            if not agent.get("trigger") and not agent.get("schedule"):
                errors.append(f"Agent '{name}' has no trigger or schedule")

        return errors

    def to_yaml(self) -> str:
        """Serialize config back to YAML (for wizard to save)."""
        return yaml.dump(self.raw, default_flow_style=False, sort_keys=False)

    def save(self, path: Path | str = None) -> None:
        """Write config to disk."""
        save_path = Path(path) if path else self.config_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w") as f:
            yaml.dump(self.raw, f, default_flow_style=False, sort_keys=False)

    def save_to_disk(self) -> None:
        """Sync resolved config back to raw, then persist.

        The resolved dict may have been mutated at runtime (e.g., via
        Settings UI). This copies the changes back to raw before saving.
        """
        import copy
        # Merge resolved changes back into raw (preserving env var refs)
        self.raw = copy.deepcopy(self.resolved)
        # Re-mask api_key values with ${VAR} syntax — never write literal keys to YAML.
        _connector_env_map = {
            "market_data": "FMP_API_KEY",
            "ai_model": "OPENAI_API_KEY",
            "web_search": "OPENAI_API_KEY",
        }
        for section in ("connectors",):
            if section in self.raw:
                for key, val in self.raw[section].items():
                    if isinstance(val, dict) and "api_key" in val:
                        env_var = _connector_env_map.get(key)
                        if env_var:
                            val["api_key"] = f"${{{env_var}}}"
        self.save()

    @classmethod
    def from_wizard(cls, wizard_data: dict) -> "FundOpsConfig":
        """Create a new config from setup wizard form data.

        wizard_data expected keys:
            - fmp_api_key: str
            - openai_api_key: str (optional)
            - strategy: str (value/growth/dividend/custom)
            - hurdle_base: int (base return hurdle for IC Review)
            - hurdle_bear: int (bear case hurdle for IC Review)
            - screener_hurdle: int (minimum return for screener handoff)
            - portfolio: list[dict] (optional, [{ticker, shares, cost_basis}])
        """
        config = dict(DEFAULT_WORKFLOW)

        # Apply strategy preset
        strategy = wizard_data.get("strategy", "value")
        if strategy in STRATEGY_PRESETS:
            preset = STRATEGY_PRESETS[strategy]
            config["agents"]["screener"]["config"].update(preset["screener"])
            config["agents"]["ic_review"]["config"].update(preset["ic_review"])
            config["description"] = preset["description"]

        # Override hurdles if specified
        if "hurdle_base" in wizard_data:
            config["agents"]["ic_review"]["config"]["hurdle_base_pct"] = wizard_data["hurdle_base"]
        if "hurdle_bear" in wizard_data:
            config["agents"]["ic_review"]["config"]["hurdle_bear_pct"] = wizard_data["hurdle_bear"]
        if "screener_hurdle" in wizard_data:
            config["agents"]["screener"]["config"]["hurdle_pct"] = wizard_data["screener_hurdle"]
        # Legacy key support
        if "scout_hurdle" in wizard_data:
            config["agents"]["screener"]["config"]["hurdle_pct"] = wizard_data["scout_hurdle"]

        # Set API keys as env var references (actual keys go in .env)
        if wizard_data.get("fmp_api_key"):
            os.environ["FMP_API_KEY"] = wizard_data["fmp_api_key"]
        if wizard_data.get("openai_api_key"):
            os.environ["OPENAI_API_KEY"] = wizard_data["openai_api_key"]

        instance = cls.__new__(cls)
        instance.config_path = DEFAULT_CONFIG_PATH
        instance.raw = config
        instance.resolved = _resolve_env_vars(config)
        return instance

    @classmethod
    def get_strategy_presets(cls) -> dict:
        """Return available strategy presets for the wizard."""
        return {k: {"name": v["name"], "description": v["description"]}
                for k, v in STRATEGY_PRESETS.items()}
