"""Entrypoint for running the MCP server (stdio).

Usage:
  python run_mcp_server.py

Or via MCP host config (e.g., Claude Desktop) pointing to this script.
"""
from mcp_tools_math.mcp.server import main

if __name__ == "__main__":
    main()
