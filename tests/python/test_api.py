from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from valuescope.api import app


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generate_report_endpoint_returns_snapshot() -> None:
    client = TestClient(app)
    snapshot = {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-05T00:00:00Z",
        "source": {"name": "test"},
        "company": {"ticker": "000858", "name": "五粮液", "market": "CN-A"},
        "coverage": {"period_type": "annual", "years": ["2024"]},
        "metric_definitions": {},
        "sections": [],
        "warnings": [],
        "snapshot_path": "data/report_snapshots/company_report_snapshot.json",
    }

    with patch("valuescope.api.generate_report_snapshot", return_value=snapshot):
        response = client.post("/api/generate-report", json={"ticker": "000858", "years": 4})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["snapshot"]["company"]["ticker"] == "000858"

