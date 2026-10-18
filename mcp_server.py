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
finally:
    sys.stdout = _real_stdout


class CodeGraphMCPServer:
    """MCP Server exposing CodeGraph-RAG tools over stdio."""

    def __init__(self):
        self.vector_store = None
        self.graph_store = None
        self.agent = None
        self._init_backend()

    def _init_backend(self):
        """Initializes storage engines and RAG agent quietly."""
        sys.stderr.write("🚀 Starting CodeGraph-RAG MCP Server...\n")
        try:
            self.vector_store = CodeVectorStore()
            
            neo4j_uri = os.getenv("NEO4J_URI")
            neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
            neo4j_pass = os.getenv("NEO4J_PASSWORD")
            if neo4j_uri and neo4j_pass:
                self.graph_store = Neo4jGraphStore(neo4j_uri, neo4j_user, neo4j_pass)

            self.agent = CodeGraphAgent(vector_store=self.vector_store)
            sys.stderr.write("✅ CodeGraph-RAG MCP Server initialized successfully!\n")
        except Exception as e:
            sys.stderr.write(f"⚠️ Warning during MCP initialization: {e}\n")

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns MCP tool declarations for IDE client registration."""
        return [
            {
                "name": "search_codebase",
                "description": "Performs semantic and hybrid code search across the codebase using vector search and AI context reasoning.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language question or search query regarding the codebase structure or logic."
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "analyze_symbol_impact",
                "description": "Performs deep multi-hop Neo4j graph impact analysis to identify direct and transitive callers, subclasses, and files affected if a symbol changes.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Name of the target function, method, or class (e.g. 'processPayment' or 'search_similar_code')."
                        }
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "get_file_graph",
                "description": "Retrieves the structural graph layout of a file, including classes, methods, imports, and call relationships.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Relative file path (e.g. 'modules/vector_store.py' or 'modules/SampleService.java')."
                        }
                    },
                    "required": ["filepath"]
                }
            }
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Routes tool execution to the appropriate backend module."""
        try:
            if tool_name == "search_codebase":
                user_query = args.get("query", "")
                if not user_query:
                    return {"isError": True, "content": [{"type": "text", "text": "Query parameter is required."}]}
                
                if self.agent:
                    response_text = self.agent.query(user_query)
                else:
                    response_text = "RAG Agent unavailable."

                return {"content": [{"type": "text", "text": response_text}]}

            elif tool_name == "analyze_symbol_impact":
                symbol = args.get("symbol", "")
                if not symbol:
                    return {"isError": True, "content": [{"type": "text", "text": "Symbol parameter is required."}]}

                if self.graph_store:
                    impact_data = self.graph_store.analyze_impact(symbol)
                    formatted_json = json.dumps(impact_data, indent=2)
                    return {"content": [{"type": "text", "text": f"Impact Analysis for '{symbol}':\n{formatted_json}"}]}
                else:
                    return {"isError": True, "content": [{"type": "text", "text": "Neo4j Graph Store not connected."}]}

            elif tool_name == "get_file_graph":
                filepath = args.get("filepath", "")
                if not filepath:
                    return {"isError": True, "content": [{"type": "text", "text": "Filepath parameter is required."}]}

                if self.graph_store:
                    file_data = self.graph_store.get_file_graph(filepath)
                    formatted_json = json.dumps(file_data, indent=2)
                    return {"content": [{"type": "text", "text": f"Graph Structure for '{filepath}':\n{formatted_json}"}]}
                else:
                    return {"isError": True, "content": [{"type": "text", "text": "Neo4j Graph Store not connected."}]}

            else:
                return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}

        except Exception as e:
            err_trace = traceback.format_exc()
            return {"isError": True, "content": [{"type": "text", "text": f"Error executing '{tool_name}': {e}\n{err_trace}"}]}

    def send_response(self, response: Dict[str, Any]):
        """Writes JSON-RPC response strictly to real stdout."""
        msg = json.dumps(response)
        _real_stdout.write(msg + "\n")
        _real_stdout.flush()

    def run(self):
        """Main stdio JSON-RPC processing loop."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                sys.stderr.write(f"⚠️ Invalid JSON received: {line}\n")
                continue

            msg_id = request.get("id")
            method = request.get("method")

            # 1. Standard MCP Handshake
            if method == "initialize":
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "codegraph-rag-mcp",
                            "version": "1.0.0"
                        }
                    }
                })

            elif method == "notifications/initialized":
                pass  # Client notification confirmation

            # 2. List Available Tools
            elif method == "tools/list":
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": self.get_tool_definitions()
                    }
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
                    "result": result
                })

            elif msg_id is not None:
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found."
                    }
                })


if __name__ == "__main__":
    server = CodeGraphMCPServer()
    server.run()