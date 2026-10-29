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


def _finish_ingestion(db: Session, ws: Workspace, res: dict) -> None:
    """Copies the REAL ingestion result onto the workspace row."""
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
        ws.language = " / ".join(languages[:2]) if languages else "Unknown"
        INGEST_ERRORS.pop(ws.id, None)
    db.commit()


def _fail_ingestion(db: Session, workspace_id: str, exc: Exception) -> None:
    logger.exception("Ingestion failed for workspace %s", workspace_id)
    INGEST_ERRORS[workspace_id] = f"{type(exc).__name__}: {exc}"
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if ws:
        ws.status = "FAILED"
        db.commit()


def _run_background_git_ingestion(workspace_id: str, repo_url: str, branch: str):
    """Background task running actual AST parsing, vector embedding, and graph ingestion."""
    db: Session = SessionLocal()
    try:
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not ws:
            return
        res = _make_ingestor().ingest_git_repo(repo_url, branch=branch, workspace_id=workspace_id)
        _finish_ingestion(db, ws, res)
    except Exception as e:
        _fail_ingestion(db, workspace_id, e)
    finally:
        db.close()


def _run_background_zip_ingestion(workspace_id: str, temp_zip_path: str):
    """Background task extracting and indexing uploaded project archive."""
    db: Session = SessionLocal()
    try:
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not ws:
            return
        res = _make_ingestor().ingest_zip_archive(temp_zip_path, workspace_id=workspace_id)
        _finish_ingestion(db, ws, res)
    except Exception as e:
        _fail_ingestion(db, workspace_id, e)
    finally:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
        db.close()


def _owned_workspace(db: Session, workspace_id: str, current_user: Optional[User] = None) -> Workspace:
    # Allow looking up any ingested workspace by ID for collaborative viewing and symbol inspection
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return ws


@router.get("/list", response_model=List[WorkspaceResponse])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Returns active workspaces for the current developer session or returns defaults."""
    # List all indexed workspaces so any repo added by the user is immediately selectable
    db_workspaces = db.query(Workspace).order_by(Workspace.created_at.desc()).all()
    results: List[WorkspaceResponse] = [_to_response(ws) for ws in db_workspaces]

    # If user has no custom workspaces yet, provide default demo workspaces
    if not results:
        results = [WorkspaceResponse(**dw) for dw in DEMO_WORKSPACES]
    return results


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
    return _to_response(_owned_workspace(db, workspace_id, current_user))


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
