import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api.rag import _verify_workspace_access, DEMO_WORKSPACE_IDS
from backend.app.services.vector_store import CodeVectorStore
from qdrant_client.http.models import Filter, FieldCondition, MatchValue


client = TestClient(app)


def test_verify_workspace_access_rejects_empty():
    mock_db = MagicMock()
    # Test None
    with pytest.raises(HTTPException) as exc_info:
        _verify_workspace_access(None, None, mock_db)
    assert exc_info.value.status_code == 400
    assert "Workspace ID is required" in exc_info.value.detail

    # Test empty string
    with pytest.raises(HTTPException) as exc_info:
        _verify_workspace_access("", None, mock_db)
    assert exc_info.value.status_code == 400
    assert "Workspace ID is required" in exc_info.value.detail

    # Test whitespace
    with pytest.raises(HTTPException) as exc_info:
        _verify_workspace_access("   ", None, mock_db)
    assert exc_info.value.status_code == 400


def test_verify_workspace_access_removes_ws_prefix_bypass():
    mock_db = MagicMock()
    # "ws-alice-private" starts with "ws-" but is not in DEMO_WORKSPACE_IDS
    # It must NOT bypass auth; an anonymous caller should get 401
    with pytest.raises(HTTPException) as exc_info:
        _verify_workspace_access("ws-alice-private", None, mock_db)
    assert exc_info.value.status_code == 401
    assert "Authentication required" in exc_info.value.detail


def test_verify_workspace_access_allows_demo_workspaces():
    mock_db = MagicMock()
    for demo_id in DEMO_WORKSPACE_IDS:
        # Demo workspaces are accessible anonymously without raising
        _verify_workspace_access(demo_id, None, mock_db)


def test_vector_store_always_applies_workspace_filter():
    vs = CodeVectorStore()
    vs.generate_embedding = MagicMock(return_value=[0.1] * 384)
    vs.qdrant = MagicMock()
    vs.qdrant.query_points.return_value = MagicMock(points=[])

    # 1. When workspace_id is empty or None, filter must NOT be dropped
    vs.search_similar_code("test query", limit=5, workspace_id=None)
    assert vs.qdrant.query_points.called
    _, kwargs = vs.qdrant.query_points.call_args
    assert kwargs.get("query_filter") is not None
    q_filter = kwargs["query_filter"]
    assert isinstance(q_filter, Filter)
    assert len(q_filter.must) == 1
    assert q_filter.must[0].key == "workspace_id"
    assert q_filter.must[0].match.value == ""

    # 2. When workspace_id is provided, filter is strictly that workspace
    vs.search_similar_code("test query", limit=5, workspace_id="ws-alice")
    _, kwargs = vs.qdrant.query_points.call_args
    assert kwargs.get("query_filter") is not None
    assert kwargs["query_filter"].must[0].match.value == "ws-alice"


def test_api_endpoints_reject_empty_workspace_id():
    # /api/rag/query
    res = client.post("/api/rag/query", json={"workspace_id": "", "query": "hello"})
    assert res.status_code == 400
    assert "Workspace ID is required" in res.json().get("detail", "")

    res = client.post("/api/rag/query", json={"workspace_id": None, "query": "hello"})
    assert res.status_code == 400

    # /api/rag/search
    res = client.post("/api/rag/search", json={"workspace_id": "", "query": "hello"})
    assert res.status_code == 400

    # /api/rag/impact
    res = client.post("/api/rag/impact", json={"workspace_id": "", "symbol": "myFunc"})
    assert res.status_code == 400

    # /api/rag/refactor
    res = client.post("/api/rag/refactor", json={"workspace_id": "", "prompt": "refactor this"})
    assert res.status_code == 400

    # /api/rag/architecture-graph
    res = client.post("/api/rag/architecture-graph", json={"workspace_id": ""})
    assert res.status_code == 400


def test_api_endpoints_reject_unauthorized_custom_ws_prefix():
    # An anonymous caller trying to access a custom workspace starting with "ws-"
    res = client.post("/api/rag/query", json={"workspace_id": "ws-alice-private", "query": "hello"})
    assert res.status_code == 401

    res = client.post("/api/rag/impact", json={"workspace_id": "ws-alice-private", "symbol": "myFunc"})
    assert res.status_code == 401

    res = client.post("/api/rag/refactor", json={"workspace_id": "ws-alice-private", "prompt": "refactor this"})
    assert res.status_code == 401

