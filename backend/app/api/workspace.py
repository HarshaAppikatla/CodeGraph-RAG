from backend.app.fixtures.demo_data import DEMO_WORKSPACES, DEMO_SYMBOLS_LIST
import logging
import os
import tempfile
import zipfile
from threading import Lock
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db, SessionLocal
from backend.app.models.workspace import Workspace
from backend.app.models.user import User, is_demo_user
from backend.app.api.auth import get_current_user_optional
from backend.app.services.repo_ingestor import (
    RepositoryIngestor, cancel_job, is_job_cancelled, clear_job_cancellation
)
from backend.app.services.registry import get_vector_store, get_graph_store

logger = logging.getLogger("codegraph.ingest")
router = APIRouter(prefix="/workspace", tags=["Workspaces"])

MAX_ZIP_BYTES = 1024 * 1024 * 1024  # Server-side safety cap (1 GB)

# In-memory tracking of currently running ingestion jobs (Option B)
_ACTIVE_INGESTION_JOBS_LOCK = Lock()
_ACTIVE_INGESTION_JOBS: set = set()


def _register_active_job(workspace_id: str) -> None:
    with _ACTIVE_INGESTION_JOBS_LOCK:
        _ACTIVE_INGESTION_JOBS.add(workspace_id)


def _unregister_active_job(workspace_id: str) -> None:
    with _ACTIVE_INGESTION_JOBS_LOCK:
        _ACTIVE_INGESTION_JOBS.discard(workspace_id)


def _is_job_active(workspace_id: str) -> bool:
    with _ACTIVE_INGESTION_JOBS_LOCK:
        return workspace_id in _ACTIVE_INGESTION_JOBS


# Why an ingestion failed, keyed by workspace id
INGEST_ERRORS: Dict[str, str] = {}


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    repoUrl: str
    type: str
    branch: str
    filesCount: int
    nodesCount: int
    edgesCount: int
    lastIndexed: str
    status: str
    language: str
    error: Optional[str] = None




def _to_response(ws: Workspace) -> WorkspaceResponse:
    err = getattr(ws, "error_message", None) or INGEST_ERRORS.get(ws.id)
    return WorkspaceResponse(
        id=ws.id,
        name=ws.name,
        repoUrl=ws.repo_url,
        type=ws.type,
        branch=ws.branch,
        filesCount=ws.files_count,
        nodesCount=ws.nodes_count,
        edgesCount=ws.edges_count,
        lastIndexed="Just now",
        status=ws.status,
        language=ws.language,
        error=err,
    )


def _make_ingestor() -> RepositoryIngestor:
    """Ingestor wired to the shared stores (Qdrant local mode allows only one client)."""
    return RepositoryIngestor(vector_store=get_vector_store(), graph_store=get_graph_store())


def _finish_ingestion(workspace_id: str, res: dict) -> None:
    """Updates the workspace row in a dedicated fresh DB session."""
    try:
        with SessionLocal() as db:
            ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
            if not ws:
                return
            # If the job was cancelled or already marked FAILED by timeout or restart, do not revive it!
            if is_job_cancelled(workspace_id) or ws.status == "FAILED":
                logger.info("Ingestion finished for already-cancelled/failed workspace %s; preserving status %s", workspace_id, ws.status)
                return
            if res.get("status") != "success":
                err_msg = res.get("message") or "Ingestion failed."
                INGEST_ERRORS[ws.id] = err_msg
                ws.error_message = err_msg
                ws.status = "FAILED"
            elif res.get("total_files", 0) == 0:
                err_msg = "No indexable source files were found."
                INGEST_ERRORS[ws.id] = err_msg
                ws.error_message = err_msg
                ws.status = "FAILED"
            else:
                summary = res.get("indexing_summary", {})
                graph_ok = summary.get("graph_ok", False)
                vector_ok = summary.get("vector_ok", False)
                graph_nodes = summary.get("graph_nodes", 0)
                vector_chunks = summary.get("vector_chunks", 0)

                if not graph_ok and not vector_ok:
                    # Neither backend accepted any writes — treat as FAILED so the UI
                    # doesn't show READY with inflated parser-estimate counts.
                    err_msg = (
                        "Indexing completed but no data was written to either the graph store "
                        "(Neo4j may be down) or the vector store (embedding model may have failed to load). "
                        f"Parser saw {graph_nodes} nodes and {vector_chunks} vector chunks, but none were committed."
                    )
                    INGEST_ERRORS[ws.id] = err_msg
                    ws.error_message = err_msg
                    ws.status = "FAILED"
                    ws.nodes_count = 0
                    ws.edges_count = 0
                else:
                    if graph_ok and not vector_ok:
                        ws.status = "PARTIAL"
                        ws.error_message = (
                            "Graph store indexed successfully, but vector embeddings could not be stored "
                            "(embedding model may have failed to load). Semantic search will not work."
                        )
                        INGEST_ERRORS[ws.id] = ws.error_message
                    elif vector_ok and not graph_ok:
                        ws.status = "PARTIAL"
                        gs = get_graph_store()
                        if not (gs and gs.driver):
                            ws.error_message = (
                                "Vector embeddings indexed successfully, but graph store writes failed "
                                "(Neo4j is down or unreachable). Blast-radius and impact analysis will not work."
                            )
                        else:
                            ws.error_message = (
                                "Vector embeddings indexed successfully. No AST-parsable symbols (functions, classes) "
                                "were detected in this repository. Blast-radius and graph analysis are inactive."
                            )
                        INGEST_ERRORS[ws.id] = ws.error_message
                    else:
                        truncation_warning = res.get("warning") or summary.get("warning")
                        if truncation_warning:
                            ws.status = "PARTIAL"
                            ws.error_message = truncation_warning
                            INGEST_ERRORS[ws.id] = truncation_warning
                        else:
                            # Both backends confirmed real writes and no truncation
                            ws.status = "READY"
                            ws.error_message = None
                            INGEST_ERRORS.pop(ws.id, None)

                    if res.get("branch"):
                        ws.branch = res["branch"]
                    ws.files_count = res.get("total_files", 0)
                    # Store only confirmed write counts, not parser estimates
                    ws.nodes_count = summary.get("graph_nodes", 0) if graph_ok else 0
                    ws.edges_count = summary.get("graph_edges", 0) if graph_ok else 0
                    languages = summary.get("languages") or []
                    ws.language = " / ".join(languages[:2]) if languages else "Polyglot"
                    logger.info(
                        "🎉 Workspace %s ingestion %s: %d files (total found: %s), %d nodes, %d edges, %d vectors "
                        "(graph_ok=%s, vector_ok=%s)",
                        ws.id, ws.status, ws.files_count, res.get("total_files_found", ws.files_count),
                        ws.nodes_count, ws.edges_count, vector_chunks, graph_ok, vector_ok
                    )
            db.commit()
    except Exception as e:
        logger.exception("Failed to finish ingestion for workspace %s: %s", workspace_id, e)


def _fail_ingestion(workspace_id: str, exc: Exception) -> None:
    logger.exception("Ingestion crashed for workspace %s", workspace_id)
    err_msg = f"{type(exc).__name__}: {exc}"
    INGEST_ERRORS[workspace_id] = err_msg
    try:
        with SessionLocal() as db:
            ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
            if ws:
                ws.status = "FAILED"
                ws.error_message = err_msg
                db.commit()
    except Exception as dbe:
        logger.error("Failed to set FAILED state in DB for workspace %s: %s", workspace_id, dbe)


def _run_background_git_ingestion(workspace_id: str, repo_url: str, branch: str):
    """Background task running actual AST parsing, vector embedding, and graph ingestion."""
    _register_active_job(workspace_id)
    try:
        res = _make_ingestor().ingest_git_repo(repo_url, branch=branch, workspace_id=workspace_id)
        _finish_ingestion(workspace_id, res)
    except Exception as e:
        _fail_ingestion(workspace_id, e)
    finally:
        _unregister_active_job(workspace_id)
        clear_job_cancellation(workspace_id)


def _run_background_zip_ingestion(workspace_id: str, temp_zip_path: str):
    """Background task extracting and indexing uploaded project archive."""
    _register_active_job(workspace_id)
    try:
        res = _make_ingestor().ingest_zip_archive(temp_zip_path, workspace_id=workspace_id)
        _finish_ingestion(workspace_id, res)
    except Exception as e:
        _fail_ingestion(workspace_id, e)
    finally:
        _unregister_active_job(workspace_id)
        clear_job_cancellation(workspace_id)
        if os.path.exists(temp_zip_path):
            try:
                os.remove(temp_zip_path)
            except Exception:
                pass


def _reconcile_indexing_workspace(ws: Workspace, db: Session) -> Workspace:
    """Universal Auto-Reconciliation:
    1. If INDEXING, check if background job finished or was interrupted by a restart.
    2. If READY or PARTIAL, verify vector and graph store persistence to catch data loss on restart.
    """
    if not ws:
        return ws

    # Health check for READY / PARTIAL workspaces: detect data loss after server restart
    if ws.status in ("READY", "PARTIAL"):
        is_demo_ws = ws.id.startswith("ws-demo-") or any(dw["id"] == ws.id for dw in DEMO_WORKSPACES)
        if not is_demo_ws and ws.files_count > 0:
            try:
                vs = get_vector_store()
                vec_cnt = vs.count_workspace_vectors(ws.id) if (vs and hasattr(vs, "count_workspace_vectors")) else None
            except Exception as ve:
                logger.warning("Vector health check error for %s: %s", ws.id, ve)
                vec_cnt = None

            try:
                gs = get_graph_store()
                graph_cnt = gs.count_workspace_nodes(ws.id) if (gs and hasattr(gs, "count_workspace_nodes") and gs.driver) else None
            except Exception as ge:
                logger.warning("Graph health check error for %s: %s", ws.id, ge)
                graph_cnt = None

            if vec_cnt is not None and graph_cnt is not None:
                db_ws = db.query(Workspace).filter(Workspace.id == ws.id).first() if ws not in db else ws
                if not db_ws:
                    return ws

                if vec_cnt == 0 and graph_cnt == 0:
                    db_ws.status = "FAILED"
                    db_ws.error_message = "Indexed data was lost after server restart. Please re-index this repository."
                    INGEST_ERRORS[db_ws.id] = db_ws.error_message
                    db.commit()
                    db.refresh(db_ws)
                    logger.warning("Workspace %s data lost after restart -> marked FAILED", db_ws.id)
                    return db_ws
                elif vec_cnt == 0 and graph_cnt > 0 and db_ws.status == "READY":
                    db_ws.status = "PARTIAL"
                    db_ws.error_message = "Vector embeddings were lost after server restart. Semantic search is unavailable. Please re-index."
                    INGEST_ERRORS[db_ws.id] = db_ws.error_message
                    db.commit()
                    db.refresh(db_ws)
                    logger.warning("Workspace %s vectors lost after restart -> downgraded to PARTIAL", db_ws.id)
                    return db_ws
                elif graph_cnt == 0 and vec_cnt > 0 and db_ws.status == "READY":
                    db_ws.status = "PARTIAL"
                    db_ws.error_message = "Knowledge graph was lost after server restart. Blast radius and architecture views are unavailable. Please re-index."
                    INGEST_ERRORS[db_ws.id] = db_ws.error_message
                    db.commit()
                    db.refresh(db_ws)
                    logger.warning("Workspace %s graph lost after restart -> downgraded to PARTIAL", db_ws.id)
                    return db_ws

        return ws

    if ws.status != "INDEXING":
        return ws

    is_active = _is_job_active(ws.id)
    created_tz = ws.created_at.replace(tzinfo=timezone.utc) if (ws.created_at and ws.created_at.tzinfo is None) else (ws.created_at or datetime.now(timezone.utc))
    elapsed_seconds = (datetime.now(timezone.utc) - created_tz).total_seconds()

    db_ws = db.query(Workspace).filter(Workspace.id == ws.id).first() if ws not in db else ws
    if not db_ws:
        return ws

    # 1. Job is actively running in this process
    if is_active:
        if elapsed_seconds > 1200:  # 20 minutes safety cap
            cancel_job(ws.id)
            db_ws.status = "FAILED"
            db_ws.error_message = "Ingestion exceeded maximum safety cap (20 minutes). Please try a smaller repository."
            INGEST_ERRORS[db_ws.id] = db_ws.error_message
            db.commit()
            db.refresh(db_ws)
            logger.warning("Active workspace %s exceeded 20m safety cap, marked FAILED and halted thread", db_ws.id)
            return db_ws
        return ws

    # 2. Job is NOT active in this process: server restarted or process crashed.
    # Never reconcile an incomplete or interrupted job to READY just because partial nodes exist!
    # Allow 15s grace period for freshly queued background tasks to register in _ACTIVE_INGESTION_JOBS.
    if elapsed_seconds > 15:
        cancel_job(ws.id)
        db_ws.status = "FAILED"
        db_ws.error_message = "Ingestion interrupted by server restart. Please re-index."
        INGEST_ERRORS[db_ws.id] = db_ws.error_message
        db.commit()
        db.refresh(db_ws)
        logger.info("Auto-marked restart-orphaned INDEXING workspace %s (%s) as FAILED", db_ws.id, db_ws.name)
        return db_ws

    return ws


def _owned_workspace(db: Session, workspace_id: str, current_user: Optional[User] = None) -> Workspace:
    """Strictly enforces tenant isolation: visitors only access and manage their own workspaces."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required to access workspace.")

    ws = db.query(Workspace).filter(Workspace.id == workspace_id, Workspace.user_id == current_user.id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found or unauthorized.")
    return ws


@router.get("/list", response_model=List[WorkspaceResponse])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Returns active workspaces for the current developer session."""
    if not current_user:
        # Anonymous visitors see only the preloaded read-only demo workspaces
        return [WorkspaceResponse(**dw) for dw in DEMO_WORKSPACES]

    if is_demo_user(current_user):
        db_workspaces = (
            db.query(Workspace)
            .filter(Workspace.user_id == current_user.id)
            .order_by(Workspace.created_at.desc())
            .all()
        )
        custom_workspaces = [_to_response(_reconcile_indexing_workspace(ws, db)) for ws in db_workspaces]
        custom_ids = {ws.id for ws in custom_workspaces}

        # Preloaded demo workspaces (Study-Sync & Payment-Gateway) for demo account
        demos = [WorkspaceResponse(**dw) for dw in DEMO_WORKSPACES if dw["id"] not in custom_ids]
        return demos + custom_workspaces

    # Real registered/logged in user: strictly return ONLY workspaces belonging to this user
    db_workspaces = (
        db.query(Workspace)
        .filter(Workspace.user_id == current_user.id)
        .order_by(Workspace.created_at.desc())
        .all()
    )
    return [_to_response(_reconcile_indexing_workspace(ws, db)) for ws in db_workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Real status and counts for one workspace (the UI polls this while INDEXING)."""
    for dw in DEMO_WORKSPACES:
        if dw["id"] == workspace_id:
            return WorkspaceResponse(**dw)
    ws = _owned_workspace(db, workspace_id, current_user)
    return _to_response(_reconcile_indexing_workspace(ws, db))


@router.get("/{workspace_id}/symbols")
def list_workspace_symbols(
    workspace_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Classes/functions actually indexed for this workspace (feeds the symbol picker)."""
    if any(dw["id"] == workspace_id for dw in DEMO_WORKSPACES):
        return {
            "status": "READY",
            "symbols": DEMO_SYMBOLS_LIST,
        }
    ws = _owned_workspace(db, workspace_id, current_user)
    symbols = []
    if ws.status == "READY":
        try:
            # 1. Query Neo4j AST graph for rich structural symbols
            symbols = get_graph_store().list_symbols(workspace_id)
        except Exception as ge:
            logger.warning(f"Neo4j symbol lookup notice: {ge}")

        # 2. Fall back to Qdrant vector store if needed
        if not symbols:
            try:
                symbols = get_vector_store().list_symbols(workspace_id)
            except Exception as ve:
                logger.warning(f"Vector store symbol lookup notice: {ve}")

    return {"status": ws.status, "symbols": symbols}


@router.delete("/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Permanently deletes a workspace and cleans up its graph nodes (Neo4j), vector embeddings (Qdrant), and DB row."""
    # 1. Protect canned demo workspaces from deletion
    if any(dw["id"] == workspace_id for dw in DEMO_WORKSPACES) or workspace_id.startswith("ws-demo-"):
        raise HTTPException(
            status_code=403,
            detail="Preloaded sample demo workspaces cannot be deleted.",
        )

    # 2. Authenticate ownership
    ws = _owned_workspace(db, workspace_id, current_user)
    ws_name = ws.name

    # 3. Purge error cache and signal cancellation to any running background thread
    INGEST_ERRORS.pop(ws.id, None)
    cancel_job(ws.id)

    # 4. Detach and delete all nodes and relationships in Neo4j
    deleted_nodes = 0
    cleanup_errors = []

    try:
        gs = get_graph_store()
        if gs and hasattr(gs, "delete_workspace"):
            deleted_nodes = gs.delete_workspace(ws.id)
    except Exception as ge:
        logger.error("Neo4j deletion failed for workspace %s: %s", ws.id, ge)
        cleanup_errors.append(f"Graph store cleanup failed: {ge}")

    # 5. Delete vector embeddings in Qdrant
    try:
        vs = get_vector_store()
        if vs and hasattr(vs, "delete_workspace"):
            vs.delete_workspace(ws.id)
    except Exception as ve:
        logger.error("Qdrant deletion failed for workspace %s: %s", ws.id, ve)
        cleanup_errors.append(f"Vector store cleanup failed: {ve}")

    # If any external storage service failed to delete data, DO NOT delete workspace record from DB!
    # Retaining the DB row prevents orphaned data in Neo4j/Qdrant and allows retry.
    if cleanup_errors:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Failed to cleanly delete workspace '{ws_name}'. Data cleanup error in backend storage. "
                f"The workspace record was retained to prevent orphaned data. Errors: {'; '.join(cleanup_errors)}"
            ),
        )

    # 6. Delete workspace record from database only when external stores succeeded
    db.delete(ws)
    db.commit()

    logger.info("Successfully deleted workspace %s ('%s') and purged %d Neo4j nodes.", ws.id, ws_name, deleted_nodes)
    return {
        "success": True,
        "message": f"Workspace '{ws_name}' deleted successfully.",
        "workspace_id": workspace_id,
        "deleted_nodes": deleted_nodes,
    }



@router.post("/ingest", response_model=WorkspaceResponse)
async def ingest_workspace(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Initiates dual-store ingestion for a Git repository or local ZIP archive (JSON or Form)."""
    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required to ingest a workspace. Please sign in or click 1-Click Demo.",
        )
    user_id = current_user.id

    max_concurrent = int(os.getenv("MAX_CONCURRENT_INGESTIONS_PER_USER") or getattr(settings, "MAX_CONCURRENT_INGESTIONS_PER_USER", 1))
    max_workspaces = int(os.getenv("MAX_WORKSPACES_PER_USER") or getattr(settings, "MAX_WORKSPACES_PER_USER", 25))

    # Reconcile existing indexing workspaces for this user to ensure dead jobs from restarts are cleared
    existing_indexing = db.query(Workspace).filter(Workspace.user_id == user_id, Workspace.status == "INDEXING").all()
    for active_ws in existing_indexing:
        _reconcile_indexing_workspace(active_ws, db)

    # 1. Check total workspaces limit per user
    user_workspaces_count = db.query(Workspace).filter(Workspace.user_id == user_id).count()
    if user_workspaces_count >= max_workspaces:
        raise HTTPException(
            status_code=400,
            detail=f"Workspace limit reached. You have {user_workspaces_count} workspaces (maximum {max_workspaces}). Please delete an existing workspace before ingesting a new one."
        )

    # 2. Check active concurrent ingestion limit per user
    active_user_ingestions = db.query(Workspace).filter(
        Workspace.user_id == user_id,
        Workspace.status == "INDEXING"
    ).count()
    if active_user_ingestions >= max_concurrent:
        raise HTTPException(
            status_code=429,
            detail=f"Concurrent ingestion limit reached. You already have an active ingestion job running (maximum {max_concurrent}). Please wait for it to complete."
        )

    content_type = request.headers.get("content-type", "")

    repo_url = None
    branch = "main"
    upload_type = "git"
    file = None

    if "application/json" in content_type:
        body = await request.json()
        repo_url = body.get("repo_url")
        branch = body.get("branch", "main")
        upload_type = body.get("type", "git")
    else:
        form = await request.form()
        repo_url = form.get("repo_url")
        branch = form.get("branch", "main")
        upload_type = form.get("upload_type", form.get("type", "git"))
        file = form.get("file")

    if upload_type == "git":
        if not repo_url or not isinstance(repo_url, str):
            raise HTTPException(status_code=400, detail="repo_url is required for git ingestion.")
        clean_url = repo_url.strip()
        if clean_url.startswith("-") or any(ch in clean_url for ch in [";", "&", "|", "`", "$", "\n", "\r", " "]):
            raise HTTPException(status_code=400, detail="Invalid repository URL format.")
        parsed_url = urlparse(clean_url)
        if parsed_url.scheme != "https":
            raise HTTPException(status_code=400, detail="Only secure https:// Git repository URLs are allowed.")
        hostname = (parsed_url.hostname or "").lower().strip()
        if not hostname:
            raise HTTPException(status_code=400, detail="Invalid Git repository domain.")

        # SSRF Protection: Block internal, loopback, and cloud metadata addresses
        if hostname in ("localhost", "127.0.0.1", "::1", "169.254.169.254", "0.0.0.0"):
            raise HTTPException(status_code=400, detail="Internal, metadata, or loopback Git addresses are not permitted.")

        allowed_hosts = [h.strip().lower() for h in getattr(settings, "GIT_ALLOWED_HOSTS", "github.com,gitlab.com,bitbucket.org").split(",") if h.strip()]
        clean_hostname = hostname.removeprefix("www.")
        if clean_hostname not in allowed_hosts and hostname not in allowed_hosts:
            raise HTTPException(
                status_code=400,
                detail=f"Git host '{hostname}' is not permitted. Allowed hosts: {', '.join(allowed_hosts)}"
            )

        clean_branch = (branch or "main").strip()
        if clean_branch.startswith("-") or any(ch in clean_branch for ch in [";", "&", "|", "`", "$", "\n", "\r", " "]):
            clean_branch = "main"

        ws_name = clean_url.rstrip("/").split("/")[-1].replace(".git", "") or "Git-Repository"
        ws = Workspace(
            user_id=user_id,
            name=ws_name,
            repo_url=clean_url,
            type="git",
            branch=clean_branch,
            status="INDEXING",
            language="Detecting...",
        )
        db.add(ws)
        db.commit()
        db.refresh(ws)
        _register_active_job(ws.id)
        background_tasks.add_task(_run_background_git_ingestion, ws.id, clean_url, clean_branch)

    elif upload_type == "zip":
        # ZIP upload handling (multipart form with a 'file' field)
        if not (file and hasattr(file, "file")):
            raise HTTPException(
                status_code=400,
                detail="A .zip file upload (multipart form field 'file') is required for type 'zip'.",
            )
        filename = getattr(file, "filename", None) or "uploaded-project.zip"

        # Save to disk with a size cap, then validate it is really a zip BEFORE creating a workspace
        fd, temp_zip = tempfile.mkstemp(suffix=".zip")
        written = 0
        try:
            with os.fdopen(fd, "wb") as f:
                while True:
                    block = file.file.read(1024 * 1024)
                    if not block:
                        break
                    written += len(block)
                    if written > MAX_ZIP_BYTES:
                        raise HTTPException(status_code=413, detail=f"ZIP is larger than the {MAX_ZIP_BYTES // (1024 * 1024)} MB limit.")
                    f.write(block)
            if not zipfile.is_zipfile(temp_zip):
                raise HTTPException(status_code=400, detail="The uploaded file is not a valid .zip archive.")
        except HTTPException:
            os.remove(temp_zip)
            raise

        ws = Workspace(
            user_id=user_id,
            name=filename.rsplit(".", 1)[0] if filename.lower().endswith(".zip") else filename,
            repo_url=filename,
            type="zip",
            branch="local",
            status="INDEXING",
            language="Detecting...",
        )
        db.add(ws)
        db.commit()
        db.refresh(ws)
        _register_active_job(ws.id)
        background_tasks.add_task(_run_background_zip_ingestion, ws.id, temp_zip)

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported ingestion type '{upload_type}'. Use 'git' or 'zip'.",
        )

    return _to_response(ws)
