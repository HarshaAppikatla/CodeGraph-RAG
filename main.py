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
        graph_store = Neo4jGraphStore(neo4j_uri, neo4j_user, neo4j_pass)

    doc_id_counter = 1

    for filepath in module_files:
        if "__init__.py" in filepath:
            continue
            
        print(f"📦 Processing '{filepath}'...")
        
        parser = CodeASTParser(filepath)
        ast_data = parser.extract_structures()

        if graph_store:
            try:
                graph_store.ingest_ast(filepath, ast_data)
            except Exception as e:
                print(f"  ❌ Graph Error: {e}")

        for fn in ast_data.get("functions", []):
            snippet_text = f"File: {filepath}\nFunction: {fn['name']}\nArguments: {', '.join(fn['args'])}\nDocstring: {fn['docstring']}"
            vector_store.upsert_code_snippet(
                doc_id=doc_id_counter,
                code_snippet=snippet_text,
                metadata={"file": filepath, "type": "function", "name": fn["name"]}
            )
            doc_id_counter += 1

        for cls in ast_data.get("classes", []):
            snippet_text = f"File: {filepath}\nClass: {cls['name']}\nMethods: {', '.join(cls['methods'])}\nDocstring: {cls['docstring']}"
            vector_store.upsert_code_snippet(
                doc_id=doc_id_counter,
                code_snippet=snippet_text,
                metadata={"file": filepath, "type": "class", "name": cls["name"]}
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