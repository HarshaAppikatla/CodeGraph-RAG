import os
import time
from typing import Optional
from google import genai
from google.genai.errors import ServerError, ClientError, APIError
from modules.vector_store import CodeVectorStore
from modules.graph_store import Neo4jGraphStore

# Active Gemini models with separate free-tier quota pools
FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro"
]

class CodeGraphAgent:
    """Autonomous Agent that performs hybrid Retrieval-Augmented Generation 
    combining Qdrant vector search and Neo4j graph dependency expansion."""

    def __init__(self, vector_store: Optional[CodeVectorStore] = None):
        api_key = os.getenv("GEMINI_API_KEY")
        self.ai_client = genai.Client(api_key=api_key)
        self.vector_store = vector_store or CodeVectorStore()
        
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
        neo4j_pass = os.getenv("NEO4J_PASSWORD")
        
        self.graph_store = None
        if neo4j_uri and neo4j_pass:
            self.graph_store = Neo4jGraphStore(neo4j_uri, neo4j_user, neo4j_pass)

    def query(self, user_query: str) -> str:
        """Executes hybrid retrieval (Vector + Graph) and synthesizes answer."""
        # 1. Semantic Search via Qdrant
        vector_results = self.vector_store.search_similar_code(user_query, limit=2)
        
        context_blocks = []
        for res in vector_results:
            fn_name = res.get("name")
            code_text = res.get("code")
            file_name = res.get("file")
            
            context_str = f"--- [Vector Match in {file_name}] ---\n{code_text}\n"
            
            # 2. Graph Traversal via Neo4j for structural context
            if self.graph_store and fn_name:
                cypher = """
                MATCH (f:File)-[:DEFINES_FUNCTION]->(fn:Function {name: $fn_name})
                RETURN f.path AS file_path
                """
                try:
                    with self.graph_store.driver.session() as session:
                        result = session.run(cypher, fn_name=fn_name)
                        records = list(result)
                        if records:
                            context_str += f"[Graph Knowledge]: Function '{fn_name}' belongs to module '{records[0]['file_path']}'\n"
                except Exception as e:
                    context_str += f"[Graph Query Note]: {e}\n"
                    
            context_blocks.append(context_str)

        full_context = "\n".join(context_blocks)
        
        # 3. Prompt Construction
        prompt = f"""You are an expert Codebase Intelligence Agent.
Answer the user query accurately using the retrieved code snippets and knowledge graph metadata below.

=== RETRIEVED HYBRID CONTEXT ===
{full_context}

=== USER QUERY ===
{user_query}

Provide a clear, technical answer explaining the code structure and functionality:"""

        # 4. LLM Generation with Dynamic Model Rotation
        for model in FALLBACK_MODELS:
            for attempt in range(2):
                try:
                    response = self.ai_client.models.generate_content(
                        model=model,
                        contents=prompt,
                    )
                    return response.text
                except (ClientError, ServerError, APIError) as e:
                    error_msg = str(e)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        print(f"⚠️ Quota exhausted for model '{model}'. Switching to next available model...")
                        break  # Jump to next model in list
                    elif "404" in error_msg or "NOT_FOUND" in error_msg:
                        print(f"⚠️ Model '{model}' not found or deprecated. Switching...")
                        break
                    elif attempt == 0:
                        time.sleep(2)
                    else:
                        print(f"⚠️ Model '{model}' failed ({e}). Fallback triggered...")

        raise RuntimeError("All configured Gemini models have exceeded their limits or are unavailable.")

    def close(self):
        if self.graph_store:
            self.graph_store.close()