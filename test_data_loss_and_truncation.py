import os
import tempfile
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from backend.app.services.vector_store import CodeVectorStore
from backend.app.services.graph_store import Neo4jGraphStore
from backend.app.services.repo_ingestor import RepositoryIngestor
from backend.app.api.rag import _retrieve
from backend.app.models.workspace import Workspace
from backend.app.models.user import User
from backend.app.api.workspace import _finish_ingestion, _reconcile_indexing_workspace
from backend.app.database import SessionLocal, init_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == "test_user_dl").first()
        if not user:
            user = User(id="test_user_dl", email="test_user_dl@example.com", password_hash="dummy")
            db.add(user)
            db.commit()


def test_retrieve_never_invents_fake_chunks_or_fake_scores():
    """When vector search returns nothing, _retrieve must return empty list, NOT fake 0.85/knowledge-graph chunks."""
    with patch("backend.app.api.rag.get_vector_store") as mock_get_vs, \
         patch("backend.app.api.rag.get_graph_store") as mock_get_gs:
        mock_vs = MagicMock()
        mock_vs.search.return_value = []
        mock_get_vs.return_value = mock_vs

        mock_gs = MagicMock()
        mock_gs.list_symbols.return_value = [{"file": "service.py", "name": "foo", "type": "Function"}]
        mock_get_gs.return_value = mock_gs

        chunks = _retrieve("ws-test-real", "some search query", top_k=5)

        # Retrieval must be completely empty: no fake 0.85 score, no invented "knowledge graph is ready"
        assert chunks == [], f"Expected empty list, got {chunks}"
        for c in chunks:
            assert c.get("score") != 0.85, "Fake 0.85 score chunk was returned!"
            assert "knowledge graph is ready" not in c.get("snippet", "").lower()


def test_workspace_data_loss_on_restart_downgrades_ready_status():
    """If vectors and graph nodes are gone on restart, a READY workspace in Postgres must be updated to FAILED."""
    ws_id = "ws-test-data-loss-restart"
    with SessionLocal() as db:
        ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
        if not ws:
            ws = Workspace(
                id=ws_id,
                user_id="test_user_dl",
                name="Test Data Loss",
                repo_url="https://github.com/test/repo",
                files_count=10,
                nodes_count=20,
                edges_count=15,
                status="READY",
            )
            db.add(ws)
            db.commit()

    with patch("backend.app.api.workspace.get_vector_store") as mock_get_vs, \
         patch("backend.app.api.workspace.get_graph_store") as mock_get_gs:
        # Vector store responds with 0 vectors (e.g. wiped ephemeral storage on restart)
        mock_vs = MagicMock()
        mock_vs.count_workspace_vectors.return_value = 0
        mock_get_vs.return_value = mock_vs

        # Graph store responds with 0 nodes
        mock_gs = MagicMock()
        mock_gs.count_workspace_nodes.return_value = 0
        mock_gs.driver = True
        mock_get_gs.return_value = mock_gs

        with SessionLocal() as db:
            ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
            reconciled = _reconcile_indexing_workspace(ws, db)
            assert reconciled.status == "FAILED", f"Expected FAILED status after data loss, got {reconciled.status}"
            assert "lost after server restart" in reconciled.error_message


def test_workspace_vector_loss_downgrades_to_partial():
    """If vectors were lost on restart but graph survived, workspace must downgrade to PARTIAL with warning."""
    ws_id = "ws-test-vector-loss-restart"
    with SessionLocal() as db:
        ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
        if not ws:
            ws = Workspace(
                id=ws_id,
                user_id="test_user_dl",
                name="Test Vector Loss",
                repo_url="https://github.com/test/repo",
                files_count=8,
                nodes_count=14,
                edges_count=10,
                status="READY",
            )
            db.add(ws)
            db.commit()

    with patch("backend.app.api.workspace.get_vector_store") as mock_get_vs, \
         patch("backend.app.api.workspace.get_graph_store") as mock_get_gs:
        # Vectors wiped on restart (0)
        mock_vs = MagicMock()
        mock_vs.count_workspace_vectors.return_value = 0
        mock_get_vs.return_value = mock_vs

        # Neo4j persistent data survived (14 nodes)
        mock_gs = MagicMock()
        mock_gs.count_workspace_nodes.return_value = 14
        mock_gs.driver = True
        mock_get_gs.return_value = mock_gs

        with SessionLocal() as db:
            ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
            reconciled = _reconcile_indexing_workspace(ws, db)
            assert reconciled.status == "PARTIAL", f"Expected PARTIAL status, got {reconciled.status}"
            assert "Vector embeddings were lost" in reconciled.error_message


def test_four_hundred_file_repo_is_not_truncated(tmp_path):
    """A 400-file repository must index all 400 files without hitting an artificial 300-file ceiling."""
    # Create 400 small python source files
    files = []
    for i in range(400):
        f = tmp_path / f"module_{i}.py"
        f.write_text(f"def func_{i}():\n    return {i}\n", encoding="utf-8")
        files.append(f)

    mock_vs = MagicMock()
    mock_vs.upsert_code_batch.return_value = 400
    mock_vs.embedding_ok = True

    mock_gs = MagicMock()
    mock_gs.ingest_ast.return_value = True

    ingestor = RepositoryIngestor(vector_store=mock_vs, graph_store=mock_gs)
    res = ingestor.ingest_local_directory(str(tmp_path), workspace_id="ws-test-400-files")

    assert res["total_files"] == 400, f"Expected 400 indexed files, got {res['total_files']}"
    assert res.get("total_files_found") == 400
    assert res.get("truncated") is False, "400-file repo was unexpectedly truncated"
    assert res.get("warning") is None


def test_truncation_warning_surfaces_when_cap_exceeded(tmp_path):
    """When a safety limit is exceeded, truncation is never silent: warning is produced and status is PARTIAL."""
    # Create 10 python files
    files = []
    for i in range(10):
        f = tmp_path / f"test_mod_{i}.py"
        f.write_text(f"def test_f_{i}(): pass\n", encoding="utf-8")
        files.append(f)

    mock_vs = MagicMock()
    mock_vs.upsert_code_batch.return_value = 4
    mock_vs.embedding_ok = True

    mock_gs = MagicMock()
    mock_gs.ingest_ast.return_value = True

    # Artificially set limit to 4 via environment variable
    with patch.dict(os.environ, {"MAX_INDEXABLE_FILES": "4"}):
        ingestor = RepositoryIngestor(vector_store=mock_vs, graph_store=mock_gs)
        res = ingestor.ingest_local_directory(str(tmp_path), workspace_id="ws-test-truncate-warn")

        assert res["total_files"] == 4
        assert res["total_files_found"] == 10
        assert res["truncated"] is True
        assert "Codebase truncated" in res["warning"]
        assert "6 files omitted" in res["warning"]

        # Verify _finish_ingestion sets status to PARTIAL with the warning
        ws_id = "ws-test-truncation-partial"
        with SessionLocal() as db:
            ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
            if not ws:
                ws = Workspace(
                    id=ws_id,
                    user_id="test_user_dl",
                    name="Test Truncation WS",
                    repo_url="https://github.com/test/repo",
                    status="INDEXING",
                )
                db.add(ws)
                db.commit()

        _finish_ingestion(ws_id, res)

        with SessionLocal() as db:
            ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
            assert ws.status == "PARTIAL", f"Expected PARTIAL due to truncation, got {ws.status}"
            assert ws.error_message is not None
            assert "Codebase truncated" in ws.error_message
            assert "6 files omitted" in ws.error_message

