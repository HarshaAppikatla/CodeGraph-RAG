#!/usr/bin/env python3
"""
Model Context Protocol (MCP) Server for CodeGraph-RAG.
Implements JSON-RPC 2.0 over stdio to expose codebase intelligence to Cursor, Claude, and VS Code.
All debug logs and print statements are redirected strictly to sys.stderr to guarantee stdio protocol safety.
"""

import sys
import os
import json
import traceback
from typing import Dict, Any, List
from dotenv import load_dotenv

# Load .env file automatically for standalone stdio processes
load_dotenv()

# STDIOSAFETY: Save real stdout for JSON-RPC 2.0 transport only,
# and permanently redirect standard sys.stdout to sys.stderr.
_real_stdout = sys.stdout
sys.stdout = sys.stderr

try:
    from backend.app.services.vector_store import CodeVectorStore
    from backend.app.services.graph_store import Neo4jGraphStore
    from backend.app.services.repo_ingestor import RepositoryIngestor
    from backend.app.services.ast_parser import CodeASTParser
    from backend.app.services.agent_workflow import CodeGraphAgent
except ImportError:
    try:
        from app.services.vector_store import CodeVectorStore
        from app.services.graph_store import Neo4jGraphStore
        from app.services.repo_ingestor import RepositoryIngestor
        from app.services.ast_parser import CodeASTParser
        from app.services.agent_workflow import CodeGraphAgent
    except ImportError:
        CodeVectorStore = None
        Neo4jGraphStore = None
        RepositoryIngestor = None
        CodeASTParser = None
        CodeGraphAgent = None


class CodeGraphMCPServer:
    """MCP Server exposing CodeGraph-RAG tools over stdio."""

    def __init__(self):
        self.vector_store = None
        self.graph_store = None
        self.ast_parser = None
        self.repo_ingestor = None
        self.agent = None
        self._init_backend()

    def log(self, message: str) -> None:
        """Logs status strictly to sys.stderr to preserve stdout for JSON-RPC transport."""
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()

    def _init_backend(self):
        """Initializes storage engines quietly with all diagnostics directed to stderr."""
        self.log("🚀 Starting CodeGraph-RAG MCP Server...")
        try:
            if CodeVectorStore:
                try:
                    self.vector_store = CodeVectorStore()
                except Exception as vs_err:
                    self.log(f"⚠️ VectorStore init notice: {vs_err}")

            if CodeASTParser:
                self.ast_parser = CodeASTParser

            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "neo4j"))
            neo4j_pass = os.getenv("NEO4J_PASSWORD", "password")

            if Neo4jGraphStore:
                try:
                    self.graph_store = Neo4jGraphStore(
                        uri=neo4j_uri,
                        user=neo4j_user,
                        password=neo4j_pass,
                    )
                except Exception as graph_err:
                    self.log(f"⚠️ Neo4j initialization notice: {graph_err}")
                    self.graph_store = None

            if RepositoryIngestor:
                try:
                    self.repo_ingestor = RepositoryIngestor(
                        vector_store=self.vector_store,
                        graph_store=self.graph_store,
                        ast_parser=self.ast_parser,
                    )
                except Exception as ing_err:
                    self.log(f"⚠️ RepositoryIngestor init notice: {ing_err}")

            if CodeGraphAgent and os.getenv("GEMINI_API_KEY"):
                try:
                    self.agent = CodeGraphAgent(vector_store=self.vector_store)
                except Exception as agent_err:
                    self.log(f"⚠️ CodeGraphAgent init notice: {agent_err}")

            self.log("✅ CodeGraph-RAG MCP Server initialized successfully!")
        except Exception as e:
            self.log(f"⚠️ Warning during MCP initialization: {e}")

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns MCP tool declarations for IDE client registration."""
        return [
            {
                "name": "search_codebase",
                "description": "Performs semantic vector search and AI context reasoning across code snippets in Qdrant.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language question or query regarding codebase logic or architecture.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Maximum number of code snippets to retrieve.",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "analyze_symbol_impact",
                "description": "Performs multi-hop Neo4j graph impact analysis to identify callers, subclasses, and affected files.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Target function, method, or class name (e.g., 'generateToken' or 'registerStompEndpoints').",
                        }
                    },
                    "required": ["symbol"],
                },
            },
            {
                "name": "get_file_graph",
                "description": "Retrieves the structural layout of a file (classes, methods, imports, and method call edges).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Relative file path within the repository.",
                        }
                    },
                    "required": ["filepath"],
                },
            },
            {
                "name": "ingest_repository",
                "description": "Dynamically clones and indexes a remote Git repository URL or extracts a local ZIP archive into Qdrant and Neo4j.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_url": {
                            "type": "string",
                            "description": "Git repository HTTPS URL or path to a local .zip archive.",
                        }
                    },
                    "required": ["repo_url"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Routes tool execution to the appropriate backend module."""
        try:
            if tool_name == "search_codebase":
                user_query = args.get("query", "")
                top_k = args.get("top_k", 5)
                if not user_query:
                    return {"isError": True, "content": [{"type": "text", "text": "Query parameter is required."}]}

                if self.agent:
                    response_text = self.agent.query(user_query)
                elif self.vector_store:
                    results = self.vector_store.search(user_query, top_k=top_k)
                    response_text = json.dumps(results, indent=2)
                else:
                    response_text = "Search engines unavailable."

                return {"content": [{"type": "text", "text": response_text}]}

            elif tool_name in ("analyze_symbol_impact", "analyze_impact"):
                symbol = args.get("symbol") or args.get("target_symbol", "")
                if not symbol:
                    return {"isError": True, "content": [{"type": "text", "text": "Symbol parameter is required."}]}

                if self.graph_store:
                    impact_data = self.graph_store.analyze_impact(symbol)
                    return {"content": [{"type": "text", "text": json.dumps(impact_data, indent=2)}]}
                return {"isError": True, "content": [{"type": "text", "text": "Neo4j Graph Store not connected."}]}

            elif tool_name == "get_file_graph":
                filepath = args.get("filepath", "")
                if not filepath:
                    return {"isError": True, "content": [{"type": "text", "text": "Filepath parameter is required."}]}

                if self.graph_store:
                    file_data = self.graph_store.get_file_graph(filepath)
                    return {"content": [{"type": "text", "text": json.dumps(file_data, indent=2)}]}
                return {"isError": True, "content": [{"type": "text", "text": "Neo4j Graph Store not connected."}]}

            elif tool_name == "ingest_repository":
                repo_url = args.get("repo_url", "")
                if not repo_url:
                    return {"isError": True, "content": [{"type": "text", "text": "repo_url parameter is required."}]}

                if not self.repo_ingestor:
                    return {"isError": True, "content": [{"type": "text", "text": "Repository Ingestor not initialized."}]}

                if repo_url.endswith(".zip"):
                    res = self.repo_ingestor.ingest_zip_archive(repo_url)
                else:
                    res = self.repo_ingestor.ingest_git_repo(repo_url)

                return {"content": [{"type": "text", "text": f"Ingestion Result:\n{json.dumps(res, indent=2)}"}]}

            else:
                return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}

        except Exception as e:
            err_trace = traceback.format_exc()
            return {"isError": True, "content": [{"type": "text", "text": f"Error executing '{tool_name}': {e}\n{err_trace}"}]}

    def send_response(self, response: Dict[str, Any]) -> None:
        """Writes JSON-RPC response strictly to real stdout."""
        msg = json.dumps(response)
        _real_stdout.write(msg + "\n")
        _real_stdout.flush()

    def run(self) -> None:
        """Main stdio JSON-RPC processing loop."""
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    self.log(f"⚠️ Invalid JSON received: {line}")
                    continue

                msg_id = request.get("id")
                method = request.get("method")

                if method == "initialize":
                    self.send_response({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {
                                "name": "codegraph-rag-mcp",
                                "version": "2.0.0",
                            },
                        },
                    })
                elif method == "notifications/initialized":
                    pass
                elif method == "ping":
                    self.send_response({"jsonrpc": "2.0", "id": msg_id, "result": {}})
                elif method == "tools/list":
                    self.send_response({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {"tools": self.get_tool_definitions()},
                    })
                elif method == "tools/call":
                    params = request.get("params", {})
                    tool_name = params.get("name")
                    arguments = params.get("arguments", {})
                    result = self.handle_tool_call(tool_name, arguments)
                    self.send_response({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": result,
                    })
                elif msg_id is not None:
                    self.send_response({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method '{method}' not found.",
                        },
                    })
        except (KeyboardInterrupt, EOFError):
            self.log("👋 Shutting down CodeGraph-RAG MCP Server.")


if __name__ == "__main__":
    server = CodeGraphMCPServer()
    server.run()
