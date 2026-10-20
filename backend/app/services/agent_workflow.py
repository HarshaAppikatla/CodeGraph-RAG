import os
import sys
import re
import time
from typing import Optional, List, Dict, Any
from google import genai
from google.genai.errors import ServerError, ClientError, APIError
from backend.app.services.vector_store import CodeVectorStore
from backend.app.services.graph_store import Neo4jGraphStore

PREFERRED_TEXT_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]
FALLBACK_MODELS = PREFERRED_TEXT_MODELS

EXCLUDED_MODEL_KEYWORDS = [
    "tts", "audio", "embed", "imagen", "vision", "lyria",
    "banana", "image", "customtools", "omni", "deep-research"
]

MAX_CHAT_HISTORY_TURNS = 20


class CodeGraphAgent:
    """Autonomous Agent performing hybrid Retrieval-Augmented Generation with Impact Analysis."""

    def __init__(self, vector_store: Optional[CodeVectorStore] = None):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.ai_client = genai.Client(api_key=api_key)
        self.vector_store = vector_store or CodeVectorStore()

        self.available_models = self._discover_models()
        self.active_model_idx = 0

        self.chat_history: List[Dict[str, str]] = []

        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "neo4j"))
        neo4j_pass = os.getenv("NEO4J_PASSWORD")
        self.graph_store = None

        if neo4j_uri and neo4j_pass:
            try:
                self.graph_store = Neo4jGraphStore(neo4j_uri, neo4j_user, neo4j_pass)
            except Exception as e:
                self.log(f"⚠️ Warning: Failed to connect to Neo4j Graph Store: {e}")

    def log(self, message: str) -> None:
        """Logs strictly to sys.stderr to avoid stdio protocol corruption."""
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()

    def _discover_models(self) -> List[str]:
        """Queries GenAI API at startup and filters out non-text or preview experimental models."""
        discovered = []
        try:
            for m in self.ai_client.models.list():
                name = m.name.replace("models/", "") if hasattr(m, "name") else str(m)
                name_lower = name.lower()

                supports_generate = True
                if hasattr(m, "supported_generation_methods") and m.supported_generation_methods:
                    supports_generate = "generateContent" in m.supported_generation_methods

                if supports_generate and any(k in name_lower for k in ["flash", "pro"]):
                    if not any(ex in name_lower for ex in EXCLUDED_MODEL_KEYWORDS):
                        discovered.append(name)
        except Exception as e:
            self.log(f"⚠️ Model discovery note: {e}")

        combined = []
        for pref in PREFERRED_TEXT_MODELS:
            if pref not in combined:
                combined.append(pref)

        for d in discovered:
            if d not in combined:
                combined.append(d)

        self.log(f"🔍 Initialized models for API Key: {combined[:4]}")
        return combined if combined else PREFERRED_TEXT_MODELS

    def _append_chat_history(self, user: str, agent: str):
        """Appends turn to history while capping total stored length to prevent memory growth."""
        self.chat_history.append({"user": user, "agent": agent})
        if len(self.chat_history) > MAX_CHAT_HISTORY_TURNS:
            self.chat_history = self.chat_history[-MAX_CHAT_HISTORY_TURNS:]

    def _detect_impact_query_symbol(self, query: str) -> Optional[str]:
        """Identifies target symbols if user is asking about code impact, changes, or breakages."""
        impact_keywords = ["break", "impact", "change", "modify", "affect", "depend", "caller", "refactor"]
        if not any(kw in query.lower() for kw in impact_keywords):
            return None

        tokens = re.findall(r"[A-Za-z0-9_\.]+", query)
        ignore_words = {
            "change", "signature", "process", "break", "what", "which", "will",
            "files", "methods", "if", "modify", "impact", "for", "while", "class",
            "def", "function", "code", "every", "file", "fails", "get"
        }
        candidates = [t for t in tokens if len(t) > 2 and t.lower() not in ignore_words]

        return candidates[0] if candidates else None

    def query(self, user_query: str) -> str:
        """Executes hybrid retrieval (Vector + Graph Impact Analysis) and generates response."""
        raw_vector_results = self.vector_store.search_similar_code(user_query, limit=7)
        context_blocks = []

        if isinstance(raw_vector_results, list):
            for res in raw_vector_results:
                if not isinstance(res, dict):
                    continue

                fn_name = res.get("name")
                file_name = res.get("file", "Unknown")
                code_text = res.get("snippet") or res.get("code") or ""
                docstring = res.get("docstring", "")

                if not code_text and not fn_name:
                    continue

                context_str = f"--- [Vector Match: {file_name} | Entity: {fn_name or 'Snippet'}] ---\n"
                if docstring:
                    context_str += f"Docstring: {docstring}\n"
                if code_text:
                    context_str += f"Code:\n{code_text}\n"

                context_blocks.append(context_str)

        target_symbol = self._detect_impact_query_symbol(user_query)
        if target_symbol and self.graph_store:
            impact_data = self.graph_store.analyze_impact(target_symbol)
            if isinstance(impact_data, dict) and impact_data.get("impact_found"):
                impact_summary = (
                    f"\n=== NEO4J GRAPH IMPACT ANALYSIS FOR '{target_symbol}' ===\n"
                    f"Target Node: {impact_data.get('target_symbol', target_symbol)} (Types: {impact_data.get('symbol_type', [])})\n"
                    f"Defined In: {impact_data.get('defined_in_file', 'Unknown')}\n"
                    f"Direct & Transitive Callers (Would Break/Require Refactoring): {impact_data.get('affected_callers') or 'None'}\n"
                    f"Affected Subclasses/Inheritance: {impact_data.get('affected_subclasses') or 'None'}\n"
                )
                context_blocks.insert(0, impact_summary)

        full_context = "\n\n".join(context_blocks) if context_blocks else "No relevant code snippets retrieved."

        history_str = ""
        if self.chat_history:
            history_str = "=== PREVIOUS CONVERSATION HISTORY ===\n"
            for turn in self.chat_history[-3:]:
                if isinstance(turn, dict):
                    u_turn = turn.get("user", "")
                    a_turn = turn.get("agent", "")
                    history_str += f"User: {u_turn}\nAgent: {a_turn}\n\n"

        prompt = f"""You are an expert Codebase Intelligence Agent.

{history_str}=== RETRIEVED HYBRID CONTEXT ===
{full_context}

=== USER QUERY ===
{user_query}

INSTRUCTIONS:
1. Use PREVIOUS CONVERSATION HISTORY to maintain context for short follow-ups or language shifts.
2. If the user query asks about impact, refactoring, or what would break if a function/class changes, explicitly list the affected callers, subclasses, and files identified in the GRAPH IMPACT ANALYSIS.
3. If the user query is a greeting, casual remark, or non-technical question, respond naturally and concisely without explaining code.
4. Answer accurately using the retrieved code snippets and knowledge graph metadata above.
"""

        total_models = len(self.available_models)
        for offset in range(total_models):
            current_idx = (self.active_model_idx + offset) % total_models
            model = self.available_models[current_idx]

            for attempt in range(3):
                try:
                    response = self.ai_client.models.generate_content(
                        model=model,
                        contents=prompt,
                    )
                    if response and getattr(response, "text", None):
                        self.active_model_idx = current_idx
                        answer = response.text
                        self._append_chat_history(user_query, answer)
                        return answer
                except (ClientError, ServerError, APIError, Exception) as e:
                    error_msg = str(e)

                    if "503" in error_msg or "UNAVAILABLE" in error_msg:
                        self.log(f"⚠️ Model '{model}' server busy (503). Retrying attempt {attempt+1}/3 in 2s...")
                        time.sleep(2)
                        continue

                    elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        self.log(f"⚠️ Quota exhausted for model '{model}'. Waiting 3s before switching...")
                        time.sleep(3)
                        break

                    elif any(err in error_msg for err in ["400", "404", "NOT_FOUND", "INVALID_ARGUMENT"]) or "deprecated" in error_msg.lower():
                        break

                    elif attempt < 2:
                        time.sleep(2)
                    else:
                        self.log(f"⚠️ Model '{model}' failed ({e}). Switching...")

        return "⚠️ All configured Gemini models are currently experiencing high demand or rate limits. Please try again in a few moments."

    def close(self):
        """Cleanup agent store handles."""
        if self.graph_store:
            try:
                self.graph_store.close()
            except Exception:
                pass
