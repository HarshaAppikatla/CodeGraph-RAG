"""Process-wide store singletons.

Qdrant's local file mode only allows ONE client per storage folder; a second
CodeVectorStore silently falls back to an empty in-memory client. Ingestion
(background task) and querying (request handlers) must therefore share one.
"""
import threading
import time
from typing import Optional

from backend.app.services.vector_store import CodeVectorStore
from backend.app.services.graph_store import Neo4jGraphStore

_vector_lock = threading.Lock()
_graph_lock = threading.Lock()
_vector_store: Optional[CodeVectorStore] = None
_graph_store: Optional[Neo4jGraphStore] = None
_last_graph_attempt = 0.0


def get_vector_store() -> CodeVectorStore:
    global _vector_store
    with _vector_lock:
        if _vector_store is None:
            _vector_store = CodeVectorStore()
        return _vector_store


def get_graph_store() -> Neo4jGraphStore:
    """Returns the shared graph store, retrying the connection if Neo4j was down."""
    global _graph_store, _last_graph_attempt
    with _graph_lock:
        now = time.time()
        if _graph_store is None:
            _graph_store = Neo4jGraphStore()
            _last_graph_attempt = now
        elif _graph_store.driver is None and (now - _last_graph_attempt > 10.0):
            _graph_store = Neo4jGraphStore()
            _last_graph_attempt = now
        return _graph_store
