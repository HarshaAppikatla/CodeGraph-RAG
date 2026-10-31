import os
import sys
import atexit
from typing import List, Dict, Any, Tuple, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from backend.app.config import settings

DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


class CodeVectorStore:
    """Manages vector storage and code embeddings using Qdrant and SentenceTransformers."""

    def __init__(
        self,
        collection_name: str = "code_chunks",
        qdrant_path: str = "./qdrant_data",
        model_name: str = DEFAULT_EMBED_MODEL,
    ):
        self.collection_name = collection_name
        self.qdrant_path = qdrant_path
        self.model_name = model_name
        self.vector_size = 384
        self._model = None

        # 1. Initialize Qdrant Client (Cloud or local embedded storage)
        qdrant_host = os.getenv("QDRANT_HOST") or getattr(settings, "QDRANT_HOST", None)
        qdrant_api_key = os.getenv("QDRANT_API_KEY") or getattr(settings, "QDRANT_API_KEY", None)

        if qdrant_host and qdrant_host.startswith("http"):
            # Qdrant Cloud Instance
            self.log(f"☁️ Connecting to Qdrant Cloud at {qdrant_host}...")
            try:
                self.qdrant = QdrantClient(
                    url=qdrant_host,
                    api_key=qdrant_api_key if qdrant_api_key else None,
                    timeout=10.0,
                )
                self.log("✅ Qdrant Cloud connected successfully.")
            except Exception as e:
                self.log(f"⚠️ Failed connecting to Qdrant Cloud ({e}), trying memory client...")
                self.qdrant = QdrantClient(":memory:")
        else:
            # Local Embedded Persistent Storage
            local_path = os.getenv("QDRANT_PATH", self.qdrant_path)
            try:
                self.qdrant = QdrantClient(path=local_path)
            except Exception as e:
                self.log(f"⚠️ Notice on local Qdrant file store ({e}), trying memory client...")
                self.qdrant = QdrantClient(":memory:")

        self.client = self.qdrant
        atexit.register(self._safe_close)

        # 2. Bootstrap Collection
        self._ensure_collection()

    @property
    def model(self):
        """Lazy loads lightweight FastEmbed (ONNX) or falls back to SentenceTransformer."""
        if self._model is None:
            # 1. Try FastEmbed (Lightweight ONNX CPU, ~60MB RAM)
            try:
                from fastembed import TextEmbedding
                self.log(f"🎯 Loading lightweight FastEmbed model '{self.model_name}'...")
                self._model = TextEmbedding(model_name=self.model_name)
                self.vector_size = 384
                self.log("✅ FastEmbed ONNX model ready (~60MB RAM).")
                return self._model
            except Exception as fe_err:
                self.log(f"⚠️ FastEmbed notice: {fe_err}. Trying SentenceTransformer fallback...")

            # 2. Fallback to SentenceTransformer
            try:
                import torch
                torch.set_num_threads(1)
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                self.vector_size = self._model.get_sentence_embedding_dimension()
                self.log(f"✅ SentenceTransformer model loaded ({self.vector_size} dims).")
            except Exception as e:
                self.log(f"⚠️ Failed to load embedding model '{self.model_name}': {e}")
                self._model = None
        return self._model

    def log(self, message: str) -> None:
        """Logs messages to sys.stderr to preserve stdout for MCP JSON-RPC protocol messages."""
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()

    def _safe_close(self) -> None:
        """Safely closes the Qdrant client connection prior to interpreter shutdown."""
        if hasattr(self, "client") and self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass

    def _ensure_collection(self) -> None:
        """Creates or recreates the Qdrant collection if missing or dimension mismatched."""
        try:
            if self.qdrant.collection_exists(self.collection_name):
                info = self.qdrant.get_collection(self.collection_name)
                existing_dim = info.config.params.vectors.size
                if existing_dim != self.vector_size:
                    self.log(
                        f"⚠️ Vector dimension mismatch ({existing_dim} vs {self.vector_size}). "
                        f"Recreating collection '{self.collection_name}'..."
                    )
                    self.reset_collection()
            else:
                self.qdrant.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
                )
            try:
                self.qdrant.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="workspace_id",
                    field_schema="keyword",
                )
            except Exception:
                pass
        except Exception as e:
            self.log(f"⚠️ Qdrant collection initialization notice: {e}")

    def reset_collection(self) -> None:
        """Safely wipes and recreates the Qdrant collection to clear stale vectors."""
        try:
            if self.qdrant.collection_exists(self.collection_name):
                self.qdrant.delete_collection(self.collection_name)
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
            try:
                self.qdrant.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="workspace_id",
                    field_schema="keyword",
                )
            except Exception:
                pass
            self.log(f"🧹 Cleaned stale vector embeddings in Qdrant collection '{self.collection_name}'.")
        except Exception as e:
            self.log(f"⚠️ Error resetting collection: {e}")

    def generate_embedding(self, text: str) -> List[float]:
        """Generates a dense vector embedding using FastEmbed (or SentenceTransformer)."""
        if not text or not text.strip():
            return [0.0] * self.vector_size
        embedder = self.model
        if not embedder:
            return [0.0] * self.vector_size
        try:
            if hasattr(embedder, "embed"):
                vectors = list(embedder.embed([text]))
                return vectors[0].tolist() if vectors else [0.0] * self.vector_size
            else:
                vector = embedder.encode(text, convert_to_numpy=True)
                return vector.tolist()
        except Exception as e:
            self.log(f"⚠️ Embedding generation error: {e}")
            return [0.0] * self.vector_size

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates dense vector embeddings for a list of text snippets in batch."""
        if not texts:
            return []
        embedder = self.model
        if not embedder:
            return [[0.0] * self.vector_size for _ in texts]
        try:
            if hasattr(embedder, "embed"):
                vectors = list(embedder.embed(texts, batch_size=32))
                return [v.tolist() for v in vectors]
            else:
                vectors = embedder.encode(texts, convert_to_numpy=True, batch_size=32, show_progress_bar=False)
                return vectors.tolist()
        except Exception as e:
            self.log(f"⚠️ Batch embedding generation error: {e}")
            return [[0.0] * self.vector_size for _ in texts]

    def upsert_code_snippet(self, doc_id: int, code_snippet: str, metadata: Dict[str, Any]) -> bool:
        """Embeds a single code snippet and stores it in Qdrant."""
        vector = self.generate_embedding(code_snippet)
        if not vector:
            return False

        payload = {
            "snippet": code_snippet,
            "code": code_snippet,
            "content": code_snippet,
            **metadata,
        }

        try:
            point = PointStruct(id=doc_id, vector=vector, payload=payload)
            self.qdrant.upsert(collection_name=self.collection_name, points=[point])
            return True
        except Exception as e:
            self.log(f"   ⚠️ Qdrant Upsert Notice for doc #{doc_id}: {e}")
            return False

    def upsert_code_batch(self, batch_items: List[Dict[str, Any]]) -> int:
        """
        Embeds and upserts a list of documents in memory-capped micro-batches for high reliability on constrained environments.
        Each item dict: {"doc_id": int, "code_snippet": str, "metadata": dict}
        """
        if not batch_items:
            return 0

        valid_items = [item for item in batch_items if item.get("code_snippet") and item["code_snippet"].strip()]
        if not valid_items:
            return 0

        total_upserted = 0
        chunk_size = 16
        for i in range(0, len(valid_items), chunk_size):
            chunk_items = valid_items[i:i + chunk_size]
            texts = [item["code_snippet"] for item in chunk_items]
            try:
                vectors = self.generate_embeddings_batch(texts)
                if not vectors or len(vectors) != len(chunk_items):
                    continue

                points = []
                for item, vector in zip(chunk_items, vectors):
                    payload = {
                        "snippet": item["code_snippet"],
                        "code": item["code_snippet"],
                        "content": item["code_snippet"],
                        **item.get("metadata", {}),
                    }
                    points.append(PointStruct(id=item["doc_id"], vector=vector, payload=payload))

                self.qdrant.upsert(collection_name=self.collection_name, points=points)
                total_upserted += len(points)
            except Exception as e:
                self.log(f"⚠️ Vector batch upsert notice (chunk {i}): {e}")

        return total_upserted

    def search_similar_code(
        self, query: str, limit: int = 5, workspace_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Searches Qdrant for code snippets semantically similar to the query.

        When workspace_id is given, only chunks indexed for that workspace are returned.
        """
        query_vector = self.generate_embedding(query)
        if not query_vector:
            return []

        query_filter = None
        if workspace_id:
            query_filter = Filter(
                must=[FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id))]
            )

        try:
            if hasattr(self.qdrant, "query_points"):
                response = self.qdrant.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                )
                points = response.points
            else:
                response = self.qdrant.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                )
                points = response

            results = []
            for point in points:
                payload = dict(getattr(point, "payload", {}) or {})
                payload["score"] = getattr(point, "score", 0.0)
                results.append(payload)
            return results
        except Exception as e:
            self.log(f"⚠️ Qdrant Search Notice: {e}")
            return []

    def search(self, query: str, top_k: int = 5, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alias interface supporting callers expecting search(query, top_k)."""
        return self.search_similar_code(query=query, limit=top_k, workspace_id=workspace_id)

    def list_symbols(self, workspace_id: str, limit: int = 300) -> List[Dict[str, str]]:
        """Distinct class/function names indexed for one workspace, with their file."""
        flt = Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id))])
        seen: Dict[str, str] = {}
        offset = None
        try:
            while True:
                points, offset = self.qdrant.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=flt,
                    limit=256,
                    offset=offset,
                    with_payload=["filepath", "symbols"],
                    with_vectors=False,
                )
                for point in points:
                    payload = point.payload or {}
                    for name in payload.get("symbols", []):
                        seen.setdefault(name, payload.get("filepath", ""))
                if offset is None:
                    break
        except Exception as e:
            self.log(f"⚠️ Qdrant symbol listing notice: {e}")
        return [{"name": n, "file": f} for n, f in sorted(seen.items())][:limit]
