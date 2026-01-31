"""MCP server (official python-sdk) exposing mcp_tools_travel tools.

This uses FastMCP from the official MCP Python SDK:
- Tools are ordinary Python functions decorated with @mcp.tool().
- Schemas are derived automatically from type hints / Pydantic models.
- Transport (stdio, SSE, streamable HTTP) is handled by the SDK/CLI.
"""

from __future__ import annotations

import sys
import argparse
import logging

import uvicorn
from mcp.server.fastmcp import FastMCP


from ..services.addition import fun_add
from ..services.subtraction import fun_sub
from ..services.multiplication import fun_mul
from ..services.division import fun_div

# ---------------------------------------------------------------------------
# MCP-Server & Tools
# ---------------------------------------------------------------------------

mcp = FastMCP(name="math-server", stateless_http=False)

logger = logging.getLogger("math-mcp")
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

#@mcp.tool()
#def ping() -> str:
#    """Health check: returns 'pong'"""
#    return "pong"

@mcp.tool()
def addition(a: float, b: float) -> float:
    """Addiert a + b"""
    return fun_add(a, b)


@mcp.tool()
def subtraktion(a: float, b: float) -> float:
    """Subtrahiert a - b"""
    return fun_sub(a, b)


@mcp.tool()
def multiplikation(a: float, b: float) -> float:
    """Multipliziert a * b"""
    return fun_mul(a, b)

@mcp.tool()
def division(a: float, b: float) -> float:
    """Dividiert a / b"""
    return fun_div(a, b)

# ---------------------------------------------------------------------------
# ASGI-App für streamable HTTP & Uvicorn-Entry-Point
# ---------------------------------------------------------------------------

# ASGI-App exportieren; der MCP-Endpunkt ist /mcp
starlette_app = mcp.streamable_http_app()  # path="/mcp"


def main() -> None:
    """Start the math MCP server via Uvicorn (streamable HTTP)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    logger.info(
        "Starting Math MCP server (streamable-http) on http://%s:%d/mcp …",
        args.host,
        args.port,
    )

    uvicorn.run(
        starlette_app,
        host=args.host,
        port=args.port,
        reload=False,
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
