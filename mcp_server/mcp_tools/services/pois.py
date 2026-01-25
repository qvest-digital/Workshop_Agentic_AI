from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

import requests

from ..core.cache import FileCache
from ..core.schemas import Spot


# Minimal, explainable activity→OSM mapping for trainings.
_ACTIVITY_TO_OVERPASS: Dict[str, List[str]] = {
    "hiking": [
        'node["tourism"="viewpoint"](around:{r},{lat},{lon});',
        'node["natural"="peak"](around:{r},{lat},{lon});',
        'way["route"="hiking"](around:{r},{lat},{lon});',
    ],
    "running": [
        'node["leisure"="park"](around:{r},{lat},{lon});',
        'way["leisure"="park"](around:{r},{lat},{lon});',
        'way["highway"="pedestrian"](around:{r},{lat},{lon});',
    ],
    "beach": [
        'node["natural"="beach"](around:{r},{lat},{lon});',
        'way["natural"="beach"](around:{r},{lat},{lon});',
    ],
    "sightseeing": [
        'node["tourism"="attraction"](around:{r},{lat},{lon});',
        'node["historic"](around:{r},{lat},{lon});',
        'node["amenity"="museum"](around:{r},{lat},{lon});',
    ],
}


def get_activity_spots(
    lat: float,
    lon: float,
    radius_km: float,
    activity: str,
    cache: Optional[FileCache] = None,
    timeout_s: int = 60,
    max_elements: int = 80,
) -> List[Spot]:
    """Token-free POI retrieval via Overpass API.

    Notes:
    - Overpass is rate limited; caching is recommended.
    - We use `out center` so we can place ways on a map without full geometry.
    """
    activity_key = _normalize_activity(activity)
    selectors = _ACTIVITY_TO_OVERPASS.get(activity_key) or _ACTIVITY_TO_OVERPASS["sightseeing"]
    if activity_key not in _ACTIVITY_TO_OVERPASS:
        activity_key = "sightseeing"

    r_m = int(max(1.0, radius_km) * 1000)

    query_parts = "\n".join(s.format(r=r_m, lat=lat, lon=lon) for s in selectors)
    query = f"""
    [out:json][timeout:25];
    (
      {query_parts}
    );
    out center {max_elements};
    """

    key = f"overpass:{activity_key}:{lat:.5f},{lon:.5f}:{radius_km:.2f}:{hashlib.sha256(query.encode('utf-8')).hexdigest()}"
    if cache:
        cached = cache.get(key)
        if cached:
            return _spots_from_overpass(cached, activity_key)

    url = "https://overpass-api.de/api/interpreter"
    r = requests.post(url, data={"data": query}, timeout=timeout_s)
    r.raise_for_status()
    data = r.json()

    if cache:
        cache.set(key, data)

    return _spots_from_overpass(data, activity_key)


def _spots_from_overpass(data: Dict, activity_key: str) -> List[Spot]:
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

        spots.append(Spot(name=str(name), lat=float(lat), lon=float(lon), tags=tags, activity=activity_key))

    # Deduplicate (name + rounded coords)
    seen = set()
    uniq: List[Spot] = []
    for s in spots:
        k = (s.name.lower().strip(), round(s.lat, 5), round(s.lon, 5))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)

    return uniq


def _normalize_activity(activity: str) -> str:
    a = (activity or "").strip().lower()
    mapping = {
        "wandern": "hiking",
        "hike": "hiking",
        "hiking": "hiking",
        "laufen": "running",
        "joggen": "running",
        "running": "running",
        "strand": "beach",
        "beach": "beach",
        "sightseeing": "sightseeing",
        "kultur": "sightseeing",
        "museum": "sightseeing",
    }
    return mapping.get(a, a)