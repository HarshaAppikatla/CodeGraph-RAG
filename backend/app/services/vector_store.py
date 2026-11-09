import os
import sys
import atexit
from typing import List, Dict, Any, Tuple, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue,
    HnswConfigDiff, OptimizersConfigDiff, SearchParams
)
from backend.app.config import settings

DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_GEMINI_EMBED_MODEL = "text-embedding-004"
DEFAULT_GEMINI_DIMENSION = 3072


class CodeVectorStore:
    """Manages vector storage and code embeddings using Qdrant with local FastEmbed/SentenceTransformers (384D) or Google Gemini embeddings (3072D)."""

    def __init__(
        self,
        collection_name: str = "code_chunks",
        qdrant_path: str = "./qdrant_data",
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        vector_size: Optional[int] = None,
    ):
        self.collection_name = collection_name
        self.qdrant_path = qdrant_path

        env_provider = os.getenv("EMBEDDING_PROVIDER", "").strip().lower()
        chosen_provider = (provider or env_provider or "").lower()

        if chosen_provider == "gemini" or (model_name and ("gemini" in model_name.lower() or "text-embedding" in model_name.lower())):
            self.provider = "gemini"
            self.model_name = model_name or os.getenv("GEMINI_EMBEDDING_MODEL") or DEFAULT_GEMINI_EMBED_MODEL
            self.vector_size = vector_size or int(os.getenv("GEMINI_EMBEDDING_DIMENSION", str(DEFAULT_GEMINI_DIMENSION)))
        else:
            self.provider = "local"
            self.model_name = model_name or os.getenv("EMBEDDING_MODEL") or DEFAULT_EMBED_MODEL
            self.vector_size = vector_size or 384

        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
        self._gemini_client = None
        self._model = None
        # Tracks whether at least one real (non-zero) embedding was produced during this session.
        # Remains False until generate_embeddings_batch successfully returns non-zero vectors.
        self._embedding_ok: bool = False

        if self.provider == "gemini":
            self._init_gemini_client()

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
    def embedding_ok(self) -> bool:
        """Returns True when the embedding model loaded successfully and produced real vectors."""
        return self._embedding_ok

    def _init_gemini_client(self) -> None:
        """Initializes Google GenAI client for cloud embeddings."""
        key = self.gemini_api_key or os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
        if key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=key)
                self.log(
                    f"✅ Initialized Google GenAI embedding client "
                    f"(model: '{self.model_name}', dims: {self.vector_size})."
                )
            except Exception as e:
                self.log(f"⚠️ Failed to initialize Google GenAI embedding client: {e}")
                self._gemini_client = None
        else:
            self.log("⚠️ No GEMINI_API_KEY available for Gemini embeddings.")

    @property
    def model(self):
        """Lazy loads lightweight FastEmbed (ONNX) or falls back to SentenceTransformer."""
        if self._model is None:
            # 1. Try FastEmbed (Lightweight ONNX CPU, constrained to 1 thread to avoid memory spikes)
            try:
                import os
                os.environ["OMP_NUM_THREADS"] = "1"
                os.environ["MKL_NUM_THREADS"] = "1"
                from fastembed import TextEmbedding
                self.log(f"🎯 Loading lightweight FastEmbed model '{self.model_name}'...")
                cache_dir = os.getenv("FASTEMBED_CACHE_PATH", None)
                self._model = TextEmbedding(
                    model_name=self.model_name,
                    cache_dir=cache_dir,
                    threads=1,
                    lazy_load=True,
                    enable_cpu_mem_arena=False,
                )
                self.vector_size = 384
                self.log("✅ FastEmbed ONNX model ready (constrained to 1 thread & low memory).")
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
                    hnsw_config=HnswConfigDiff(
                        m=16,
                        ef_construct=100,
                        full_scan_threshold=100,
                        payload_m=16,
                    ),
                    optimizers_config=OptimizersConfigDiff(
                        indexing_threshold=100,
                    ),
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
                hnsw_config=HnswConfigDiff(
                    m=16,
                    ef_construct=100,
                    full_scan_threshold=100,
                    payload_m=16,
                ),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=100,
                ),
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
        """Generates a dense vector embedding using Gemini (cloud) or FastEmbed / SentenceTransformer (local).

        Returns an empty list when the text is empty or the model fails to load,
        preventing zero-vectors from being stored or searched.
        """
        if not text or not text.strip():
            return []

        if self.provider == "gemini":
            if not self._gemini_client:
                self._init_gemini_client()
            if not self._gemini_client:
                return []
            try:
                from google.genai import types
                config = types.EmbedContentConfig(output_dimensionality=self.vector_size)
                response = self._gemini_client.models.embed_content(
                    model=self.model_name,
                    contents=text,
                    config=config,
                )
                if response and response.embeddings:
                    vec = response.embeddings[0].values
                    if vec and not all(v == 0.0 for v in vec):
                        self._embedding_ok = True
                        return list(vec)
                return []
            except Exception as e:
                self.log(f"⚠️ Gemini embedding generation error: {e}")
                return []

        embedder = self.model
        if not embedder:
            return []
        try:
            if hasattr(embedder, "embed"):
                vectors = list(embedder.embed([text]))
                if vectors:
                    vec = vectors[0].tolist()
                    if not all(v == 0.0 for v in vec):
                        self._embedding_ok = True
                    return vec
                return []
            else:
                vector = embedder.encode(text, convert_to_numpy=True)
                vec = vector.tolist()
                if not all(v == 0.0 for v in vec):
                    self._embedding_ok = True
                return vec
        except Exception as e:
            self.log(f"⚠️ Embedding generation error: {e}")
            return []

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates dense vector embeddings for a list of text snippets in batch.

        Returns an empty list when the embedding model is unavailable so callers
        can distinguish a model failure from a legitimately-empty input list and
        avoid storing zero-vectors that would pollute search results.
        """
        if not texts:
            return []

        if self.provider == "gemini":
            if not self._gemini_client:
                self._init_gemini_client()
            if not self._gemini_client:
                self.log("⚠️ Gemini client unavailable; skipping batch (zero vectors will NOT be stored).")
                return []
            try:
                from google.genai import types
                config = types.EmbedContentConfig(output_dimensionality=self.vector_size)
                response = self._gemini_client.models.embed_content(
                    model=self.model_name,
                    contents=texts,
                    config=config,
                )
                if response and response.embeddings:
                    result = [list(emb.values) for emb in response.embeddings]
                    if result and any(not all(v == 0.0 for v in vec) for vec in result):
                        self._embedding_ok = True
                    return result
                return []
            except Exception as e:
                self.log(f"⚠️ Gemini batch embedding generation error: {e}")
                return []

        embedder = self.model
        if not embedder:
            # Model failed to load — signal failure to callers rather than storing zero-vectors
            self.log("⚠️ Embedding model unavailable; skipping batch (zero vectors will NOT be stored).")
            return []
        try:
            if hasattr(embedder, "embed"):
                vectors = list(embedder.embed(texts, batch_size=4))
                result = [v.tolist() for v in vectors]
            else:
                vectors = embedder.encode(texts, convert_to_numpy=True, batch_size=4, show_progress_bar=False)
                result = vectors.tolist()
            # Mark that we produced real embeddings at least once this session
            if result and any(not all(v == 0.0 for v in vec) for vec in result):
                self._embedding_ok = True
            return result
        except Exception as e:
            self.log(f"⚠️ Batch embedding generation error: {e}")
            return []
        finally:
            import gc
            gc.collect()

    def upsert_code_snippet(self, doc_id: int, code_snippet: str, metadata: Dict[str, Any]) -> bool:
        """Embeds a single code snippet and stores it in Qdrant."""
        vector = self.generate_embedding(code_snippet)
        if not vector or all(v == 0.0 for v in vector):
            return False

        payload = {
            "snippet": code_snippet,
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
        chunk_size = 12
        for i in range(0, len(valid_items), chunk_size):
            chunk_items = valid_items[i:i + chunk_size]
            texts = [item["code_snippet"] for item in chunk_items]
            try:
                vectors = self.generate_embeddings_batch(texts)
                if not vectors or len(vectors) != len(chunk_items):
                    continue

                # Never store zero vectors into Qdrant
                if any(all(v == 0.0 for v in vec) for vec in vectors):
                    self.log(f"⚠️ Zero-vectors detected in batch chunk {i}; skipping upsert.")
                    continue

                points = []
                for item, vector in zip(chunk_items, vectors):
                    payload = {
                        "snippet": item["code_snippet"],
                        **item.get("metadata", {}),
                    }
                    points.append(PointStruct(id=item["doc_id"], vector=vector, payload=payload))

                self.qdrant.upsert(collection_name=self.collection_name, points=points)
                total_upserted += len(points)
                del points
                del vectors
            except Exception as e:
                self.log(f"⚠️ Vector batch upsert notice (chunk {i}): {e}")
            finally:
                import gc
                gc.collect()

        return total_upserted

    def search_similar_code(
        self, query: str, limit: int = 5, workspace_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Searches Qdrant for code snippets semantically similar to the query.

        When workspace_id is given, only chunks indexed for that workspace are returned.
        Uses HNSW graph traversal instead of brute-force scan.
        """
        query_vector = self.generate_embedding(query)
        if not query_vector or all(v == 0.0 for v in query_vector):
            return []

        # Always apply the workspace filter to guarantee tenant isolation and prevent cross-workspace leaks
        clean_ws = str(workspace_id).strip() if workspace_id else ""
        query_filter = Filter(
            must=[FieldCondition(key="workspace_id", match=MatchValue(value=clean_ws))]
        )
        search_params = SearchParams(hnsw_ef=64, exact=False)

        try:
            if hasattr(self.qdrant, "query_points"):
                response = self.qdrant.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    search_params=search_params,
                    limit=limit,
                )
                points = response.points
            else:
                response = self.qdrant.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    search_params=search_params,
                    limit=limit,
                )
                points = response

            results = []
            for point in points:
                payload = dict(getattr(point, "payload", {}) or {})
                payload["score"] = getattr(point, "score", 0.0)
                # Populate backward-compatibility aliases in memory without duplicating in storage
                snippet_text = payload.get("snippet") or payload.get("code") or payload.get("content") or ""
                payload["snippet"] = snippet_text
                payload["code"] = snippet_text
                payload["content"] = snippet_text
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

    def count_workspace_vectors(self, workspace_id: str) -> int:
        """Returns the number of vector points stored in Qdrant for this workspace."""
        if not workspace_id:
            return 0
        try:
            flt = Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(value=str(workspace_id).strip()))])
            res = self.qdrant.count(collection_name=self.collection_name, count_filter=flt, exact=True)
            return getattr(res, "count", 0)
        except Exception as e:
            self.log(f"⚠️ Vector count check error for {workspace_id}: {e}")
            return 0

    def delete_workspace(self, workspace_id: str) -> bool:
        """Deletes all vector embeddings associated with a workspace from Qdrant."""
        if not workspace_id:
            return False
        try:
            flt = Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id))])
            self.qdrant.delete(
                collection_name=self.collection_name,
                points_selector=flt,
            )
            self.log(f"🗑️ Deleted Qdrant points for workspace '{workspace_id}'")
            return True
        except Exception as e:
            self.log(f"⚠️ Failed to delete Qdrant points for workspace '{workspace_id}': {e}")
            raise
