import os
import time
from typing import Optional, List, Dict
from google import genai
from google.genai.errors import ServerError, ClientError, APIError
from modules.vector_store import CodeVectorStore
from modules.graph_store import Neo4jGraphStore

# Active Gemini text generation models matching dashboard quotas
FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite"
]

class CodeGraphAgent:
    """Autonomous Agent that performs hybrid Retrieval-Augmented Generation 
    combining Qdrant vector search, Neo4j graph dependency expansion, and multi-turn chat memory."""

    def __init__(self, vector_store: Optional[CodeVectorStore] = None):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.ai_client = genai.Client(api_key=api_key)
        self.vector_store = vector_store or CodeVectorStore()

        # Cache working model index across queries
        self.active_model_idx = 0

        # Conversation history store for multi-turn context awareness
        self.chat_history: List[Dict[str, str]] = []

        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
        neo4j_pass = os.getenv("NEO4J_PASSWORD")

        self.graph_store = None
        if neo4j_uri and neo4j_pass:
            try:
                self.graph_store = Neo4jGraphStore(neo4j_uri, neo4j_user, neo4j_pass)
            except Exception as e:
                print(f"⚠️ Warning: Failed to connect to Neo4j Graph Store: {e}")

    def query(self, user_query: str) -> str:
        """Executes hybrid retrieval (Vector + Graph) and synthesizes an answer using chat history."""
        # 1. Semantic Search via Qdrant (retrieving top 4 for broader architectural coverage)
        vector_results = self.vector_store.search_similar_code(user_query, limit=4)

        context_blocks = []
        for res in vector_results:
            fn_name = res.get("name")
            code_text = res.get("code", "")
            file_name = res.get("file", "Unknown")

            context_str = f"--- [Vector Match in {file_name}] ---\n{code_text}\n"

            # 2. Graph Traversal via Neo4j
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

        full_context = "\n".join(context_blocks) if context_blocks else "No relevant code snippets retrieved."

        # Format recent conversation history (last 3 interactions)
        history_str = ""
        if self.chat_history:
            history_str = "=== PREVIOUS CONVERSATION HISTORY ===\n"
            for turn in self.chat_history[-3:]:
                history_str += f"User: {turn['user']}\nAgent: {turn['agent']}\n\n"

        # 3. Prompt Construction with Memory & Adaptive Instructions
        prompt = f"""You are an expert Codebase Intelligence Agent.

{history_str}=== RETRIEVED HYBRID CONTEXT ===
{full_context}

=== USER QUERY ===
{user_query}

INSTRUCTIONS:
1. Use the PREVIOUS CONVERSATION HISTORY to maintain context for short follow-ups (e.g., "some other features", "explain more", "what else"). Avoid repeating details already discussed.
2. If the user query is a greeting, casual remark, or non-technical question, respond naturally and concisely without explaining code.
3. If the user query is technical or asks about the codebase, answer accurately using the retrieved code snippets and knowledge graph metadata above.
"""

        # 4. Rotated Model Execution Starting from Last Known Working Model
        total_models = len(FALLBACK_MODELS)

        for offset in range(total_models):
            current_idx = (self.active_model_idx + offset) % total_models
            model = FALLBACK_MODELS[current_idx]

            for attempt in range(2):
                try:
                    response = self.ai_client.models.generate_content(
                        model=model,
                        contents=prompt,
                    )
                    if response and response.text:
                        # Save working model index and append turn to chat history
                        self.active_model_idx = current_idx
                        answer = response.text
                        self.chat_history.append({"user": user_query, "agent": answer})
                        return answer
                except (ClientError, ServerError, APIError, Exception) as e:
                    error_msg = str(e)

                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        print(f"⚠️ Quota exhausted for model '{model}'. Waiting 3s before switching...")
                        time.sleep(3)
                        break
                    elif "404" in error_msg or "NOT_FOUND" in error_msg or "deprecated" in error_msg.lower():
                        print(f"⚠️ Model '{model}' not found or deprecated. Switching...")
                        break
                    elif attempt == 0:
                        time.sleep(2)
                    else:
                        print(f"⚠️ Model '{model}' failed ({e}). Switching...")

        raise RuntimeError("All configured Gemini models have exceeded their limits or are unavailable.")

    def close(self):
        if self.graph_store:
            self.graph_store.close()