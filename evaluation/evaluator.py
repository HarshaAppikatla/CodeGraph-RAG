import os
import time
from typing import List, Dict, Any
from google import genai
from google.genai.errors import ServerError, ClientError, APIError
from backend.app.services.agent_workflow import CodeGraphAgent, FALLBACK_MODELS
from backend.app.services.vector_store import CodeVectorStore

class RAGEvaluator:
    """Evaluates CodeGraph-RAG outputs for Faithfulness and Relevancy using Gemini."""

    def __init__(self, agent: CodeGraphAgent):
        self.agent = agent
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")
        self.ai_client = genai.Client(api_key=api_key)

    def evaluate_query(self, query: str) -> Dict[str, Any]:
        """Runs a query through the agent and evaluates the generated response."""
        start_time = time.time()
        agent_response = self.agent.query(query)
        latency = round(time.time() - start_time, 2)

        eval_prompt = f"""You are an automated evaluator for a Code RAG system.
Evaluate the following response based on two criteria:
1. **Faithfulness**: Is the response accurate according to standard Python AST parsing and software architecture concepts?
2. **Relevancy**: Does the response directly address the user query?

=== USER QUERY ===
{query}

=== AGENT RESPONSE ===
{agent_response}

Provide concise evaluation scores (1-5 for Faithfulness, 1-5 for Relevancy) and a 1-sentence justification:"""

        eval_result_text = ""
        for model in FALLBACK_MODELS:
            try:
                eval_result = self.ai_client.models.generate_content(
                    model=model,
                    contents=eval_prompt,
                )
                if eval_result and eval_result.text:
                    eval_result_text = eval_result.text
                    break
            except (ClientError, ServerError, APIError, Exception) as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    time.sleep(2)
                    continue
                break

        return {
            "query": query,
            "response": agent_response,
            "evaluation": eval_result_text,
            "latency_seconds": latency,
        }

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    vector_store = CodeVectorStore()
    agent = CodeGraphAgent(vector_store=vector_store)
    evaluator = RAGEvaluator(agent)

    benchmark_queries = [
        "What classes and methods are defined in backend/app/services/ast_parser.py?",
        "How does Neo4jGraphStore structure relationships between files and functions?",
        "Explain the step-by-step workflow of how CodeGraphAgent handles a user query."
    ]

    print("🧪 Starting CodeGraph-RAG Benchmark Evaluation...\n")
    
    try:
        for idx, test_query in enumerate(benchmark_queries, start=1):
            print(f"================ Query {idx}/{len(benchmark_queries)} ================")
            print(f"❓ Query: '{test_query}'")
            
            metrics = evaluator.evaluate_query(test_query)
            
            print(f"⏱️ Latency: {metrics['latency_seconds']}s")
            print("📊 Evaluation Output:")
            print(metrics['evaluation'])
            print("\n")
    finally:
        # Explicitly close Qdrant and Neo4j connections to eliminate interpreter teardown warnings
        if hasattr(vector_store, "client") and hasattr(vector_store.client, "close"):
            try:
                vector_store.client.close()
            except Exception:
                pass
        agent.close()
