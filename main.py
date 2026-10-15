import os
import glob
import sys
from dotenv import load_dotenv
from modules.ast_parser import CodeASTParser
from modules.graph_store import Neo4jGraphStore
from modules.vector_store import CodeVectorStore
from modules.agent_workflow import CodeGraphAgent

load_dotenv()

def ingest_codebase(vector_store: CodeVectorStore):
    """Parses all Python modules and updates Neo4j and Qdrant."""
    print("🚀 Ingesting Codebase into Neo4j & Qdrant...\n")

    module_files = glob.glob("modules/**/*.py", recursive=True)
    if not module_files:
        print("❌ No python modules found in 'modules/' directory.")
        return

    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_pass = os.getenv("NEO4J_PASSWORD")

    graph_store = None
    if neo4j_uri and neo4j_pass:
        try:
            graph_store = Neo4jGraphStore(neo4j_uri, neo4j_user, neo4j_pass)
        except Exception as e:
            print(f"⚠️ Warning: Neo4j connection failed: {e}")

    doc_id_counter = 1

    for filepath in module_files:
        if "__init__.py" in filepath:
            continue

        print(f"📦 Processing '{filepath}'...")
        parser = CodeASTParser(filepath)
        ast_data = parser.extract_structures()

        # 1. Ingest into Neo4j Knowledge Graph
        if graph_store:
            try:
                graph_store.ingest_ast(filepath, ast_data)
            except Exception as e:
                print(f"   ❌ Graph Error: {e}")

        # 2. Ingest Functions & Methods into Vector Store
        for fn in ast_data.get("functions", []):
            snippet_text = (
                f"File: {filepath}\n"
                f"Function/Method: {fn['name']}\n"
                f"Docstring: {fn.get('docstring', '')}\n"
                f"Code:\n{fn.get('code', '')}"
            )
            vector_store.upsert_code_snippet(
                doc_id=doc_id_counter,
                code_snippet=snippet_text,
                metadata={"file": filepath, "type": fn.get("type", "function"), "name": fn["name"]}
            )
            doc_id_counter += 1

        # 3. Ingest Classes into Vector Store
        for cls in ast_data.get("classes", []):
            method_names = [m["name"] if isinstance(m, dict) else str(m) for m in cls.get("methods", [])]
            snippet_text = (
                f"File: {filepath}\n"
                f"Class: {cls['name']}\n"
                f"Methods: {', '.join(method_names)}\n"
                f"Docstring: {cls.get('docstring', '')}"
            )
            vector_store.upsert_code_snippet(
                doc_id=doc_id_counter,
                code_snippet=snippet_text,
                metadata={"file": filepath, "type": "class", "name": cls["name"]}
            )
            doc_id_counter += 1

        # 4. Ingest Global Constants (e.g., FALLBACK_MODELS) into Vector Store
        for const in ast_data.get("constants", []):
            snippet_text = (
                f"File: {filepath}\n"
                f"Constant: {const['name']}\n"
                f"Docstring: {const.get('docstring', '')}\n"
                f"Code:\n{const.get('code', '')}"
            )
            vector_store.upsert_code_snippet(
                doc_id=doc_id_counter,
                code_snippet=snippet_text,
                metadata={"file": filepath, "type": "constant", "name": const["name"]}
            )
            doc_id_counter += 1

    if graph_store:
        graph_store.close()

    print("\n🎉 Knowledge Graph & Vector Store successfully updated!\n")

def interactive_chat():
    vector_store = CodeVectorStore()
    ingest_codebase(vector_store)
    
    agent = CodeGraphAgent(vector_store=vector_store)
    print("🤖 CodeGraph Agent initialized! Type 'exit' or 'quit' to stop.\n")
    print("=" * 60)

    try:
        while True:
            user_query = input("\n❓ Ask CodeGraph Agent: ").strip()
            if not user_query:
                continue

            if user_query.lower() in ["exit", "quit"]:
                print("\n👋 Exiting CodeGraph Agent. Goodbye!")
                break

            print("\n🔍 Analyzing codebase and querying graph + vector stores...")
            answer = agent.query(user_query)
            
            print("\n💡 Agent Response:")
            print("-" * 60)
            print(answer)
            print("-" * 60)

    except KeyboardInterrupt:
        print("\n\n👋 Session interrupted. Goodbye!")
    finally:
        agent.close()

if __name__ == "__main__":
    interactive_chat()