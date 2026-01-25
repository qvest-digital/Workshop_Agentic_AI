from __future__ import annotations

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (Haversine) in kilometers."""
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def travel_time_minutes(distance_km: float) -> float:
    """Travel time heuristic without routing APIs.

    Goal: deterministic + explainable for trainings, not "perfect".
    """
    if distance_km <= 2:
        speed_kmh = 15.0
    elif distance_km <= 10:
        speed_kmh = 25.0
    elif distance_km <= 30:
        speed_kmh = 45.0
    else:
        speed_kmh = 60.0
    return (distance_km / speed_kmh) * 60.0
