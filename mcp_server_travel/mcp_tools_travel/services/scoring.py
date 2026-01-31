from __future__ import annotations

from typing import List, Optional

from ..core.schemas import Spot, WeatherProfile
from ..utils.geo import haversine_km, travel_time_minutes


def score_spots_heuristic(
    origin_lat: float,
    origin_lon: float,
    spots: List[Spot],
    weather: Optional[WeatherProfile],
) -> List[Spot]:
    """Add distance, travel-time, and a transparent baseline score to each spot.

    This is intentionally simple and explainable for trainings.
    Swap it later with a learned model (classic ML) without changing the MCP tools.
    """
    for s in spots:
        d_km = haversine_km(origin_lat, origin_lon, s.lat, s.lon)
        s.distance_km = d_km
        s.travel_time_min = travel_time_minutes(d_km)
        s.score = _heuristic_score(distance_km=d_km, weather=weather, activity=s.activity or "sightseeing")

    return sorted(spots, key=lambda x: (x.score or 0.0), reverse=True)


def _heuristic_score(distance_km: float, weather: Optional[WeatherProfile], activity: str) -> float:
    """Baseline score in ~[0..100]."""
    score = 70.0

    # distance penalty
    score -= min(35.0, distance_km * 1.5)

    if weather is not None:
        rainy_days = weather.rainy_days or 0
        score -= min(20.0, rainy_days * 3.0)

        tmax = weather.temp_max_c
        if tmax is not None:
            if tmax >= 33:
                score -= 10.0
            elif 20 <= tmax <= 28:
                score += 5.0

        wmax = weather.wind_max_kmh
        if wmax is not None and wmax >= 45 and activity in {"beach", "hiking"}:
            score -= 8.0

    if activity == "running":
        score += 2.0
    elif activity == "beach" and weather is not None and (weather.rainy_days or 0) == 0:
        score += 5.0

    return float(max(0.0, min(100.0, score)))
