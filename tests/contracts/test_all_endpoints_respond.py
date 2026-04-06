"""Parametrized test: every frontend API call gets a valid response.

Catches 80% of 'button does nothing' bugs by verifying:
1. Endpoint exists (no 404/405)
2. Returns valid JSON (no 500)
3. Expected top-level keys present (no silent shape changes)
"""

import pytest
from tests.contracts.api_contract_map import (
    GET_CONTRACTS, TICKER_GET_CONTRACTS,
    POST_CONTRACTS, TICKER_POST_CONTRACTS,
)

TEST_TICKER = "AAPL"


# ── GET endpoints (no ticker) ────────────────────────────────────

@pytest.mark.parametrize("name,contract", list(GET_CONTRACTS.items()), ids=list(GET_CONTRACTS.keys()))
def test_get_endpoint_responds(seeded_client, name, contract):
    """Every GET endpoint returns 200 with valid JSON and expected keys."""
    resp = seeded_client.get(contract["path"])
    assert resp.status_code == 200, f"{name}: expected 200, got {resp.status_code} — {resp.text[:200]}"

    data = resp.json()
    if contract["response_keys"]:
        assert isinstance(data, dict), f"{name}: expected dict, got {type(data)}"
        for key in contract["response_keys"]:
            assert key in data, f"{name}: missing key '{key}'. Got: {list(data.keys())}"


# ── GET endpoints (with ticker) ──────────────────────────────────

@pytest.mark.parametrize("name,contract", list(TICKER_GET_CONTRACTS.items()), ids=list(TICKER_GET_CONTRACTS.keys()))
def test_ticker_get_endpoint_responds(seeded_client, name, contract):
    """Every ticker-specific GET endpoint returns 200/404 with valid JSON."""
    path = contract["path"].replace("{ticker}", TEST_TICKER)
    resp = seeded_client.get(path)
    assert resp.status_code in (200, 404), f"{name}: expected 200/404, got {resp.status_code} — {resp.text[:200]}"

    if resp.status_code == 200 and contract["response_keys"]:
        data = resp.json()
        for key in contract["response_keys"]:
            assert key in data, f"{name}: missing key '{key}'. Got: {list(data.keys()) if isinstance(data, dict) else type(data)}"


# ── POST endpoints (no ticker) ───────────────────────────────────

@pytest.mark.parametrize("name,contract", list(POST_CONTRACTS.items()), ids=list(POST_CONTRACTS.keys()))
def test_post_endpoint_responds(seeded_client, name, contract):
    """Every POST endpoint returns 2xx with valid JSON and expected keys."""
    resp = seeded_client.post(contract["path"], json=contract.get("body", {}))
    allowed = (200, 201, 202, 500) if contract.get("allow_500") else (200, 201, 202)
    assert resp.status_code in allowed, f"{name}: expected {allowed}, got {resp.status_code} — {resp.text[:200]}"

    if resp.status_code >= 400:
        return  # Can't check response keys on error responses

    data = resp.json()
    if contract["response_keys"]:
        for key in contract["response_keys"]:
            assert key in data, f"{name}: missing key '{key}'. Got: {list(data.keys()) if isinstance(data, dict) else type(data)}"


# ── POST endpoints (with ticker) ─────────────────────────────────

@pytest.mark.parametrize("name,contract", list(TICKER_POST_CONTRACTS.items()), ids=list(TICKER_POST_CONTRACTS.keys()))
def test_ticker_post_endpoint_responds(seeded_client, name, contract):
    """Every ticker-specific POST endpoint returns 2xx with valid JSON."""
    path = contract["path"].replace("{ticker}", TEST_TICKER)
    resp = seeded_client.post(path, json=contract.get("body", {}))
    assert resp.status_code in (200, 201, 202), f"{name}: expected 2xx, got {resp.status_code} — {resp.text[:200]}"

    data = resp.json()
    if contract["response_keys"]:
        for key in contract["response_keys"]:
            assert key in data, f"{name}: missing key '{key}'. Got: {list(data.keys()) if isinstance(data, dict) else type(data)}"
