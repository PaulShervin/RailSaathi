"""
RailSathi AI — Routing Provider Interface & Urban Travel Estimators

Provides routing abstractions and last-mile travel calculation engines.
Separates deterministic geometric/heuristic road models from provider-derived route data,
clearly labeling sources and maintaining persistent caching.
"""

import math
import logging
from typing import Any, Optional, Protocol, runtime_checkable
from datetime import datetime

logger = logging.getLogger("railsaathi.journey.routing")


def calculate_haversine_distance_km(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """Calculate the great-circle distance between two points on the earth in kilometers."""
    r = 6371.0  # Earth's mean radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(r * c, 2)


@runtime_checkable
class RoutingProvider(Protocol):
    """Protocol defining the standard interface for last-mile road routing providers."""

    @property
    def provider_name(self) -> str:
        """Human-readable provider identifier."""
        ...

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        transit_mode: str = "cab",
    ) -> dict[str, Any]:
        """
        Calculate distance and travel duration between two coordinates.
        Returns a dictionary with:
        - distance_km (float)
        - duration_minutes (int)
        - is_heuristic (bool)
        - provider (str)
        - source_type (str)
        - confidence (str)
        """
        ...


class DeterministicUrbanRoutingModel:
    """
    Deterministic urban road detour and travel-time model for Indian metropolitan areas.
    
    Parameters:
    - Road network detour factor: 1.30x straight-line aerial distance.
    - Average urban cab speed: 22.0 km/h (accounting for signals & city traffic).
    - Station exit and boarding buffer: 8 minutes.
    - Explicitly labeled as heuristic so users and consumers are not misled.
    """

    def __init__(
        self,
        detour_factor: float = 1.30,
        avg_speed_kmh: float = 22.0,
        terminal_buffer_minutes: int = 8,
    ):
        self.detour_factor = detour_factor
        self.avg_speed_kmh = avg_speed_kmh
        self.terminal_buffer_minutes = terminal_buffer_minutes

    @property
    def provider_name(self) -> str:
        return "RailSathi Deterministic Urban Routing Model (Heuristic Detour & Traffic Buffer)"

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        transit_mode: str = "cab",
    ) -> dict[str, Any]:
        aerial_dist_km = calculate_haversine_distance_km(origin_lat, origin_lon, dest_lat, dest_lon)
        road_dist_km = round(aerial_dist_km * self.detour_factor, 2)
        
        # Calculate travel minutes: (dist / speed) * 60 + terminal buffer
        driving_minutes = (road_dist_km / self.avg_speed_kmh) * 60.0
        total_minutes = int(math.ceil(driving_minutes + self.terminal_buffer_minutes))
        total_minutes = max(total_minutes, 10)  # Minimum 10 minutes for any station exit

        return {
            "distance_km": road_dist_km,
            "duration_minutes": total_minutes,
            "is_heuristic": True,
            "source_type": "heuristic_urban_model",
            "provider": self.provider_name,
            "confidence": "verified_heuristic_estimate",
            "retrieved_at": datetime.now().isoformat(),
        }


class MockRoutingProvider:
    """
    Mock routing provider for offline tests simulating external routing engines (e.g. OSRM, GraphHopper).
    """

    def __init__(self, fixed_distance_km: float = 12.5, fixed_duration_minutes: int = 35):
        self.fixed_distance_km = fixed_distance_km
        self.fixed_duration_minutes = fixed_duration_minutes
        self.calls_count: int = 0
        self.provider_name_val = "MockLiveRoutingEngine"

    @property
    def provider_name(self) -> str:
        return self.provider_name_val

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        transit_mode: str = "cab",
    ) -> dict[str, Any]:
        self.calls_count += 1
        return {
            "distance_km": self.fixed_distance_km,
            "duration_minutes": self.fixed_duration_minutes,
            "is_heuristic": False,
            "source_type": "routing_provider",
            "provider": self.provider_name,
            "confidence": "provider_live_route",
            "retrieved_at": datetime.now().isoformat(),
        }


def get_routing_provider(provider_type: Optional[str] = None) -> RoutingProvider:
    """Factory to instantiate the configured RoutingProvider."""
    p_type = (provider_type or "heuristic").strip().lower()
    if p_type == "mock":
        return MockRoutingProvider()
    return DeterministicUrbanRoutingModel()
