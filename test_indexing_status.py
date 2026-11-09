import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from qdrant_client import QdrantClient

from backend.app.services.vector_store import CodeVectorStore
from backend.app.services.graph_store import Neo4jGraphStore
from backend.app.services.repo_ingestor import RepositoryIngestor
from backend.app.models.workspace import Workspace
from backend.app.models.user import User
from backend.app.api.workspace import _finish_ingestion
from backend.app.database import SessionLocal, init_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == "test_user").first()
        if not user:
            user = User(id="test_user", email="test_user@example.com", password_hash="dummy")
            db.add(user)
            db.commit()


def test_embedding_failure_does_not_store_zero_vectors():
    """When the embedding model fails to load, zero vectors must NOT be stored in Qdrant."""
    # Create an in-memory vector store with a mocked failing embedder model
    vs = CodeVectorStore(collection_name="test_zero_vec_guard", qdrant_path=":memory:")
    # Force embedder to None (simulating load failure)
    vs._model = None
    with patch.object(CodeVectorStore, "model", new=None):
        # 1. generate_embedding returns empty list, NOT [0.0]*384
        single_vec = vs.generate_embedding("def sample_function(): pass")
        assert single_vec == [], f"Expected empty list, got {len(single_vec)} items"

        # 2. generate_embeddings_batch returns empty list, NOT [[0.0]*384]
        batch_vecs = vs.generate_embeddings_batch(["def fn1(): pass", "def fn2(): pass"])
        assert batch_vecs == [], f"Expected empty list, got {len(batch_vecs)} items"

        # 3. upsert_code_snippet must return False
        success = vs.upsert_code_snippet(1, "def sample(): pass", {"file": "test.py"})
        assert success is False

        # 4. upsert_code_batch must return 0
        items = [
            {"doc_id": "doc1", "code_snippet": "def foo(): pass", "metadata": {}},
            {"doc_id": "doc2", "code_snippet": "class Bar: pass", "metadata": {}},
        ]
        upserted_count = vs.upsert_code_batch(items)
        assert upserted_count == 0

        # Verify Qdrant points count is 0 (nothing stored)
        client = vs.qdrant
        count_res = client.count(collection_name=vs.collection_name)
        assert count_res.count == 0, f"Expected 0 points in Qdrant, found {count_res.count}"


def test_neo4j_down_reports_zero_nodes_and_edges(tmp_path):
    """When Neo4j is down (driver is None or errors), graph_nodes and graph_edges must be 0, not parser stats."""
    code_file = tmp_path / "service.py"
    code_file.write_text(
        """class LoanService:
    def borrow_book(self, user, book):
        return True

    def return_book(self, user, book):
        return False
""",
        encoding="utf-8",
    )

    # GraphStore with driver=None (simulating Neo4j down)
    mock_gs = MagicMock(spec=Neo4jGraphStore)
    mock_gs.driver = None
    mock_gs.ingest_ast.return_value = False

    # Mock VectorStore that succeeds
    mock_vs = MagicMock(spec=CodeVectorStore)
    mock_vs.upsert_code_batch.return_value = 2
    mock_vs.embedding_ok = True

    ingestor = RepositoryIngestor(vector_store=mock_vs, graph_store=mock_gs)
    result = ingestor.ingest_local_directory(str(tmp_path), workspace_id="ws-test-neo4j-down")

    # Nodes and edges must be 0 because write to Neo4j did not succeed
    assert result["graph_nodes"] == 0, f"Expected 0 graph_nodes when Neo4j is down, got {result['graph_nodes']}"
    assert result["graph_edges"] == 0, f"Expected 0 graph_edges when Neo4j is down, got {result['graph_edges']}"
    assert result["graph_ok"] is False, "Expected graph_ok to be False"
    assert result["vector_ok"] is True, "Expected vector_ok to be True"
    assert result["vector_chunks"] == 2


def test_finish_ingestion_neo4j_down_sets_partial():
    """If Neo4j is down but vectors succeed, status must be PARTIAL (not READY) with 0 graph nodes."""
    ws_id = "ws-test-partial-status"
    with SessionLocal() as db:
        ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
        if not ws:
            ws = Workspace(
                id=ws_id,
                user_id="test_user",
                name="Test Partial",
                repo_url="https://github.com/test/repo",
                status="INDEXING",
            )
            db.add(ws)
            db.commit()

    res = {
        "status": "success",
        "total_files": 5,
        "branch": "main",
        "indexing_summary": {
            "graph_ok": False,
            "vector_ok": True,
            "graph_nodes": 0,
            "graph_edges": 0,
            "vector_chunks": 10,
            "languages": ["Python"],
        },
    }

    _finish_ingestion(ws_id, res)

    with SessionLocal() as db:
        ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
        assert ws.status == "PARTIAL", f"Expected status PARTIAL, got {ws.status}"
        assert ws.nodes_count == 0, f"Expected 0 nodes, got {ws.nodes_count}"
        assert ws.edges_count == 0, f"Expected 0 edges, got {ws.edges_count}"
        assert ws.error_message is not None
        assert "Neo4j" in ws.error_message or "graph" in ws.error_message.lower()


def test_finish_ingestion_both_down_sets_failed():
    """If both Neo4j and vector store fail, workspace must be marked FAILED, not READY."""
    ws_id = "ws-test-both-down"
    with SessionLocal() as db:
        ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
        if not ws:
            ws = Workspace(
                id=ws_id,
                user_id="test_user",
                name="Test Both Down",
                repo_url="https://github.com/test/repo",
                status="INDEXING",
            )
            db.add(ws)
            db.commit()

    res = {
        "status": "success",
        "total_files": 3,
        "branch": "main",
        "indexing_summary": {
            "graph_ok": False,
            "vector_ok": False,
            "graph_nodes": 0,
            "graph_edges": 0,
            "vector_chunks": 0,
            "languages": ["Python"],
        },
    }

    _finish_ingestion(ws_id, res)

    with SessionLocal() as db:
        ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
        assert ws.status == "FAILED", f"Expected status FAILED, got {ws.status}"
        assert ws.nodes_count == 0
        assert ws.edges_count == 0
        assert ws.error_message is not None


def test_finish_ingestion_both_succeed_sets_ready():
    """When both Neo4j and Qdrant succeed, status is READY with confirmed write counts."""
    ws_id = "ws-test-both-success"
    with SessionLocal() as db:
        ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
        if not ws:
            ws = Workspace(
                id=ws_id,
                user_id="test_user",
                name="Test Both Success",
                repo_url="https://github.com/test/repo",
                status="INDEXING",
            )
            db.add(ws)
            db.commit()

    res = {
        "status": "success",
        "total_files": 4,
        "branch": "main",
        "indexing_summary": {
            "graph_ok": True,
            "vector_ok": True,
            "graph_nodes": 12,
            "graph_edges": 8,
            "vector_chunks": 16,
            "languages": ["Python"],
        },
    }

    _finish_ingestion(ws_id, res)

    with SessionLocal() as db:
        ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
        assert ws.status == "READY", f"Expected status READY, got {ws.status}"
        assert ws.nodes_count == 12
        assert ws.edges_count == 8
        assert ws.error_message is None
