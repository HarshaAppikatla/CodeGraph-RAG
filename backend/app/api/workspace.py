import logging
import os
import tempfile
import zipfile
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.database import get_db, SessionLocal
from backend.app.models.workspace import Workspace
from backend.app.models.user import User
from backend.app.api.auth import get_current_user_optional
from backend.app.services.repo_ingestor import RepositoryIngestor
from backend.app.services.registry import get_vector_store, get_graph_store

logger = logging.getLogger("codegraph.ingest")
router = APIRouter(prefix="/workspace", tags=["Workspaces"])

MAX_ZIP_BYTES = 500 * 1024 * 1024  # Server-side safety cap (500 MB)

# Why an ingestion failed, keyed by workspace id (process-local; the DB has no column for it)
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


DEMO_WORKSPACES = [
    {
        "id": "ws-study-sync",
        "name": "Study-Sync Backend",
        "repoUrl": "https://github.com/HarshaAppikatla/Study-Sync",
        "type": "git",
        "branch": "main",
        "filesCount": 211,
        "nodesCount": 2533,
        "edgesCount": 1195,
        "lastIndexed": "Just now",
        "status": "READY",
        "language": "Java / Spring Boot",
    },
    {
        "id": "ws-payment-gw",
        "name": "Payment-Gateway Microservice",
        "repoUrl": "payment-gateway-service.zip",
        "type": "zip",
        "branch": "release/v2.1",
        "filesCount": 148,
        "nodesCount": 1820,
        "edgesCount": 840,
        "lastIndexed": "2 hours ago",
        "status": "READY",
        "language": "Go / gRPC",
    },
]


def _to_response(ws: Workspace) -> WorkspaceResponse:
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
        error=INGEST_ERRORS.get(ws.id),
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
            if res.get("status") != "success":
                INGEST_ERRORS[ws.id] = res.get("message") or "Ingestion failed."
                ws.status = "FAILED"
            elif res.get("total_files", 0) == 0:
                INGEST_ERRORS[ws.id] = "No indexable source files were found."
                ws.status = "FAILED"
            else:
                summary = res.get("indexing_summary", {})
                ws.status = "READY"
                if res.get("branch"):
                    ws.branch = res["branch"]
                ws.files_count = res.get("total_files", 0)
                ws.nodes_count = summary.get("graph_nodes", 0)
                ws.edges_count = summary.get("graph_edges", 0)
                languages = summary.get("languages") or []
                ws.language = " / ".join(languages[:2]) if languages else "Polyglot"
                INGEST_ERRORS.pop(ws.id, None)
            db.commit()
    except Exception as e:
        logger.exception("Failed to finish ingestion for workspace %s: %s", workspace_id, e)


def _fail_ingestion(workspace_id: str, exc: Exception) -> None:
    logger.exception("Ingestion crashed for workspace %s", workspace_id)
    INGEST_ERRORS[workspace_id] = f"{type(exc).__name__}: {exc}"
    try:
        with SessionLocal() as db:
            ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
            if ws:
                ws.status = "FAILED"
                db.commit()
    except Exception as dbe:
        logger.error("Failed to set FAILED state in DB for workspace %s: %s", workspace_id, dbe)


def _run_background_git_ingestion(workspace_id: str, repo_url: str, branch: str):
    """Background task running actual AST parsing, vector embedding, and graph ingestion."""
    try:
        res = _make_ingestor().ingest_git_repo(repo_url, branch=branch, workspace_id=workspace_id)
        _finish_ingestion(workspace_id, res)
    except Exception as e:
        _fail_ingestion(workspace_id, e)


def _run_background_zip_ingestion(workspace_id: str, temp_zip_path: str):
    """Background task extracting and indexing uploaded project archive."""
    try:
        res = _make_ingestor().ingest_zip_archive(temp_zip_path, workspace_id=workspace_id)
        _finish_ingestion(workspace_id, res)
    except Exception as e:
        _fail_ingestion(workspace_id, e)
    finally:
        if os.path.exists(temp_zip_path):
            try:
                os.remove(temp_zip_path)
            except Exception:
                pass


def _reconcile_indexing_workspace(ws: Workspace, db: Session) -> Workspace:
    """Universal Auto-Reconciliation: If a workspace is INDEXING, check if Neo4j already indexed nodes for it."""
    if not ws or ws.status != "INDEXING":
        return ws

    try:
        gs = get_graph_store()
        if gs and gs.driver:
            with gs.driver.session() as session:
                f_res = session.run('MATCH (f:File {ws: $ws}) RETURN count(f) as cnt', ws=ws.id).single()
                files_cnt = f_res['cnt'] if f_res else 0
                n_res = session.run('MATCH (n {ws: $ws}) RETURN count(n) as cnt', ws=ws.id).single()
                nodes_cnt = n_res['cnt'] if n_res else 0
                e_res = session.run('MATCH (a {ws: $ws})-[r]->(b {ws: $ws}) RETURN count(r) as cnt', ws=ws.id).single()
                edges_cnt = e_res['cnt'] if e_res else 0

                if nodes_cnt > 0:
                    ws.status = "READY"
                    ws.files_count = files_cnt or 1
                    ws.nodes_count = nodes_cnt
                    ws.edges_count = edges_cnt
                    if ws.language in ("Detecting...", "Unknown"):
                        ws.language = "Polyglot"
                    db.commit()
                    db.refresh(ws)
                    logger.info("Auto-reconciled workspace %s (%s) to READY (%d nodes)", ws.id, ws.name, nodes_cnt)
    except Exception as err:
        logger.warning("Reconciliation check error for %s: %s", ws.id, err)

    return ws


def _is_demo_user(current_user: Optional[User]) -> bool:
    """Helper to detect if the session is operating in public demo mode."""
    if current_user is None:
        return True
    return current_user.email == "harsha.demo@codegraph.ai" or current_user.id == "usr-demo-777"


def _owned_workspace(db: Session, workspace_id: str, current_user: Optional[User] = None) -> Workspace:
    # Allow looking up workspace by ID with strict tenant boundary for non-demo users
    query = db.query(Workspace).filter(Workspace.id == workspace_id)
    if not _is_demo_user(current_user) and current_user:
        query = query.filter(Workspace.user_id == current_user.id)
    ws = query.first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return ws


@router.get("/list", response_model=List[WorkspaceResponse])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Returns active workspaces for the current developer session or returns defaults for demo account."""
    if _is_demo_user(current_user):
        demo_user_id = current_user.id if current_user else "usr-demo-777"
        db_workspaces = (
            db.query(Workspace)
            .filter((Workspace.user_id == demo_user_id) | (Workspace.user_id == "usr-demo-777"))
            .order_by(Workspace.created_at.desc())
            .all()
        )
        custom_workspaces = [_to_response(_reconcile_indexing_workspace(ws, db)) for ws in db_workspaces]
        custom_ids = {ws.id for ws in custom_workspaces}

        # Preloaded demo workspaces (Study-Sync & Payment-Gateway) for demo account only
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
    if _is_demo_user(current_user):
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
    if _is_demo_user(current_user) and any(dw["id"] == workspace_id for dw in DEMO_WORKSPACES):
        return {
            "status": "READY",
            "symbols": [
                {"name": "generateToken", "file": "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/JwtService.java"},
                {"name": "authenticate", "file": "studysync-backend/src/main/java/com/studysync/studysyncbackend/service/AuthenticationService.java"},
                {"name": "registerStompEndpoints", "file": "studysync-backend/src/main/java/com/studysync/studysyncbackend/config/WebSocketConfig.java"},
            ],
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
    if any(dw["id"] == workspace_id for dw in DEMO_WORKSPACES) or workspace_id.startswith("ws-"):
        raise HTTPException(
            status_code=400,
            detail="Preloaded demo workspaces cannot be deleted.",
        )

    # 2. Authenticate ownership
    ws = _owned_workspace(db, workspace_id, current_user)
    ws_name = ws.name

    # 3. Purge error cache
    INGEST_ERRORS.pop(ws.id, None)

    # 4. Detach and delete all nodes and relationships in Neo4j
    deleted_nodes = 0
    try:
        gs = get_graph_store()
        if gs:
            deleted_nodes = gs.delete_workspace(ws.id)
    except Exception as ge:
        logger.warning("Neo4j deletion notice for workspace %s: %s", ws.id, ge)

    # 5. Delete vector embeddings in Qdrant
    try:
        vs = get_vector_store()
        if vs:
            vs.delete_workspace(ws.id)
    except Exception as ve:
        logger.warning("Qdrant deletion notice for workspace %s: %s", ws.id, ve)

    # 6. Delete workspace record from PostgreSQL database
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
    user_id = current_user.id if current_user else "usr-demo-777"
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
        if not repo_url:
            raise HTTPException(status_code=400, detail="repo_url is required for git ingestion.")
        ws_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "") or "Git-Repository"
        ws = Workspace(
            user_id=user_id,
            name=ws_name,
            repo_url=repo_url,
            type="git",
            branch=branch or "main",
            status="INDEXING",
            language="Detecting...",
        )
        db.add(ws)
        db.commit()
        db.refresh(ws)
        background_tasks.add_task(_run_background_git_ingestion, ws.id, repo_url, branch or "main")

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
        background_tasks.add_task(_run_background_zip_ingestion, ws.id, temp_zip)

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported ingestion type '{upload_type}'. Use 'git' or 'zip'.",
        )

    return _to_response(ws)
