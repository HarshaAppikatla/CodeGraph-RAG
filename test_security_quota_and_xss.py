import os
import json
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import settings
from backend.app.api.rag import rag_rate_limiter, _resolve_key
from backend.app.database import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_keys_status_does_not_expose_server_gemini_key_to_guests():
    """Server's GEMINI_API_KEY must not be reported as 'configured' or masked in /keys/status for guests."""
    with patch.object(settings, "GEMINI_API_KEY", "AIzaSyServerSecretKey1234567890"):
        res = client.get("/api/keys/status")
        assert res.status_code == 200
        data = res.json()

        # Guest must NOT see the server's private key as configured!
        assert data["status"]["gemini"] is False, "Server Gemini key was falsely shown as configured for guest"
        assert data["gemini"] is False
        assert data["masked_keys"].get("gemini") is None, "Masked server key was exposed to guest"


def test_resolve_key_does_not_hand_server_gemini_key_to_guests():
    """_resolve_key must return empty string for unauthenticated callers without their own key."""
    with patch.object(settings, "GEMINI_API_KEY", "AIzaSyServerSecretKey1234567890"):
        resolved = _resolve_key(provider="gemini", req_key=None, current_user=None)
        assert resolved == "", f"Server key was resolved for guest: {resolved}"


def test_top_k_enforces_strict_cap():
    """top_k must be capped (max 25, min 1) to prevent memory and token exhaustion attacks."""
    # Test top_k > 25 is rejected with 422
    res_large = client.post(
        "/api/rag/query",
        json={"workspace_id": "ws-study-sync", "query": "hello", "top_k": 100000}
    )
    assert res_large.status_code == 422, f"Expected 422 for huge top_k, got {res_large.status_code}"

    # Test top_k < 1 is rejected with 422
    res_zero = client.post(
        "/api/rag/query",
        json={"workspace_id": "ws-study-sync", "query": "hello", "top_k": 0}
    )
    assert res_zero.status_code == 422, f"Expected 422 for zero top_k, got {res_zero.status_code}"


def test_rag_rate_limiting():
    """Requests exceeding 45/minute to /rag/query must receive HTTP 429 Too Many Requests."""
    # Reset limiter for test IP
    test_key = "ip:testclient"
    rag_rate_limiter.records[test_key] = []

    # Send 45 requests (should succeed)
    for _ in range(45):
        assert rag_rate_limiter.check(test_key) is True

    # 46th request must be rejected by the limiter
    assert rag_rate_limiter.check(test_key) is False

    # Calling the endpoint when rate limited must return 429
    with patch.object(rag_rate_limiter, "check", return_value=False):
        res = client.post(
            "/api/rag/query",
            json={"workspace_id": "ws-study-sync", "query": "test rate limit"}
        )
        assert res.status_code == 429, f"Expected 429 Too Many Requests, got {res.status_code}"
        assert "Rate limit exceeded" in res.json()["detail"]


def test_mermaid_viewer_security_configuration():
    """Frontend MermaidViewer must use strict securityLevel and DOMPurify sanitization."""
    viewer_file = Path("frontend/src/components/MermaidViewer.jsx")
    content = viewer_file.read_text(encoding="utf-8")

    assert "securityLevel: 'strict'" in content, "MermaidViewer must have securityLevel: 'strict'"
    assert "securityLevel: 'loose'" not in content, "MermaidViewer still has securityLevel: 'loose'!"
    assert "DOMPurify.sanitize" in content, "MermaidViewer must sanitize SVG with DOMPurify"
