from __future__ import annotations

import math
from typing import Dict, List, Optional

import requests

from ..core.cache import FileCache
from ..core.schemas import Spot


def get_parks_nearby(
    lat: float,
    lon: float,
    radius_km: float,
    cache: Optional[FileCache] = None,
    timeout_s: int = 60,
    max_elements: int = 5,
) -> List[Spot]:
    """
    Liefert Parks (OSM leisure=park) in der Nähe von (lat, lon),
    inklusive Distanz in km unter tags["distance_km"].
    """
    r_m = int(max(1.0, radius_km) * 1000)

    query = f"""
    [out:json][timeout:25];
    (
      node["leisure"="park"](around:{r_m},{lat},{lon});
      way["leisure"="park"](around:{r_m},{lat},{lon});
    );
    out center {max_elements};
    """

    key = f"overpass:parks:{lat:.5f},{lon:.5f}:{radius_km:.2f}"

    if cache:
        cached = cache.get(key)
        if cached:
            return _spots_from_overpass(cached, origin_lat=lat, origin_lon=lon)

    url = "https://overpass-api.de/api/interpreter"
    r = requests.post(url, data={"data": query}, timeout=timeout_s)
    r.raise_for_status()
    data: Dict = r.json()

    if cache:
        cache.set(key, data)

    return _spots_from_overpass(data, origin_lat=lat, origin_lon=lon)


def _spots_from_overpass(
    data: Dict,
    origin_lat: float,
    origin_lon: float,
) -> List[Spot]:
    elements = data.get("elements") or []
    spots: List[Spot] = []

    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue

        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            center = el.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")
        if lat is None or lon is None:
            continue

        distance_km = _haversine_distance_km(origin_lat, origin_lon, float(lat), float(lon))
        tags = dict(tags)
        tags["distance_km"] = distance_km

        spots.append(
            Spot(
                name=str(name),
                lat=float(lat),
                lon=float(lon),
                tags=tags,
                activity="parks",
            )
        )

    # Deduplicate (name + rounded coords)
    seen = set()
    uniq: List[Spot] = []
    for s in spots:
        k = (s.name.lower().strip(), round(s.lat, 5), round(s.lon, 5))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)

    # Nach Distanz sortieren
    uniq.sort(key=lambda s: float(s.tags.get("distance_km", 1e9)))

    return uniq


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine-Abstand in km zwischen zwei WGS84-Koordinaten."""
    R = 6371.0  # Erdradius in km

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c
