"""Tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app

app = create_app()
client = TestClient(app)


def test_dashboard():
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200


def test_config():
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    # API keys should be sanitized
    connectors = data.get("connectors", {})
    for key in connectors:
        if isinstance(connectors[key], dict) and "api_key" in connectors[key]:
            val = connectors[key]["api_key"]
            assert not val or val.startswith("****") or val == ""


def test_config_presets():
    resp = client.get("/api/config/presets")
    assert resp.status_code == 200
    assert "presets" in resp.json()


def test_screener_results_empty():
    resp = client.get("/api/screener/results")
    assert resp.status_code == 200


def test_thesis_not_found():
    resp = client.get("/api/thesis/FAKE")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("thesis") is None or data.get("message")


def test_portfolio_empty():
    resp = client.get("/api/portfolio")
    assert resp.status_code == 200


def test_portfolio_status():
    resp = client.get("/api/portfolio/status")
    assert resp.status_code == 200


def test_jobs_list():
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert "jobs" in resp.json()


def test_job_not_found():
    resp = client.get("/api/jobs/nonexistent-job-id")
    assert resp.status_code == 404


def test_pipeline_status():
    resp = client.get("/api/pipeline/status")
    assert resp.status_code == 200


def test_library_memos():
    resp = client.get("/api/library/memos")
    assert resp.status_code == 200


def test_allocator_recommendations():
    resp = client.get("/api/allocator/recommendations")
    assert resp.status_code == 200
