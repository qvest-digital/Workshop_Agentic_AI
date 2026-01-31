"""mcp_tools_travel package

Purpose:
- Provide clean, testable services for a weather-based travel & activity planner.
- Expose those services via an MCP server (official python-sdk / FastMCP), so an LLM can call tools.

Structure:
- core/: schemas + caching
- services/: geocoding/weather/pois/scoring logic
- utils/: pure helpers (geo math, etc.)
- mcp/: FastMCP server + tool wiring
"""

from .core.schemas import Coordinates, TripSpec, WeatherDay, WeatherProfile, Spot  # noqa: F401
