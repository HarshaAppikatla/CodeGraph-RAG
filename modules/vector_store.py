import os
import sys
import atexit
from typing import List, Dict, Any, Tuple, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


class CodeVectorStore:
    """Manages local vector storage and code embeddings using Qdrant and SentenceTransformers."""

    def __init__(
        self,
        collection_name: str = "code_chunks",
        qdrant_path: str = "./qdrant_data",
        model_name: str = DEFAULT_EMBED_MODEL,
    ):
        self.collection_name = collection_name
        self.qdrant_path = qdrant_path
        self.model_name = model_name

        # 1. Initialize Local SentenceTransformer Model
        self.log(f"🎯 Initializing local embedding model '{self.model_name}'...")
        try:
            self.model = SentenceTransformer(self.model_name)
            self.vector_size = self.model.get_sentence_embedding_dimension()
            self.log(f"✅ Local model loaded successfully ({self.vector_size} dims).")
        except Exception as e:
            self.log(f"❌ Failed to load local model '{self.model_name}': {e}")
            raise e

        # 2. Initialize Qdrant Client
        self.qdrant = QdrantClient(path=self.qdrant_path)
        self.client = self.qdrant

        # Clean client cleanup on process exit
        atexit.register(self._safe_close)

        # 3. Bootstrap Collection
        self._ensure_collection()

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
        except Exception as e:
            self.log(f"❌ Qdrant collection initialization error: {e}")

    def reset_collection(self) -> None:
        """Safely wipes and recreates the Qdrant collection to clear stale vectors."""
        try:
            if self.qdrant.collection_exists(self.collection_name):
                self.qdrant.delete_collection(self.collection_name)
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
            self.log(f"🧹 Cleaned stale vector embeddings in Qdrant collection '{self.collection_name}'.")
        except Exception as e:
            self.log(f"❌ Error resetting collection: {e}")

    def generate_embedding(self, text: str) -> List[float]:
        """Generates a dense vector embedding for a single code snippet using local CPU inference."""
        if not text or not text.strip():
            return []
        try:
            vector = self.model.encode(text, convert_to_numpy=True)
            return vector.tolist()
        except Exception as e:
            self.log(f"❌ Local Embedding Error: {e}")
            return []

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates dense vector embeddings for a list of text snippets in batch."""
        if not texts:
            return []
        try:
            vectors = self.model.encode(texts, convert_to_numpy=True, batch_size=32, show_progress_bar=False)
            return vectors.tolist()
        except Exception as e:
            self.log(f"❌ Batch Local Embedding Error: {e}")
            return []

    def upsert_code_snippet(self, doc_id: int, code_snippet: str, metadata: Dict[str, Any]) -> bool:
        """Embeds a single code snippet and stores it in Qdrant."""
        vector = self.generate_embedding(code_snippet)
        if not vector:
            self.log(
                f"   ⚠️ Skipping doc #{doc_id} ('{metadata.get('filename', metadata.get('name', 'unnamed'))}'): Embedding failed."
            )
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
            self.log(f"   ❌ Qdrant Upsert Error for doc #{doc_id}: {e}")
            return False

    def upsert_code_batch(self, batch_items: List[Dict[str, Any]]) -> int:
        """
        Embeds and upserts a list of documents in batch for maximum throughput.
        Each item dict: {"doc_id": int, "code_snippet": str, "metadata": dict}
        """
        if not batch_items:
            return 0

        valid_items = [item for item in batch_items if item.get("code_snippet") and item["code_snippet"].strip()]
        if not valid_items:
            return 0

        texts = [item["code_snippet"] for item in valid_items]
        vectors = self.generate_embeddings_batch(texts)

        if not vectors or len(vectors) != len(valid_items):
            self.log("❌ Batch embedding size mismatch or failure.")
            return 0

        points = []
        for item, vector in zip(valid_items, vectors):
            payload = {
                "snippet": item["code_snippet"],
                "code": item["code_snippet"],
                "content": item["code_snippet"],
                **item.get("metadata", {}),
            }
            points.append(PointStruct(id=item["doc_id"], vector=vector, payload=payload))

        try:
            self.qdrant.upsert(collection_name=self.collection_name, points=points)
            return len(points)
        except Exception as e:
            self.log(f"❌ Qdrant Batch Upsert Error: {e}")
            return 0

    def search_similar_code(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches Qdrant for code snippets semantically similar to the query."""
        query_vector = self.generate_embedding(query)
        if not query_vector:
            return []

        try:
            if hasattr(self.qdrant, "query_points"):
                response = self.qdrant.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=limit,
                )
                return [point.payload for point in response.points]
            else:
                response = self.qdrant.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=limit,
                )
                return [point.payload for point in response]
        except Exception as e:
            self.log(f"❌ Qdrant Search Error: {e}")
            return []

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Alias interface supporting callers expecting search(query, top_k)."""
        return self.search_similar_code(query=query, limit=top_k)