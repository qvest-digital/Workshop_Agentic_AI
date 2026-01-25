from __future__ import annotations

from typing import Optional

import requests

from ..core.cache import FileCache
from ..core.schemas import Coordinates


def geocode_destination(
    destination: str,
    cache: Optional[FileCache] = None,
    user_agent: str = "weather-planner-mcp/0.1 (local)",
    timeout_s: int = 30,
) -> Coordinates:
    """Token-free geocoding via OSM Nominatim.

    Notes:
    - Nominatim requires a User-Agent header.
    - Do not spam; cache by default.
    """
    key = f"nominatim:{destination}"
    if cache:
        cached = cache.get(key)
        if cached and "lat" in cached and "lon" in cached:
            return Coordinates(lat=float(cached["lat"]), lon=float(cached["lon"]))

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": destination, "format": "json", "limit": 1}
    headers = {"User-Agent": user_agent}

    r = requests.get(url, params=params, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError(f"Nominatim: no results for destination='{destination}'")

    coords = Coordinates(lat=float(data[0]["lat"]), lon=float(data[0]["lon"]))
    if cache:
        cache.set(key, {"lat": coords.lat, "lon": coords.lon})
    return coords
