import os
import atexit
from typing import List, Dict, Any, Tuple, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from google import genai

CANDIDATE_EMBED_MODELS = [
    "gemini-embedding-001",
    "text-embedding-004",
    "embedding-001",
]


class CodeVectorStore:
    """Manages vector storage and code embeddings using Qdrant and Google Gemini."""

    def __init__(
        self,
        collection_name: str = "code_chunks",
        qdrant_path: str = "./qdrant_data",
    ):
        self.collection_name = collection_name
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is missing.")

        self.ai_client = genai.Client(api_key=api_key)
        self.qdrant = QdrantClient(path=qdrant_path)
        self.client = self.qdrant

        # Safely register client cleanup on process exit
        atexit.register(self._safe_close)

        self.embedding_model, self.vector_size = self._auto_detect_embedding_model()
        print(f"🎯 Vector Store initialized with model '{self.embedding_model}' ({self.vector_size} dims)")
        self._ensure_collection()

    def _safe_close(self):
        """Safely closes the Qdrant client connection prior to interpreter shutdown."""
        if hasattr(self, "client") and self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass

    def _auto_detect_embedding_model(self) -> Tuple[str, int]:
        """Probes candidate models to select an active embedding model and its vector size."""
        for model_name in CANDIDATE_EMBED_MODELS:
            try:
                response = self.ai_client.models.embed_content(
                    model=model_name,
                    contents="probe",
                )
                vec = []
                if hasattr(response, "embedding") and response.embedding:
                    vec = response.embedding.values
                elif hasattr(response, "embeddings") and response.embeddings:
                    vec = response.embeddings[0].values

                if vec and len(vec) > 0:
                    return model_name, len(vec)
            except Exception:
                continue

        return "gemini-embedding-001", 3072

    def _ensure_collection(self):
        """Creates the Qdrant collection if it does not already exist."""
        if not self.qdrant.collection_exists(self.collection_name):
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    def reset_collection(self):
        """Safely wipes and recreates the Qdrant collection to clear stale vectors."""
        if self.qdrant.collection_exists(self.collection_name):
            self.qdrant.delete_collection(self.collection_name)

        self.qdrant.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
        )
        print(f"🧹 Cleaned stale vector embeddings in Qdrant collection '{self.collection_name}'.")

    def generate_embedding(self, text: str) -> List[float]:
        """Generates a dense vector embedding for a given text snippet using Gemini."""
        if not text or not text.strip():
            return []

        try:
            response = self.ai_client.models.embed_content(
                model=self.embedding_model,
                contents=text,
            )
            if hasattr(response, "embedding") and response.embedding:
                return response.embedding.values
            elif hasattr(response, "embeddings") and response.embeddings:
                return response.embeddings[0].values
            return []
        except Exception as e:
            print(f"❌ Gemini Embedding Error ({self.embedding_model}): {e}")
            return []

    def upsert_code_snippet(self, doc_id: int, code_snippet: str, metadata: Dict[str, Any]) -> bool:
        """Embeds a code snippet and stores it in Qdrant."""
        vector = self.generate_embedding(code_snippet)
        if not vector:
            print(f"   ⚠️ Skipping doc #{doc_id} ('{metadata.get('name', 'unnamed')}'): Embedding failed.")
            return False

        payload = {
            "snippet": code_snippet,
            "code": code_snippet,
            **metadata,
        }

        try:
            point = PointStruct(id=doc_id, vector=vector, payload=payload)
            self.qdrant.upsert(collection_name=self.collection_name, points=[point])
            return True
        except Exception as e:
            print(f"   ❌ Qdrant Upsert Error for doc #{doc_id}: {e}")
            return False

    def search_similar_code(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches Qdrant for code snippets semantically similar to the query."""
        query_vector = self.generate_embedding(query)
        if not query_vector:
            return []

        try:
            response = self.qdrant.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
            )
            return [point.payload for point in response.points]
        except Exception as e:
            print(f"❌ Qdrant Search Error: {e}")
            return []

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Alias interface supporting callers expecting search(query, top_k)."""
        return self.search_similar_code(query=query, limit=top_k)