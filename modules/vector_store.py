import os
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from google import genai

class CodeVectorStore:
    """Handles code embeddings and vector storage using Gemini & Qdrant."""

    def __init__(self, collection_name: str = "code_chunks"):
        self.collection_name = collection_name
        
        # Initialize Gemini client for embeddings
        api_key = os.getenv("GEMINI_API_KEY")
        self.ai_client = genai.Client(api_key=api_key)

        # Initialize Qdrant Client (Uses local disk storage inside Codespaces)
        self.qdrant = QdrantClient(path="./qdrant_data")

        # Create Qdrant collection if it doesn't exist (3072 dimensions for gemini-embedding-001)
        if not self.qdrant.collection_exists(self.collection_name):
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
            )

    def generate_embedding(self, text: str) -> List[float]:
        """Generates a vector embedding for a given code snippet using Gemini."""
        response = self.ai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
        )
        return response.embeddings[0].values

    def upsert_code_snippet(self, doc_id: int, code_snippet: str, metadata: Dict[str, Any]):
        """Embeds a code snippet and stores it in Qdrant."""
        vector = self.generate_embedding(code_snippet)
        
        point = PointStruct(
            id=doc_id,
            vector=vector,
            payload={
                "code": code_snippet,
                **metadata
            }
        )
        self.qdrant.upsert(collection_name=self.collection_name, points=[point])

    def search_similar_code(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Searches Qdrant for code snippets semantically similar to the query."""
        query_vector = self.generate_embedding(query)
        response = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
        )
        return [point.payload for point in response.points]