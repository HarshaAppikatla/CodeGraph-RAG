#!/usr/bin/env python3
"""
Model Context Protocol (MCP) Server for CodeGraph-RAG.
Implements JSON-RPC 2.0 over stdio to expose codebase intelligence to Cursor, Claude, and VS Code.
"""

import sys
import os
import json
import traceback
from typing import Dict, Any, List
from dotenv import load_dotenv

# Load .env file automatically for standalone stdio processes
load_dotenv()

# Redirect stdout during module initialization to prevent stdout contamination
_real_stdout = sys.stdout
sys.stdout = sys.stderr

try:
    from modules.vector_store import CodeVectorStore
    from modules.graph_store import Neo4jGraphStore
    from modules.agent_workflow import CodeGraphAgent
    from modules.repo_ingestor import RepositoryIngestor
    try:
        from modules.ast_parser import CodeASTParser
    except ImportError:
        CodeASTParser = None
finally:
    sys.stdout = _real_stdout


class CodeGraphMCPServer:
    """MCP Server exposing CodeGraph-RAG tools over stdio."""

    def __init__(self):
        self.vector_store = None
        self.graph_store = None
        self.agent = None
        self.ast_parser = None
        self.repo_ingestor = None
        self._init_backend()

    def log(self, message: str) -> None:
        """Logs status strictly to sys.stderr to preserve stdout for JSON-RPC transport."""
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()

    def _init_backend(self):
        """Initializes storage engines, RAG agent, and repository ingestor quietly."""
        self.log("🚀 Starting CodeGraph-RAG MCP Server...")
        try:
            # 1. Initialize Vector Store
            self.vector_store = CodeVectorStore()

            # 2. AST Parser class reference
            if CodeASTParser:
                self.ast_parser = CodeASTParser

            # 3. Initialize Graph Store with env support
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "neo4j"))
            neo4j_pass = os.getenv("NEO4J_PASSWORD", "password")

            try:
                self.graph_store = Neo4jGraphStore(
                    uri=neo4j_uri,
                    user=neo4j_user,
                    password=neo4j_pass,
                )
            except Exception as graph_err:
                self.log(f"⚠️ Neo4j initialization skipped: {graph_err}")
                self.graph_store = None

            # 4. Initialize RAG Agent
            try:
                self.agent = CodeGraphAgent(vector_store=self.vector_store)
            except Exception as agent_err:
                self.log(f"⚠️ RAG Agent initialization fallback: {agent_err}")
                self.agent = None

            # 5. Initialize Repository Ingestor
            self.repo_ingestor = RepositoryIngestor(
                vector_store=self.vector_store,
                graph_store=self.graph_store,
                ast_parser=self.ast_parser,
            )
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
                            "description": "Target function, method, or class name (e.g., 'WebSocketConfig' or 'registerStompEndpoints').",
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

                if self.agent and hasattr(self.agent, "query"):
                    response_text = self.agent.query(user_query)
                elif self.vector_store:
                    results = self.vector_store.search_code_snippets(user_query, top_k=top_k)
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

                # 1. MCP Protocol Handshake
                if method == "initialize":
                    self.send_response({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {
                                "name": "codegraph-rag-mcp",
                                "version": "1.0.0",
                            },
                        },
                    })
                elif method == "notifications/initialized":
                    pass
                elif method == "ping":
                    self.send_response({"jsonrpc": "2.0", "id": msg_id, "result": {}})

                # 2. List Available Tools
                elif method == "tools/list":
                    self.send_response({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {"tools": self.get_tool_definitions()},
                    })

                # 3. Call Tool Request
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