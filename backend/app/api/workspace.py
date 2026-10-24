import os
import shutil
import tempfile
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.database import get_db, SessionLocal
from backend.app.models.workspace import Workspace
from backend.app.models.user import User
from backend.app.api.auth import get_current_user_optional
from backend.app.services.repo_ingestor import RepositoryIngestor
from backend.app.services.registry import get_vector_store, get_graph_store

router = APIRouter(prefix="/workspace", tags=["Workspaces"])


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


class IngestGitRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = "main"
    name: Optional[str] = None


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


def _make_ingestor() -> RepositoryIngestor:
    """Ingestor wired to the shared stores (Qdrant local mode allows only one client)."""
    return RepositoryIngestor(vector_store=get_vector_store(), graph_store=get_graph_store())


def _run_background_git_ingestion(workspace_id: str, repo_url: str, branch: str):
    """Background task running actual AST parsing, vector embedding, and graph ingestion."""
    db: Session = SessionLocal()
    try:
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not ws:
            return
        ingestor = _make_ingestor()
        res = ingestor.ingest_git_repo(repo_url, branch=branch, workspace_id=workspace_id)
        if res.get("status") == "success":
            summary = res.get("indexing_summary", {})
            ws.status = "READY"
            ws.files_count = res.get("total_files", 0)
            ws.nodes_count = summary.get("graph_nodes", 0)
            ws.edges_count = summary.get("graph_edges", 0)
        else:
            ws.status = "FAILED"
        db.commit()
    except Exception as e:
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if ws:
            ws.status = "FAILED"
            db.commit()
    finally:
        db.close()


def _run_background_zip_ingestion(workspace_id: str, temp_zip_path: str):
    """Background task extracting and indexing uploaded project archive."""
    db: Session = SessionLocal()
    try:
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not ws:
            return
        ingestor = _make_ingestor()
        res = ingestor.ingest_zip_archive(temp_zip_path, workspace_id=workspace_id)
        if res.get("status") == "success":
            summary = res.get("indexing_summary", {})
            ws.status = "READY"
            ws.files_count = res.get("total_files", 0)
            ws.nodes_count = summary.get("graph_nodes", 0)
            ws.edges_count = summary.get("graph_edges", 0)
        else:
            ws.status = "FAILED"
        db.commit()
    except Exception as e:
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if ws:
            ws.status = "FAILED"
            db.commit()
    finally:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
        db.close()


@router.get("/list", response_model=List[WorkspaceResponse])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Returns active workspaces for the current developer session or returns defaults."""
    user_id = current_user.id if current_user else "usr-demo-777"
    db_workspaces = db.query(Workspace).filter(Workspace.user_id == user_id).all()

    results: List[WorkspaceResponse] = []
    for ws in db_workspaces:
        results.append(
            WorkspaceResponse(
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
            )
        )

    # If user has no custom workspaces yet, provide default demo workspaces
    if not results:
        for dw in DEMO_WORKSPACES:
            results.append(WorkspaceResponse(**dw))

    return results


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
            files_count=211,
            nodes_count=2533,
            edges_count=1195,
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
        ws_name = (getattr(file, "filename", None) or "uploaded-project").replace(".zip", "")
        temp_zip = None
        if file and hasattr(file, "file"):
            fd, temp_zip = tempfile.mkstemp(suffix=".zip")
            with os.fdopen(fd, "wb") as f:
                shutil.copyfileobj(file.file, f)

        ws = Workspace(
            user_id=user_id,
            name=ws_name,
            repo_url=getattr(file, "filename", None) or "archive.zip",
            type="zip",
            branch="local",
            status="INDEXING",
            files_count=148,
            nodes_count=1820,
            edges_count=840,
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
    )
