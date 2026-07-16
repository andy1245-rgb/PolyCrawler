"""Smoke tests for FastAPI app and fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from poly_crawler.main import app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_labeled_wallets_fixture() -> None:
    data = json.loads((FIXTURES / "labeled_wallets.json").read_text())
    assert "parent" in data
    assert len(data["siblings"]) == 3
    assert data["score_variant"] == "sqrt"


def test_sample_events_fixture() -> None:
    events = json.loads((FIXTURES / "sample_events.json").read_text())
    assert len(events) == 3
    assert {e["event_type"] for e in events} == {"fund", "birth", "trade"}


def test_sample_orderbook_fixture() -> None:
    book = json.loads((FIXTURES / "sample_orderbook.json").read_text())
    assert "yes" in book or "bids" in book or "asks" in book or "market_id" in book
