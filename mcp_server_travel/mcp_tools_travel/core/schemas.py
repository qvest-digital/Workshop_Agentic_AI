from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Coordinates(BaseModel):
    """Geographic coordinates in WGS84."""
    lat: float
    lon: float


class TripSpec(BaseModel):
    """Normalized trip specification.

    This is what an orchestrator/LLM should produce after info-checking.
    """
    destination: str = Field(..., description="Free-text destination, e.g. 'Barcelona' or 'Toskana'")
    start_date: date
    end_date: date
    activities: List[str] = Field(default_factory=list)

    # Optional constraints/preferences (extend later)
    temp_preference_c: Optional[float] = None
    avoid_rain: Optional[bool] = None
    max_radius_km: float = 15.0


class WeatherDay(BaseModel):
    """Daily weather data (Open-Meteo daily fields)."""
    date: date
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    precipitation_mm: Optional[float] = None
    wind_max_kmh: Optional[float] = None
    weather_code: Optional[int] = None


class WeatherProfile(BaseModel):
    """Weather profile for a time range.

    Contains daily records + lightweight aggregates for scoring/planning/packing.
    """
    start_date: date
    end_date: date
    days: List[WeatherDay]

    # Aggregates
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    precip_total_mm: Optional[float] = None
    rainy_days: Optional[int] = None
    wind_max_kmh: Optional[float] = None

    # Raw API payload for debugging/tracing (keep small when possible)
    raw: Dict[str, Any] = Field(default_factory=dict)

    # Provenance / transparency for downstream agents & UI
    source: str = Field(
        default="forecast",
        description="Data source: forecast | archive | historical_fallback",
    )
    is_estimate: bool = Field(
        default=False,
        description="True if values are an estimate (e.g., historical fallback for far-future dates).",
    )
    reference_years: List[int] = Field(
        default_factory=list,
        description="Years used to build an estimate when source=historical_fallback.",
    )


class Spot(BaseModel):
    """A candidate activity spot (POI) from Overpass/OSM."""
    name: str
    lat: float
    lon: float
    tags: Dict[str, Any] = Field(default_factory=dict)

    # Derived / computed fields (optional)
    activity: Optional[str] = None
    distance_km: Optional[float] = None
    travel_time_min: Optional[float] = None
    score: Optional[float] = None
