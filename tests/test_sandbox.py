"""Tests for the scoring sandbox: AST validation, compilation, and execution."""

import pytest
from backend.scoring.sandbox import (
    validate_ast, compile_scoring_function, execute_scoring, ScoringCodeError,
)


# --- AST Validation ---

def test_valid_scoring_function():
    code = """
def score(stock):
    return {'score': 5.0, 'reason': 'test'}
"""
    errors = validate_ast(code)
    assert errors == []


def test_rejects_import():
    code = """
import os
def score(stock):
    return {'score': 5.0}
"""
    errors = validate_ast(code)
    assert any("Import" in e for e in errors)


def test_rejects_from_import():
    code = """
from pathlib import Path
def score(stock):
    return {'score': 5.0}
"""
    errors = validate_ast(code)
    assert any("Import" in e for e in errors)


def test_rejects_dunder_access():
    code = """
def score(stock):
    x = stock.__class__.__bases__
    return {'score': 5.0}
"""
    errors = validate_ast(code)
    assert len(errors) > 0


def test_rejects_exec_call():
    code = """
def score(stock):
    exec("print('hacked')")
    return {'score': 5.0}
"""
    errors = validate_ast(code)
    assert any("exec" in e for e in errors)


def test_rejects_open_call():
    code = """
def score(stock):
    open('/etc/passwd')
    return {'score': 5.0}
"""
    errors = validate_ast(code)
    assert any("open" in e for e in errors)


def test_syntax_error():
    code = "def score(stock:\n  return {'score': 5.0}"
    errors = validate_ast(code)
    assert any("Syntax" in e for e in errors)


# --- Compilation ---

def test_compile_valid():
    code = """
def score(stock):
    val = safe_get(stock, 'price', 0)
    return {'score': clamp(val / 100, 0, 10), 'reason': 'test'}
"""
    fn = compile_scoring_function(code)
    assert callable(fn)
    result = fn({"price": 500})
    assert result["score"] == 5.0


def test_compile_no_score_function():
    code = "x = 5"
    with pytest.raises(ScoringCodeError, match="must define"):
        compile_scoring_function(code)


def test_compile_rejects_dangerous_code():
    code = """
import os
def score(stock):
    return {'score': 5.0}
"""
    with pytest.raises(ScoringCodeError, match="validation failed"):
        compile_scoring_function(code)


# --- Execution ---

def test_execute_scoring_happy_path():
    code = """
def score(stock):
    price = safe_get(stock, 'price', 0)
    return {'score': normalize(price, 50, 500), 'reason': 'test'}
"""
    fn = compile_scoring_function(code)
    stocks = [
        {"symbol": "AAPL", "price": 200},
        {"symbol": "MSFT", "price": 400},
        {"symbol": "GOOG", "price": 100},
    ]
    result = execute_scoring(fn, stocks)
    assert result["status"] == "complete"
    assert result["scored_count"] == 3
    assert result["failed_count"] == 0
    # Results should be sorted by score descending
    assert result["results"][0]["score"] >= result["results"][1]["score"]


def test_execute_scoring_handles_key_error():
    code = """
def score(stock):
    val = stock['nonexistent_key']
    return {'score': val}
"""
    fn = compile_scoring_function(code)
    stocks = [{"symbol": "AAPL", "price": 200}]
    result = execute_scoring(fn, stocks)
    assert result["failed_count"] == 1
    assert "nonexistent_key" in result["failed"][0]["error"]


def test_execute_scoring_validates_return():
    code = """
def score(stock):
    return {'no_score_key': 5.0}
"""
    fn = compile_scoring_function(code)
    stocks = [{"symbol": "AAPL"}]
    result = execute_scoring(fn, stocks)
    assert result["failed_count"] == 1


def test_execute_scoring_error_threshold():
    code = """
def score(stock):
    # Fails for all stocks missing 'required' key
    val = stock['required']
    return {'score': val}
"""
    fn = compile_scoring_function(code)
    stocks = [{"symbol": f"T{i}"} for i in range(10)]
    result = execute_scoring(fn, stocks)
    assert result["status"] == "error"  # >50% failed


def test_execute_scoring_partial():
    code = """
def score(stock):
    if stock.get('symbol') == 'BAD':
        raise ValueError("bad stock")
    return {'score': 5.0, 'reason': 'ok'}
"""
    fn = compile_scoring_function(code)
    stocks = [
        {"symbol": "GOOD"},
        {"symbol": "BAD"},
        {"symbol": "ALSO_GOOD"},
    ]
    result = execute_scoring(fn, stocks)
    assert result["status"] == "partial"
    assert result["scored_count"] == 2
    assert result["failed_count"] == 1


def test_execute_scoring_division_by_zero():
    code = """
def score(stock):
    val = safe_get(stock, 'price', 0) / safe_get(stock, 'eps', 0)
    return {'score': 5.0, 'reason': 'test'}
"""
    fn = compile_scoring_function(code)
    stocks = [{"symbol": "AAPL", "price": 200, "eps": 0}]
    result = execute_scoring(fn, stocks)
    assert result["failed_count"] == 1


def test_helpers_available():
    """Test that safe_get, clamp, normalize, math, statistics are available."""
    code = """
def score(stock):
    a = safe_get(stock, 'x', 5.0)
    b = clamp(a, 0, 10)
    c = normalize(a, 0, 20)
    d = math.sqrt(4)
    return {'score': b, 'sqrt': d, 'norm': c, 'reason': 'helpers work'}
"""
    fn = compile_scoring_function(code)
    result = fn({"x": 15})
    assert result["score"] == 10.0  # clamped
    assert result["sqrt"] == 2.0
    assert result["norm"] == 7.5  # 15/20 * 10
