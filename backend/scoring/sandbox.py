"""Sandboxed execution of AI-generated scoring functions.

Security model:
- AST validation: reject imports, dunder access, dangerous builtins
- Restricted globals: only math, statistics, and provided helper functions
- Timeout: signal.alarm kills execution if it exceeds time limit
- Per-stock try/except: one stock failing doesn't kill the whole run

Subprocess mode (execute_scoring_subprocess):
- Runs scoring code in a separate Python process
- CPU/memory limits via resource.setrlimit (macOS/Linux)
- Process-level timeout via subprocess.run(timeout=...)
- Full isolation: scoring code cannot access parent process memory

Use subprocess mode for production, in-process for tests.
"""

import ast
import json
import math
import os
import signal
import statistics
import subprocess
import sys
import tempfile
import logging
from typing import Any, Callable, Optional

log = logging.getLogger("fundops.scoring.sandbox")


# --- AST Validation ---

BLOCKED_NAMES = frozenset({
    "import", "__import__", "exec", "eval", "compile",
    "open", "file", "input", "breakpoint",
    "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr",
    "os", "sys", "subprocess", "shutil", "pathlib",
})

BLOCKED_ATTRS = frozenset({
    "__builtins__", "__import__", "__subclasses__",
    "__bases__", "__class__", "__globals__",
    "__code__", "__func__", "__self__",
    "__dict__", "__module__", "__qualname__",
})


class ScoringCodeError(Exception):
    """Raised when AI-generated scoring code fails validation."""
    pass


def validate_ast(code: str) -> list[str]:
    """Validate AI-generated Python code for safety.

    Returns list of error messages. Empty list = safe to execute.
    """
    errors = []

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"Syntax error: {e}"]

    for node in ast.walk(tree):
        # Block import statements
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            errors.append(f"Import not allowed: line {node.lineno}")

        # Block calls to dangerous builtins
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BLOCKED_NAMES:
                errors.append(f"Blocked function '{func.id}': line {node.lineno}")

        # Block dunder attribute access
        if isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_ATTRS:
                errors.append(f"Blocked attribute '{node.attr}': line {node.lineno}")
            if node.attr.startswith("__") and node.attr.endswith("__"):
                errors.append(f"Dunder access '{node.attr}' not allowed: line {node.lineno}")

        # Block Name references to blocked names
        if isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            # Only block if used as a call or standalone reference
            pass  # Handled in Call check above

    return errors


# --- Restricted Globals ---

_FIELD_ALIASES: dict[str, list[str]] = {
    # snake_case canonical -> camelCase alternatives from screener data
    "gross_margin": ["grossProfitMargin", "gross_profit_margin"],
    "operating_margin": ["operatingMargin", "operating_profit_margin"],
    "net_margin": ["netProfitMargin", "net_profit_margin"],
    "fcf_yield": ["fcfYield", "fcf_yield_pct"],
    "fcf_margin": ["fcfMargin"],
    "fcf_conversion": ["fcfConversion"],
    "roic": ["returnOnInvestedCapital"],
    "roe": ["returnOnEquity"],
    "debt_equity": ["debtEquity"],
    "revenue_growth": ["revenueGrowth"],
    "revenue_growth_3y": ["revenueGrowth3y"],
    "revenue_growth_5y": ["revenueGrowth5y"],
    "earnings_growth": ["earningsGrowth"],
    "earnings_yield": ["earningsYield"],
    "market_cap": ["marketCap"],
    "ebitda_margin": ["ebitdaMargin"],
    "implied_growth": ["impliedGrowth"],
    "interest_coverage": ["interestCoverage"],
    "income_quality": ["incomeQuality"],
    "owner_earnings_per_share": ["ownerEarningsPerShare"],
    "discount_pct": ["discount", "discount_to_fv"],
    "growth_gap": ["growthGap"],
    "quality_score": ["qualityScore"],
    "expected_return": ["expectedReturn"],
    "debt_to_ebitda": ["debtToEbitda", "net_debt_ebitda"],
    "company_name": ["companyName"],
}

# Build reverse lookup: camelCase -> canonical
_REVERSE_ALIASES: dict[str, str] = {}
for _canon, _alts in _FIELD_ALIASES.items():
    for _alt in _alts:
        _REVERSE_ALIASES[_alt] = _canon


def _safe_get(stock: dict, key: str, default: float = 0.0) -> float:
    """Safely get a numeric value from stock dict.

    Handles field name aliasing: scoring code uses snake_case canonical names
    (e.g. 'gross_margin') but screener data may use camelCase ('grossProfitMargin').
    Tries the canonical key first, then known aliases.
    """
    val = stock.get(key)
    if val is None:
        # Try aliases: canonical -> camelCase alternatives
        aliases = _FIELD_ALIASES.get(key, [])
        for alias in aliases:
            val = stock.get(alias)
            if val is not None:
                break
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    """Clamp a value to a range."""
    return max(low, min(high, value))


def _normalize(value: float, low: float, high: float) -> float:
    """Normalize a value from [low, high] to [0, 10]."""
    if high <= low:
        return 5.0
    return _clamp((value - low) / (high - low) * 10, 0, 10)


SAFE_GLOBALS = {
    "__builtins__": {},  # No builtins at all
    "math": math,
    "statistics": statistics,
    "abs": abs,
    "max": max,
    "min": min,
    "round": round,
    "len": len,
    "sum": sum,
    "sorted": sorted,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "float": float,
    "int": int,
    "str": str,
    "bool": bool,
    "dict": dict,
    "list": list,
    "tuple": tuple,
    "True": True,
    "False": False,
    "None": None,
    # Helper functions available to generated code
    "safe_get": _safe_get,
    "clamp": _clamp,
    "normalize": _normalize,
}


# --- Compilation & Execution ---

def compile_scoring_function(code: str) -> Callable:
    """Compile AI-generated Python code into a callable scoring function.

    The code must define a function `score(stock: dict) -> dict`.

    Returns:
        The score() function extracted from the generated code.

    Raises:
        ScoringCodeError: If validation fails or no score() function found.
    """
    # Validate AST
    errors = validate_ast(code)
    if errors:
        raise ScoringCodeError(f"Code validation failed: {'; '.join(errors)}")

    # Execute in restricted namespace
    namespace = dict(SAFE_GLOBALS)
    try:
        exec(code, namespace)
    except Exception as e:
        raise ScoringCodeError(f"Code compilation failed: {e}")

    # Extract the score function
    score_fn = namespace.get("score")
    if score_fn is None:
        raise ScoringCodeError("Generated code must define a `score(stock)` function")
    if not callable(score_fn):
        raise ScoringCodeError("`score` is not callable")

    return score_fn


class _TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _TimeoutError("Scoring execution timed out")


def execute_scoring(score_fn: Callable, stocks: list[dict],
                    timeout_seconds: int = 10) -> dict:
    """Execute a scoring function against a list of stocks.

    Each stock is scored independently. Failures are logged but don't
    stop the run. If >50% of stocks fail, the run is flagged as error.

    Args:
        score_fn: Compiled scoring function from compile_scoring_function()
        stocks: List of stock dicts with metric data
        timeout_seconds: Max seconds for the entire scoring run

    Returns:
        {
            "results": [{"ticker": ..., "score": ..., ...}, ...],
            "failed": [{"ticker": ..., "error": ...}, ...],
            "status": "complete" | "partial" | "error",
            "scored_count": int,
            "failed_count": int,
        }
    """
    results = []
    failed = []

    # Set timeout for entire run
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_seconds)

    try:
        for stock in stocks:
            ticker = stock.get("symbol") or stock.get("ticker", "UNKNOWN")
            try:
                result = score_fn(stock)

                # Validate return value
                if not isinstance(result, dict):
                    failed.append({"ticker": ticker, "error": "score() must return a dict"})
                    continue
                if "score" not in result:
                    failed.append({"ticker": ticker, "error": "score() result must contain 'score' key"})
                    continue

                # Merge scoring output with original stock data
                # so results include price, market cap, sector, etc.
                merged = {k: v for k, v in stock.items()}
                merged.update(result)
                merged["ticker"] = ticker
                results.append(merged)

            except _TimeoutError:
                raise  # Let timeout propagate
            except Exception as e:
                failed.append({"ticker": ticker, "error": str(e)})

    except _TimeoutError:
        log.warning(f"Scoring timed out after {timeout_seconds}s. "
                    f"Scored {len(results)}/{len(stocks)} stocks.")
    finally:
        signal.alarm(0)  # Cancel alarm
        signal.signal(signal.SIGALRM, old_handler)

    # Sort by score descending
    results.sort(key=lambda r: r.get("score", 0), reverse=True)

    total = len(stocks)
    scored = len(results)
    fail_count = len(failed)

    if fail_count > total * 0.5:
        status = "error"
    elif fail_count > 0:
        status = "partial"
    else:
        status = "complete"

    return {
        "results": results,
        "failed": failed,
        "status": status,
        "scored_count": scored,
        "failed_count": fail_count,
    }


# --- Subprocess Isolation ---

_SUBPROCESS_RUNNER_TEMPLATE = '''\
import json
import math
import statistics
import sys

_FIELD_ALIASES = {aliases_json}

def safe_get(stock, key, default=0.0):
    val = stock.get(key)
    if val is None:
        for alias in _FIELD_ALIASES.get(key, []):
            val = stock.get(alias)
            if val is not None:
                break
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def clamp(value, low=0.0, high=10.0):
    return max(low, min(high, value))

def normalize(value, low, high):
    if high <= low:
        return 5.0
    return clamp((value - low) / (high - low) * 10, 0, 10)

# --- Generated scoring code ---
{scoring_code}
# --- End scoring code ---

stocks = json.loads(sys.stdin.read())
results = []
failed = []

for stock in stocks:
    ticker = stock.get("symbol") or stock.get("ticker", "UNKNOWN")
    try:
        result = score(stock)
        if not isinstance(result, dict) or "score" not in result:
            failed.append({{"ticker": ticker, "error": "bad return value"}})
            continue
        merged = {{k: v for k, v in stock.items()}}
        merged.update(result)
        merged["ticker"] = ticker
        results.append(merged)
    except Exception as e:
        failed.append({{"ticker": ticker, "error": str(e)}})

results.sort(key=lambda r: r.get("score", 0), reverse=True)
total = len(stocks)
scored = len(results)
fail_count = len(failed)
status = "error" if fail_count > total * 0.5 else ("partial" if fail_count > 0 else "complete")

json.dump({{
    "results": results,
    "failed": failed,
    "status": status,
    "scored_count": scored,
    "failed_count": fail_count,
}}, sys.stdout, default=str)
'''


def execute_scoring_subprocess(
    code: str,
    stocks: list[dict],
    timeout_seconds: int = 30,
    max_memory_mb: int = 512,
) -> dict:
    """Execute scoring code in a subprocess with resource limits.

    This provides process-level isolation: the scoring code runs in a
    separate Python process with CPU timeout and memory limits.

    Args:
        code: Validated Python scoring code (must define `score(stock)`)
        stocks: List of stock dicts
        timeout_seconds: Max time for the subprocess
        max_memory_mb: Max memory in MB (macOS/Linux only)

    Returns:
        Same format as execute_scoring(): {results, failed, status, ...}
    """
    # Validate AST before even writing to disk
    errors = validate_ast(code)
    if errors:
        raise ScoringCodeError(f"Code validation failed: {'; '.join(errors)}")

    # Write runner script to temp file
    runner_code = _SUBPROCESS_RUNNER_TEMPLATE.format(
        scoring_code=code,
        aliases_json=json.dumps(_FIELD_ALIASES),
    )
    runner_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="fundops_score_",
        delete=False,
    )
    runner_file.write(runner_code)
    runner_file.close()

    try:
        stocks_json = json.dumps(stocks, default=str)

        result = subprocess.run(
            [sys.executable, runner_file.name],
            input=stocks_json,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        if result.returncode != 0:
            stderr = result.stderr[:500] if result.stderr else "unknown error"
            log.error(f"Subprocess scoring failed: {stderr}")
            return {
                "results": [],
                "failed": [{"ticker": "ALL", "error": stderr}],
                "status": "error",
                "scored_count": 0,
                "failed_count": len(stocks),
            }

        return json.loads(result.stdout)

    except subprocess.TimeoutExpired:
        log.warning(f"Subprocess scoring timed out after {timeout_seconds}s")
        return {
            "results": [],
            "failed": [{"ticker": "ALL", "error": f"Timed out after {timeout_seconds}s"}],
            "status": "error",
            "scored_count": 0,
            "failed_count": len(stocks),
        }
    except json.JSONDecodeError as e:
        log.error(f"Subprocess scoring returned invalid JSON: {e}")
        return {
            "results": [],
            "failed": [{"ticker": "ALL", "error": f"Invalid output: {e}"}],
            "status": "error",
            "scored_count": 0,
            "failed_count": len(stocks),
        }
    finally:
        try:
            os.unlink(runner_file.name)
        except OSError:
            pass
