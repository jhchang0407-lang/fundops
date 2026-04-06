"""Intent Schema -- structured intermediate format between LLM output and scoring code.

The LLM translates strategy descriptions into Intent JSON (validated against metric_schema).
The validation layer then generates deterministic Python code from the validated intent.
This eliminates field name hallucination and logically wrong code.

Flow:
  1. LLM receives strategy profile + INTENT_JSON_SCHEMA
  2. LLM outputs Intent JSON conforming to the schema
  3. validate_intent() checks all fields, operators, ranges
  4. generate_code_from_intent() produces deterministic Python
  5. sandbox.validate_ast() + sandbox.run_in_sandbox() verify safety
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass
class ScoringRule:
    """A single scoring rule that maps a metric comparison to a weighted score."""
    field: str              # canonical metric name (must resolve via metric_schema)
    operator: str           # ">", "<", ">=", "<=", "==", "between"
    value: Union[float, list]  # threshold value, or [low, high] for "between"
    weight: float           # importance weight (0.5 - 5.0)
    required: bool          # if True, stock gets score=0 when rule fails
    label: str = ""         # human-readable label for display


@dataclass
class ScoringIntent:
    """Complete scoring intent -- a list of rules plus combination logic."""
    rules: List[ScoringRule]
    logic: str = "all"                  # "all" or "any" -- how rules combine
    sort_by: Optional[dict] = None      # {"field": "roic", "direction": "desc"}
    version: str = "1.0"


# ---------------------------------------------------------------------------
# JSON Schema for LLM structured output
# ---------------------------------------------------------------------------
# This schema is passed to the LLM (e.g. OpenAI structured output mode) so it
# produces valid Intent JSON on the first try.

INTENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "rules": {
            "type": "array",
            "description": "List of scoring rules. Each rule compares a financial metric against a threshold and assigns a weighted score.",
            "items": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "Metric name (canonical or alias). Examples: 'roic', 'gross_margin', 'pe', 'fcf_yield', 'debt_equity'. Use snake_case canonical names when possible."
                    },
                    "operator": {
                        "type": "string",
                        "enum": [">", "<", ">=", "<=", "==", "between"],
                        "description": "Comparison operator. Use 'between' for range checks (value must be [low, high] array)."
                    },
                    "value": {
                        "description": "Threshold value. A single number for >, <, >=, <=, ==. A two-element array [low, high] for 'between'.",
                        "anyOf": [
                            {"type": "number"},
                            {
                                "type": "array",
                                "items": {"type": "number"},
                                "minItems": 2,
                                "maxItems": 2
                            }
                        ]
                    },
                    "weight": {
                        "type": "number",
                        "description": "Importance weight for this rule. Higher = more impact on final score. Range: 0.5 to 5.0."
                    },
                    "required": {
                        "type": "boolean",
                        "description": "If true, stocks failing this rule get score=0 (hard filter). If false, it contributes proportionally to the score."
                    },
                    "label": {
                        "type": "string",
                        "description": "Human-readable label for display. E.g. 'High ROIC', 'Low Debt'."
                    }
                },
                "required": ["field", "operator", "value", "weight", "required", "label"],
                "additionalProperties": False
            },
            "minItems": 1
        },
        "logic": {
            "type": "string",
            "enum": ["all", "any"],
            "description": "'all' = every rule contributes to score (weighted sum). 'any' = score is max of individual rule scores."
        },
        "sort_by": {
            "type": "object",
            "description": "Which metric to sort final results by.",
            "properties": {
                "field": {
                    "type": "string",
                    "description": "Metric name to sort by."
                },
                "direction": {
                    "type": "string",
                    "enum": ["asc", "desc"],
                    "description": "Sort direction."
                }
            },
            "required": ["field", "direction"],
            "additionalProperties": False
        },
        "version": {
            "type": "string",
            "description": "Schema version. Currently '1.0'."
        }
    },
    "required": ["rules", "logic", "sort_by", "version"],
    "additionalProperties": False
}


# Pre-built response_format for use with LLMClient.generate(response_format=...)
INTENT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "scoring_intent",
    "schema": INTENT_JSON_SCHEMA,
    "strict": True,
}
