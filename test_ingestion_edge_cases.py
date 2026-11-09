import os
import shutil
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.database import init_db, SessionLocal
from backend.app.models.workspace import Workspace
from backend.app.models.user import User
from backend.app.services.repo_ingestor import (
    RepositoryIngestor,
    cancel_job,
    is_job_cancelled,
    clear_job_cancellation,
    IngestionCancelledError,
)
from backend.app.api.workspace import (
    _reconcile_indexing_workspace,
    _finish_ingestion,
    _register_active_job,
    _unregister_active_job,
    _is_job_active,
    delete_workspace,
    ingest_workspace,
)


@pytest.fixture(autouse=True)
def setup_database():
    init_db()
    with SessionLocal() as db:
        db.query(Workspace).filter(Workspace.user_id.in_(["test-edge-user", "test-edge-user-2"])).delete()
        db.query(User).filter(User.id.in_(["test-edge-user", "test-edge-user-2"])).delete()
        user1 = User(id="test-edge-user", email="edge1@example.com", password_hash="hashedpassword123")
        user2 = User(id="test-edge-user-2", email="edge2@example.com", password_hash="hashedpassword123")
        db.add_all([user1, user2])
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(Workspace).filter(Workspace.user_id.in_(["test-edge-user", "test-edge-user-2"])).delete()
        db.query(User).filter(User.id.in_(["test-edge-user", "test-edge-user-2"])).delete()
        db.commit()


# 1. Clone timeout leaves a clean directory so fallback succeeds
def test_clone_timeout_cleans_temp_dir_for_fallback():
    """Verify that a clone timeout cleans temp_dir so fallback clone attempts do not fail on dirty directories."""
    ingestor = RepositoryIngestor()
    
    cleaned_dirs = []
    original_rmtree = shutil.rmtree

    def tracking_rmtree(path, *args, **kwargs):
        cleaned_dirs.append(path)
        return original_rmtree(path, *args, **kwargs)

    # Simulate timeout on attempt 1 (clean_branch="dev"), then success on attempt 2 (default branch)
    call_count = 0
    def mock_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Check GIT_TERMINAL_PROMPT is set to '0'
        env = kwargs.get("env", {})
        assert env.get("GIT_TERMINAL_PROMPT") == "0"
        
        if call_count == 1:
            import subprocess
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=120)
        
        # Second call succeeds
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = ""
        mock_res.stderr = ""
        return mock_res

    with patch("subprocess.run", side_effect=mock_subprocess_run), \
         patch("shutil.rmtree", side_effect=tracking_rmtree), \
         patch.object(ingestor, "collect_source_files", return_value=[]), \
         patch.object(ingestor, "_index_files", return_value={"graph_ok": True, "vector_ok": True}):
        
        res = ingestor.ingest_git_repo("https://github.com/org/repo.git", branch="dev")
        assert res["status"] == "success"
        assert call_count >= 2
        # Ensure rmtree was invoked after the timeout to clean the dirty directory
        assert len(cleaned_dirs) >= 1


# 2. Private repos give friendly error instead of "could not read Username"
def test_private_repo_friendly_error_message():
    """Verify that private repo authentication failures return a friendly error message."""
    ingestor = RepositoryIngestor()

    mock_res = MagicMock()
    mock_res.returncode = 128
    mock_res.stderr = "fatal: could not read Username for 'https://github.com': No such device or address"
    mock_res.stdout = ""

    with patch("subprocess.run", return_value=mock_res):
        res = ingestor.ingest_git_repo("https://github.com/org/private-repo.git")
        assert res["status"] == "error"
        assert "Repository is private or not found" in res["message"]
        assert "could not read Username" not in res["message"]


# 3. Per-user ingestion limits
@pytest.mark.asyncio
async def test_per_user_concurrency_and_workspace_limits():
    """Verify that per-user concurrent ingestion (429) and workspace total (400) limits are enforced."""
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == "test-edge-user").first()
        
        # Create an active INDEXING workspace
        ws1 = Workspace(
            id="ws-edge-active-1",
            user_id="test-edge-user",
            name="active-ws",
            repo_url="https://github.com/test/repo",
            type="git",
            branch="main",
            status="INDEXING",
            created_at=datetime.now(timezone.utc),
        )
        db.add(ws1)
        db.commit()

        # Register it in active jobs
        _register_active_job("ws-edge-active-1")
        try:
            # 1. Attempting another ingest for the same user should raise 429
            mock_request = MagicMock()
            mock_request.headers = {"content-type": "application/json"}
            mock_request.json = MagicMock(return_value={"repo_url": "https://github.com/test/repo2", "branch": "main", "type": "git"})
            bg = MagicMock()

            with pytest.raises(HTTPException) as exc_info:
                await ingest_workspace(mock_request, bg, db, user)
            assert exc_info.value.status_code == 429
            assert "Concurrent ingestion limit reached" in exc_info.value.detail

        finally:
            _unregister_active_job("ws-edge-active-1")

        # 2. Test max workspaces cap (set to 2 for test)
        with patch.dict(os.environ, {"MAX_WORKSPACES_PER_USER": "1", "MAX_CONCURRENT_INGESTIONS_PER_USER": "5"}):
            ws1.status = "READY"
            db.commit()
            
            with pytest.raises(HTTPException) as exc_cap:
                await ingest_workspace(mock_request, bg, db, user)
            assert exc_cap.value.status_code == 400
            assert "Workspace limit reached" in exc_cap.value.detail


# 4. 20-minute cap marks job FAILED and halts thread; _finish_ingestion does not revive it
def test_twenty_minute_cap_halts_thread_and_prevents_revival():
    """Verify that a 20-minute timeout cancels the job and halts running ingestion thread."""
    ws_id = "ws-edge-twenty-min"
    with SessionLocal() as db:
        ws = Workspace(
            id=ws_id,
            user_id="test-edge-user",
            name="slow-repo",
            repo_url="https://github.com/test/slow",
            type="git",
            branch="main",
            status="INDEXING",
            # Created 25 minutes ago
            created_at=datetime.now(timezone.utc) - timedelta(minutes=25),
        )
        db.add(ws)
        db.commit()

        _register_active_job(ws_id)
        try:
            # Reconcile should detect elapsed > 1200s, mark FAILED, and cancel_job
            reconciled = _reconcile_indexing_workspace(ws, db)
            assert reconciled.status == "FAILED"
            assert "20 minutes" in reconciled.error_message
            assert is_job_cancelled(ws_id) is True

            # Ingestion thread should raise IngestionCancelledError when is_job_cancelled is True
            ingestor = RepositoryIngestor()
            from pathlib import Path
            with pytest.raises(IngestionCancelledError):
                ingestor._index_files(tempfile.gettempdir(), [Path("dummy.py")], workspace_id=ws_id)

            # If the thread still calls _finish_ingestion, it must NOT overwrite FAILED back to READY
            _finish_ingestion(ws_id, {
                "status": "success",
                "total_files": 10,
                "indexing_summary": {"graph_ok": True, "vector_ok": True}
            })
            
            db.refresh(ws)
            assert ws.status == "FAILED", "Workspace was incorrectly revived to READY after 20-min timeout!"

        finally:
            _unregister_active_job(ws_id)
            clear_job_cancellation(ws_id)


# 5. Half-finished job after restart is marked FAILED, NOT READY
def test_half_finished_job_after_restart_is_marked_failed():
    """Verify that a half-finished job after restart (nodes in Neo4j) is marked FAILED, never reconciled to READY."""
    ws_id = "ws-edge-restart-half-finished"
    with SessionLocal() as db:
        ws = Workspace(
            id=ws_id,
            user_id="test-edge-user",
            name="interrupted-repo",
            repo_url="https://github.com/test/interrupted",
            type="git",
            branch="main",
            status="INDEXING",
            # Created 60 seconds ago before a restart
            created_at=datetime.now(timezone.utc) - timedelta(seconds=60),
        )
        db.add(ws)
        db.commit()

        # Job is NOT in _ACTIVE_INGESTION_JOBS (server just restarted)
        assert not _is_job_active(ws_id)

        # Mock Neo4j having 10 partial nodes from the first 2 files parsed before the crash
        mock_gs = MagicMock()
        mock_gs.driver.session.return_value.__enter__.return_value.run.return_value.single.return_value = {"cnt": 10}

        with patch("backend.app.api.workspace.get_graph_store", return_value=mock_gs):
            reconciled = _reconcile_indexing_workspace(ws, db)
            
            # MUST be FAILED, NOT READY!
            assert reconciled.status == "FAILED"
            assert "interrupted by server restart" in reconciled.error_message


# 6. Deleting workspace does not swallow Neo4j / Qdrant errors and prevents orphaned data
def test_delete_workspace_retains_db_record_on_storage_failure():
    """Verify that delete_workspace raises 502 and retains DB record if Neo4j or Qdrant fails."""
    ws_id = "ws-edge-delete-fail"
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == "test-edge-user").first()
        ws = Workspace(
            id=ws_id,
            user_id="test-edge-user",
            name="delete-fail-repo",
            repo_url="https://github.com/test/delete-fail",
            type="git",
            branch="main",
            status="READY",
        )
        db.add(ws)
        db.commit()

        # Mock Neo4j failing during deletion
        mock_gs = MagicMock()
        mock_gs.delete_workspace.side_effect = Exception("Neo4j connection reset")
        
        mock_vs = MagicMock()
        mock_vs.delete_workspace.return_value = True

        with patch("backend.app.api.workspace.get_graph_store", return_value=mock_gs), \
             patch("backend.app.api.workspace.get_vector_store", return_value=mock_vs):
            
            with pytest.raises(HTTPException) as exc_info:
                delete_workspace(ws_id, db, user)
            
            assert exc_info.value.status_code == 502
            assert "Graph store cleanup failed" in exc_info.value.detail

            # Ensure the workspace record is STILL in the database (not deleted, no orphaned data)
            retained_ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
            assert retained_ws is not None
            assert retained_ws.id == ws_id

        # Now mock both succeeding
        mock_gs.delete_workspace.side_effect = None
        mock_gs.delete_workspace.return_value = 5
        with patch("backend.app.api.workspace.get_graph_store", return_value=mock_gs), \
             patch("backend.app.api.workspace.get_vector_store", return_value=mock_vs):
            
            res = delete_workspace(ws_id, db, user)
            assert res["success"] is True

            # Workspace should now be deleted from DB
            deleted_ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
            assert deleted_ws is None
