import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.database import init_db
from backend.app.api.auth import router as auth_router
from backend.app.api.workspace import router as workspace_router
from backend.app.api.rag import router as rag_router
from backend.app.api.keys import router as keys_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    init_db()
    # Pre-warm vector store and SentenceTransformer in background thread so user never waits on cold start
    import threading
    from backend.app.services.registry import get_vector_store
    threading.Thread(target=get_vector_store, daemon=True, name="prewarm_vector_store").start()
    yield


app = FastAPI(
    title="CodeGraph-RAG Backend Engine",
    description="Multi-tenant Codebase RAG, AST Scope Resolution & Blast-Radius Engine",
    version="2.0.0",
    lifespan=lifespan,
)

# Production CORS Hardening
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
custom_origins = os.getenv("ALLOWED_ORIGINS")
if custom_origins:
    ALLOWED_ORIGINS.extend([origin.strip() for origin in custom_origins.split(",") if origin.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers under /api
app.include_router(auth_router, prefix="/api")
app.include_router(workspace_router, prefix="/api")
app.include_router(rag_router, prefix="/api")
app.include_router(keys_router, prefix="/api")


@app.get("/")
def root_endpoint():
    return {
        "status": "online",
        "service": "CodeGraph-RAG Backend Engine",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    """Standard health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "database": "connected",
        "mcp_protocol": "supported",
    }
