"""MCP server (official python-sdk) exposing mcp_tools_travel tools.

This uses FastMCP from the official MCP Python SDK:
- Tools are ordinary Python functions decorated with @mcp.tool().
- Schemas are derived automatically from type hints / Pydantic models.
- Transport (stdio, SSE, streamable HTTP) is handled by the SDK/CLI.
"""

from __future__ import annotations

from datetime import date
from typing import List

import sys
import argparse
import logging

import uvicorn
from mcp.server.fastmcp import FastMCP

from ..core.cache import FileCache
from ..core.schemas import Coordinates, WeatherProfile, Spot
from ..services.geocoding import geocode_destination
from ..services.weather import get_weather_profile
from ..services.pois import get_activity_spots
from ..services.scoring import score_spots_heuristic
from ..services.get_parks import get_parks_nearby


# ---------------------------------------------------------------------------
# MCP-Server & Tools
# ---------------------------------------------------------------------------

mcp = FastMCP(name="weather-planner", stateless_http=False)

logger = logging.getLogger("weather-planner-mcp")
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

#@mcp.tool()
#def ping() -> str:
#    """Health check: returns 'pong'"""
#    return "pong"

@mcp.tool()
def geocode(destination: str) -> Coordinates:
    """Geocode a destination string to coordinates using OSM Nominatim (token-free)."""
    cache = FileCache("./data/cache")
    return geocode_destination(destination, cache=cache)


@mcp.tool()
def get_weather(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    include_raw: bool = False,
) -> WeatherProfile:
    """Get a daily Open-Meteo WeatherProfile for the given coordinates and date range (YYYY-MM-DD)."""
    cache = FileCache("./data/cache")
    coords = Coordinates(lat=lat, lon=lon)
    return get_weather_profile(
        coords=coords,
        start=date.fromisoformat(start_date),
        end=date.fromisoformat(end_date),
        cache=cache,
        include_raw=include_raw,
    )


@mcp.tool()
def get_parks(
    lat: float,
    lon: float,
    radius_km: float,
    max_elements: int = 5,
) -> List[Spot]:
    """
    Liefert Parks (OSM leisure=park) in der Nähe von (lat, lon),
    inklusive Distanz in km unter tags["distance_km"].
    """
    cache = FileCache("./data/cache")
    return get_parks_nearby(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        max_elements=max_elements,
        cache=cache,
    )

@mcp.tool()
def get_spots(
    lat: float,
    lon: float,
    radius_km: float,
    activity: str,
) -> List[Spot]:
    """Query Overpass/OSM for activity spots near coordinates (token-free)."""
    cache = FileCache("./data/cache")
    return get_activity_spots(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        activity=activity,
        cache=cache,
    )


@mcp.tool()
def rank_spots(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    activity: str,
    radius_km: float = 15.0,
    top_k: int = 8,
) -> List[Spot]:
    """Mini pipeline: fetch weather + fetch spots + heuristic scoring/ranking for one activity.

    Returns the top_k spots with filled fields: distance_km, travel_time_min, score.
    """
    cache = FileCache("./data/cache")
    coords = Coordinates(lat=lat, lon=lon)
    weather = get_weather_profile(
        coords,
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
        cache=cache,
    )

    spots = get_activity_spots(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        activity=activity,
        cache=cache,
    )
    ranked = score_spots_heuristic(lat, lon, spots, weather)
    return ranked[: max(1, int(top_k))]


# ---------------------------------------------------------------------------
# ASGI-App für streamable HTTP & Uvicorn-Entry-Point
# ---------------------------------------------------------------------------

# ASGI-App exportieren; der MCP-Endpunkt ist /mcp
starlette_app = mcp.streamable_http_app()  # path="/mcp"


def main() -> None:
    """Start the weather-planner MCP server via Uvicorn (streamable HTTP)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    logger.info(
        "Starting weather-planner MCP server (streamable-http) on http://%s:%d/mcp …",
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
