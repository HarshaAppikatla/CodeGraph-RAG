#!/usr/bin/env python3
"""
Model Context Protocol (MCP) Server for CodeGraph-RAG.
Proxies to backend.mcp_server with guaranteed Stdio Safety.
"""
from backend.mcp_server import CodeGraphMCPServer

if __name__ == "__main__":
    server = CodeGraphMCPServer()
    server.run()
