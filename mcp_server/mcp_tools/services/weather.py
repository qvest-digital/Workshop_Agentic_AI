from __future__ import annotations

"""Weather service (Open-Meteo).

This module deliberately supports three modes:

1) forecast
   - Uses Open-Meteo forecast endpoint for near-term dates.
   - Forecast horizon is limited (typically up to ~16 days).

2) archive
   - Uses Open-Meteo archive endpoint for historical dates.

3) historical_fallback (for far-future ranges)
   - When a user plans months ahead, a *forecast* is not available.
   - We approximate weather using the same date range in recent past years
     (e.g., the last 10 years) and aggregate into a "typical" daily profile.

Why this is useful for the training use case:
- It's transparent: the returned WeatherProfile includes provenance fields
  (source, is_estimate, reference_years).
- It demonstrates limitations of forecasting systems and how to design
  sane fallbacks using available data.
"""

from datetime import date, timedelta
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

import requests

from ..core.cache import FileCache
from ..core.schemas import Coordinates, WeatherDay, WeatherProfile


FORECAST_BASE_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Open-Meteo forecast is typically available up to ~16 days.
# We hard-code a conservative value to decide routing.
MAX_FORECAST_DAYS = 16


def get_weather_profile(
    coords: Coordinates,
    start: date,
    end: date,
    cache: Optional[FileCache] = None,
    timeout_s: int = 30,
    include_raw: bool = False,
    mode: str = "auto",  # "auto" | "forecast" | "archive" | "historical_fallback"
    fallback_years_back: int = 10,
    fallback_min_years: int = 3,
) -> WeatherProfile:
    """Return a WeatherProfile for the requested date range.

    Args:
        coords: Coordinates (lat/lon).
        start/end: Date range (inclusive).
        cache: Optional file cache for stability and rate-limit protection.
        include_raw: If True, include raw API payload (can be large).
        mode:
          - "auto": choose forecast/archive/fallback automatically
          - "forecast": force forecast endpoint
          - "archive": force archive endpoint
          - "historical_fallback": force fallback estimation from archive data
        fallback_years_back: How many past years to consider for fallback estimation.
        fallback_min_years: Minimum number of successful archive years needed.

    Returns:
        WeatherProfile, with provenance fields:
        - source: forecast | archive | historical_fallback
        - is_estimate: True for historical_fallback
        - reference_years: used years for fallback
    """
    if end < start:
        raise ValueError("end_date must be >= start_date")

    today = date.today()
    max_forecast_date = today + timedelta(days=MAX_FORECAST_DAYS)

    if mode not in {"auto", "forecast", "archive", "historical_fallback"}:
        raise ValueError("mode must be one of: auto, forecast, archive, historical_fallback")

    chosen = mode
    if mode == "auto":
        # Entire range in the past => archive
        if end < today:
            chosen = "archive"
        # Range is within forecast horizon => forecast
        elif end <= max_forecast_date:
            chosen = "forecast"
        # Otherwise: far future range => fallback
        else:
            chosen = "historical_fallback"

    if chosen == "forecast":
        prof = _fetch_openmeteo_daily(
            base_url=FORECAST_BASE_URL,
            source="forecast",
            coords=coords,
            start=start,
            end=end,
            cache=cache,
            timeout_s=timeout_s,
            include_raw=include_raw,
        )
        return prof

    if chosen == "archive":
        prof = _fetch_openmeteo_daily(
            base_url=ARCHIVE_BASE_URL,
            source="archive",
            coords=coords,
            start=start,
            end=end,
            cache=cache,
            timeout_s=timeout_s,
            include_raw=include_raw,
        )
        return prof

    # Historical fallback for far future
    prof = _historical_fallback_from_archive(
        coords=coords,
        requested_start=start,
        requested_end=end,
        cache=cache,
        timeout_s=timeout_s,
        include_raw=include_raw,
        years_back=fallback_years_back,
        min_years=fallback_min_years,
    )
    return prof


def _fetch_openmeteo_daily(
    base_url: str,
    source: str,
    coords: Coordinates,
    start: date,
    end: date,
    cache: Optional[FileCache],
    timeout_s: int,
    include_raw: bool,
) -> WeatherProfile:
    """Fetch daily data from either forecast or archive endpoint."""
    key = f"openmeteo:{source}:daily:{coords.lat:.5f},{coords.lon:.5f}:{start.isoformat()}:{end.isoformat()}"
    if cache:
        cached = cache.get(key)
        if cached:
            profile = _profile_from_openmeteo(cached, start, end, include_raw=include_raw)
            profile.source = source
            profile.is_estimate = False
            profile.reference_years = []
            return profile

    params = {
        "latitude": coords.lat,
        "longitude": coords.lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,weathercode",
        "timezone": "auto",
    }

    r = requests.get(base_url, params=params, timeout=timeout_s)
    if r.status_code >= 400:
        # Try to surface Open-Meteo error reason (often present for 400s)
        try:
            err = r.json()
            reason = err.get("reason") if isinstance(err, dict) else None
        except Exception:
            reason = None
        extra = f" Reason: {reason}" if reason else ""
        raise ValueError(f"Open-Meteo request failed ({r.status_code}).{extra}")

    data = r.json()
    if cache:
        cache.set(key, data)

    profile = _profile_from_openmeteo(data, start, end, include_raw=include_raw)
    profile.source = source
    profile.is_estimate = False
    profile.reference_years = []
    return profile


def _historical_fallback_from_archive(
    coords: Coordinates,
    requested_start: date,
    requested_end: date,
    cache: Optional[FileCache],
    timeout_s: int,
    include_raw: bool,
    years_back: int,
    min_years: int,
) -> WeatherProfile:
    """Estimate a future weather profile using archive data from past years.

    Strategy (simple and training-friendly):
    - For each of the last `years_back` years, fetch archive data for the same month/day span.
    - Aggregate per-day across years:
        - temperature, precipitation, wind: mean
        - weather_code: most frequent (mode)
    - Return WeatherProfile for the *requested future dates*, but values are historical averages.

    If too few years succeed, raise a clear error.
    """
    today = date.today()
    candidate_years = [today.year - i for i in range(1, years_back + 1)]

    yearly_profiles: List[Tuple[int, WeatherProfile]] = []
    for y in candidate_years:
        mapped_start = _safe_replace_year(requested_start, y)
        mapped_end = _safe_replace_year(requested_end, y)
        if mapped_end < mapped_start:
            # Extremely rare edge cases (e.g. leap-day mapping). Skip year.
            continue
        try:
            prof = _fetch_openmeteo_daily(
                base_url=ARCHIVE_BASE_URL,
                source=f"archive-{y}",
                coords=coords,
                start=mapped_start,
                end=mapped_end,
                cache=cache,
                timeout_s=timeout_s,
                include_raw=include_raw,
            )
            yearly_profiles.append((y, prof))
        except Exception:
            # Skip years that fail (network, missing data, etc.)
            continue

    if len(yearly_profiles) < min_years:
        raise ValueError(
            f"Historical fallback failed: only {len(yearly_profiles)} archive years succeeded "
            f"(need at least {min_years})."
        )

    # Build day list for requested range
    requested_days = _date_range_inclusive(requested_start, requested_end)

    # Align by day index (assumes archive responses cover same number of days)
    agg_days: List[WeatherDay] = []
    for idx, d_req in enumerate(requested_days):
        vals_tmin: List[float] = []
        vals_tmax: List[float] = []
        vals_prec: List[float] = []
        vals_wind: List[float] = []
        vals_code: List[int] = []

        for _, prof in yearly_profiles:
            if idx >= len(prof.days):
                continue
            day = prof.days[idx]
            if day.temp_min_c is not None:
                vals_tmin.append(day.temp_min_c)
            if day.temp_max_c is not None:
                vals_tmax.append(day.temp_max_c)
            if day.precipitation_mm is not None:
                vals_prec.append(day.precipitation_mm)
            if day.wind_max_kmh is not None:
                vals_wind.append(day.wind_max_kmh)
            if day.weather_code is not None:
                vals_code.append(int(day.weather_code))

        agg_days.append(
            WeatherDay(
                date=d_req,
                temp_min_c=mean(vals_tmin) if vals_tmin else None,
                temp_max_c=mean(vals_tmax) if vals_tmax else None,
                precipitation_mm=mean(vals_prec) if vals_prec else None,
                wind_max_kmh=mean(vals_wind) if vals_wind else None,
                weather_code=_mode_int(vals_code) if vals_code else None,
            )
        )

    profile = WeatherProfile(
        start_date=requested_start,
        end_date=requested_end,
        days=agg_days,
        raw={},
        source="historical_fallback",
        is_estimate=True,
        reference_years=[y for y, _ in yearly_profiles],
    )

    # aggregates
    mins = [x.temp_min_c for x in agg_days if x.temp_min_c is not None]
    maxs = [x.temp_max_c for x in agg_days if x.temp_max_c is not None]
    precs = [x.precipitation_mm for x in agg_days if x.precipitation_mm is not None]
    winds = [x.wind_max_kmh for x in agg_days if x.wind_max_kmh is not None]

    profile.temp_min_c = min(mins) if mins else None
    profile.temp_max_c = max(maxs) if maxs else None
    profile.precip_total_mm = sum(precs) if precs else None
    profile.rainy_days = sum(1 for d in agg_days if (d.precipitation_mm or 0.0) >= 1.0)
    profile.wind_max_kmh = max(winds) if winds else None
    return profile


def _profile_from_openmeteo(data: Dict[str, Any], start: date, end: date, include_raw: bool) -> WeatherProfile:
    """Transform raw Open-Meteo payload into our domain model."""
    daily = data.get("daily") or {}
    times = daily.get("time") or []

    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []
    wind = daily.get("windspeed_10m_max") or []
    wcode = daily.get("weathercode") or []

    days: List[WeatherDay] = []
    for i, t in enumerate(times):
        try:
            d = date.fromisoformat(t)
        except Exception:
            continue
        days.append(
            WeatherDay(
                date=d,
                temp_min_c=_safe_float(tmin, i),
                temp_max_c=_safe_float(tmax, i),
                precipitation_mm=_safe_float(precip, i),
                wind_max_kmh=_safe_float(wind, i),
                weather_code=_safe_int(wcode, i),
            )
        )

    return WeatherProfile(
        start_date=start,
        end_date=end,
        days=days,
        raw=data if include_raw else {},
    )


def _safe_replace_year(d: date, year: int) -> date:
    """Replace year while avoiding invalid dates (Feb 29)."""
    try:
        return d.replace(year=year)
    except ValueError:
        # Feb 29 -> Feb 28 in non-leap years
        if d.month == 2 and d.day == 29:
            return date(year, 2, 28)
        # Fallback: clamp day down until valid
        day = d.day
        while day > 28:
            day -= 1
            try:
                return date(year, d.month, day)
            except ValueError:
                continue
        return date(year, d.month, day)


def _date_range_inclusive(start: date, end: date) -> List[date]:
    days: List[date] = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def _mode_int(values: List[int]) -> int:
    """Return the most common int (mode). Break ties by choosing the smallest."""
    counts: Dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    # sort by count desc, then value asc
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _safe_float(arr: List[Any], idx: int) -> Optional[float]:
    try:
        v = arr[idx]
        return None if v is None else float(v)
    except Exception:
        return None


def _safe_int(arr: List[Any], idx: int) -> Optional[int]:
    try:
        v = arr[idx]
        return None if v is None else int(v)
    except Exception:
        return None
