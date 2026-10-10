"""
RailSathi AI — Geocoding Provider Interface & Implementations

Provides unified geocoding abstractions and provider adapters for real-world venue resolution.
Coordinates originate strictly from authoritative providers or verified local caches;
LLMs are never used to invent or guess geographic coordinates.
"""

import time
import logging
import threading
from typing import Any, Optional, Protocol, runtime_checkable
from urllib.parse import urlencode
import urllib.request
import urllib.error
import json
from datetime import datetime

from backend.config import (
    GEOCODING_PROVIDER,
    GEOCODING_PROVIDER_URL,
    GEOCODING_USER_AGENT,
    GEOCODING_TIMEOUT_SECONDS,
)
from backend.journey.models import GeocodedPlaceCandidate

logger = logging.getLogger("railsaathi.journey.geocoding")


@runtime_checkable
class GeocodingProvider(Protocol):
    """Protocol defining the standard interface for geocoding providers."""

    @property
    def provider_name(self) -> str:
        """Human-readable provider identifier."""
        ...

    def search_venue(
        self,
        query: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = "India",
    ) -> list[GeocodedPlaceCandidate]:
        """
        Search for a place/venue and return normalized candidate locations.
        Must return an empty list if no results found or on network failure.
        """
        ...


class OSMNominatimGeocodingProvider:
    """
    OpenStreetMap Nominatim Geocoding Provider.
    
    Complies with OSM Nominatim Usage Policy:
    1. Valid, custom User-Agent identifying the application.
    2. Rate-limited to max 1 request/second via atomic lock.
    3. Structured error handling without unhandled exceptions.
    """

    def __init__(
        self,
        endpoint_url: str = GEOCODING_PROVIDER_URL,
        user_agent: str = GEOCODING_USER_AGENT,
        timeout_seconds: float = GEOCODING_TIMEOUT_SECONDS,
        min_request_interval_seconds: float = 1.0,
    ):
        self.endpoint_url = endpoint_url
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.min_request_interval_seconds = min_request_interval_seconds
        self._last_request_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def provider_name(self) -> str:
        return "OpenStreetMap Nominatim"

    def _enforce_rate_limit(self) -> None:
        """Enforce strict client-side interval between requests."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self.min_request_interval_seconds:
                sleep_time = self.min_request_interval_seconds - elapsed
                time.sleep(sleep_time)
            self._last_request_time = time.time()

    def search_venue(
        self,
        query: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = "India",
    ) -> list[GeocodedPlaceCandidate]:
        """Query Nominatim search endpoint and return normalized candidates."""
        if not query or not query.strip():
            return []

        # Construct structured query string
        query_parts = [query.strip()]
        if city and city.lower() not in query.lower():
            query_parts.append(city.strip())
        if state and state.lower() not in query.lower():
            query_parts.append(state.strip())
        if country and country.lower() not in query.lower():
            query_parts.append(country.strip())

        full_query = ", ".join(query_parts)

        params = {
            "q": full_query,
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": "5",
        }
        if country and country.lower() == "india":
            params["countrycodes"] = "in"

        url = f"{self.endpoint_url}?{urlencode(params)}"
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        self._enforce_rate_limit()

        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                if resp.status != 200:
                    logger.warning(f"Nominatim returned status {resp.status} for query '{full_query}'")
                    return []
                raw_data = resp.read().decode("utf-8")
                results = json.loads(raw_data)

            candidates: list[GeocodedPlaceCandidate] = []
            for item in results:
                try:
                    lat = float(item["lat"])
                    lon = float(item["lon"])
                except (KeyError, ValueError, TypeError):
                    continue

                addr = item.get("address", {})
                item_city = (
                    addr.get("city")
                    or addr.get("town")
                    or addr.get("village")
                    or addr.get("suburb")
                    or addr.get("county")
                    or city
                )
                item_state = addr.get("state") or state
                item_country = addr.get("country") or "India"
                place_name = item.get("name") or query.title()
                display_name = item.get("display_name", full_query)
                importance = float(item.get("importance", 0.6))
                confidence = round(min(0.98, max(0.40, importance)), 2)

                candidates.append(
                    GeocodedPlaceCandidate(
                        place_name=place_name,
                        formatted_address=display_name,
                        latitude=lat,
                        longitude=lon,
                        city=item_city,
                        state=item_state,
                        country=item_country,
                        provider=self.provider_name,
                        provider_place_id=str(item.get("place_id", "")),
                        confidence=confidence,
                        retrieved_at=datetime.now().isoformat(),
                        raw_metadata={"osm_id": item.get("osm_id"), "category": item.get("category")},
                    )
                )

            return candidates

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Geocoding request failed for query '{full_query}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in geocoding provider: {e}")
            return []


class MockGeocodingProvider:
    """
    Deterministic Mock Geocoding Provider for Offline Unit & Integration Tests.
    Allows injecting predefined candidate fixtures, simulating network outages, and tracking calls.
    """

    def __init__(self, fixtures: Optional[dict[str, list[GeocodedPlaceCandidate]]] = None):
        self.provider_name_val = "MockGeocodingProvider"
        self.fixtures: dict[str, list[GeocodedPlaceCandidate]] = fixtures or {}
        self.calls_count: int = 0
        self.queries_received: list[str] = []
        self.simulate_outage: bool = False

    @property
    def provider_name(self) -> str:
        return self.provider_name_val

    def set_fixtures(self, fixtures: dict[str, list[GeocodedPlaceCandidate]]) -> None:
        self.fixtures = fixtures

    def add_fixture(self, query_key: str, candidates: list[GeocodedPlaceCandidate]) -> None:
        self.fixtures[query_key.lower().strip()] = candidates

    def search_venue(
        self,
        query: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = "India",
    ) -> list[GeocodedPlaceCandidate]:
        self.calls_count += 1
        self.queries_received.append(query)

        if self.simulate_outage:
            logger.warning("Mock geocoder simulating network outage.")
            return []

        q_clean = query.lower().strip()

        # Exact match
        if q_clean in self.fixtures:
            return self.fixtures[q_clean]

        # Substring match in fixtures
        for k, v in self.fixtures.items():
            if k in q_clean or q_clean in k:
                return v

        return []


class VerifiedRegistryGeocodingProvider:
    """
    Local Authoritative Registry Provider for offline and baseline lookups.
    Uses verified local datasets for venues and stations without external HTTP calls.
    """

    def __init__(self):
        self.provider_name_val = "RailSathi Venue Registry (Verified)"

    @property
    def provider_name(self) -> str:
        return self.provider_name_val

    def search_venue(
        self,
        query: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = "India",
    ) -> list[GeocodedPlaceCandidate]:
        from backend.journey.location import VENUE_REGISTRY, CITY_CENTROIDS

        q_norm = query.strip().lower()
        ctx_norm = city.strip().lower() if city else None

        # Check for ambiguous venues like tidel park without locality
        if q_norm == "tidel park" and not ctx_norm:
            candidates = []
            branch_keys = [
                ("Tidel Park, Taramani, Chennai (OMR IT Corridor)", "tidel park, taramani, chennai", "Chennai"),
                ("TIDEL Park Pattabiram, Chennai/Tiruvallur District", "tidel park, pattabiram", "Chennai"),
                ("TIDEL Park Coimbatore, ELCOT SEZ", "tidel park, coimbatore", "Coimbatore"),
                ("TIDEL / ELCOT IT Park, Madurai", "tidel park, madurai", "Madurai"),
                ("TIDEL Park Trichy, Panjappur", "tidel park, tiruchirappalli", "Tiruchirappalli"),
            ]
            for name, key, city_name in branch_keys:
                if key in VENUE_REGISTRY:
                    v = VENUE_REGISTRY[key]
                    candidates.append(
                        GeocodedPlaceCandidate(
                            place_name=name,
                            formatted_address=v["resolved_address"],
                            latitude=v["latitude"],
                            longitude=v["longitude"],
                            city=city_name,
                            state=v["state"],
                            country="India",
                            provider=self.provider_name,
                            confidence=0.98,
                        )
                    )
            return candidates

        # Match against VENUE_REGISTRY
        matched: Optional[dict[str, Any]] = None
        for key, vdata in VENUE_REGISTRY.items():
            if q_norm in [k.lower() for k in vdata["keywords"]] or q_norm == key.lower():
                matched = vdata
                break

        if not matched:
            if "pattabiram" in q_norm:
                matched = VENUE_REGISTRY.get("tidel park, pattabiram")
            elif "coimbatore" in q_norm or (ctx_norm == "coimbatore" and "tidel" in q_norm):
                matched = VENUE_REGISTRY.get("tidel park, coimbatore")
            elif "madurai" in q_norm or (ctx_norm == "madurai" and ("tidel" in q_norm or "elcot" in q_norm)):
                matched = VENUE_REGISTRY.get("tidel park, madurai")
            elif "trichy" in q_norm or "tiruchirappalli" in q_norm or (ctx_norm in ["trichy", "tiruchirappalli"] and "tidel" in q_norm):
                matched = VENUE_REGISTRY.get("tidel park, tiruchirappalli")
            elif ("chennai" in q_norm or ctx_norm == "chennai" or "taramani" in q_norm or "omr" in q_norm) and "tidel" in q_norm:
                matched = VENUE_REGISTRY.get("tidel park, taramani, chennai")

        if not matched:
            for key, vdata in VENUE_REGISTRY.items():
                for kw in vdata["keywords"]:
                    if kw in q_norm or (q_norm in kw and len(q_norm) > 4):
                        if "pattabiram" in q_norm and "taramani" in vdata["canonical_name"].lower():
                            continue
                        matched = vdata
                        break
                if matched:
                    break

        if matched:
            return [
                GeocodedPlaceCandidate(
                    place_name=matched["canonical_name"],
                    formatted_address=matched["resolved_address"],
                    latitude=matched["latitude"],
                    longitude=matched["longitude"],
                    city=matched["city"],
                    state=matched["state"],
                    country="India",
                    provider=self.provider_name,
                    confidence=0.98,
                )
            ]

        # Check CITY_CENTROIDS
        for c_key, c_data in CITY_CENTROIDS.items():
            if q_norm == c_key or q_norm in [f"in {c_key}", f"to {c_key}", f"{c_key} city", f"{c_key} center", f"{c_key} central"]:
                return [
                    GeocodedPlaceCandidate(
                        place_name=f"{c_data['city']} City Center",
                        formatted_address=f"{c_data['city']}, {c_data['state']}, India",
                        latitude=c_data["lat"],
                        longitude=c_data["lon"],
                        city=c_data["city"],
                        state=c_data["state"],
                        country="India",
                        provider="RailSathi City Centroid Registry",
                        confidence=0.85,
                    )
                ]

        return []


def get_geocoding_provider(provider_type: Optional[str] = None) -> GeocodingProvider:
    """Factory to instantiate the configured GeocodingProvider."""
    p_type = (provider_type or GEOCODING_PROVIDER).strip().lower()

    if p_type == "nominatim":
        return OSMNominatimGeocodingProvider()
    elif p_type == "registry":
        return VerifiedRegistryGeocodingProvider()
    elif p_type == "mock":
        return MockGeocodingProvider()
    else:
        logger.info(f"Using VerifiedRegistry geocoding provider for type: '{p_type}'")
        return VerifiedRegistryGeocodingProvider()
