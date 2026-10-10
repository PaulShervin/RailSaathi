"""
RailSathi AI — RailRadar Live API Smoke Test

Optional, standalone smoke test suite.
Executes live API calls against https://api.railradar.in ONLY when RAILRADAR_API_KEY is configured.
Never prints raw credentials or full authorization headers.
"""

import os
import pytest
from backend.config import RAILRADAR_API_KEY, RAILRADAR_BASE_URL
from backend.journey.railradar_client import RailRadarClient
from backend.journey.timetable import RailRadarTrainDataProvider


@pytest.mark.skipif(
    not os.getenv("RAILRADAR_API_KEY") and not RAILRADAR_API_KEY,
    reason="RAILRADAR_API_KEY not configured in environment. Skipping live smoke test."
)
def test_live_railradar_station_search():
    """Live smoke test: station search for 'Chennai'."""
    client = RailRadarClient(
        api_key=os.getenv("RAILRADAR_API_KEY") or RAILRADAR_API_KEY,
        base_url=RAILRADAR_BASE_URL,
        timeout_seconds=8.0,
    )
    res = client.search_stations("Chennai", limit=5)
    assert res is not None
    assert isinstance(res.get("data"), list)
    print(f"\n[LIVE SMOKE] Station search returned {len(res.get('data', []))} stations.")


@pytest.mark.skipif(
    not os.getenv("RAILRADAR_API_KEY") and not RAILRADAR_API_KEY,
    reason="RAILRADAR_API_KEY not configured in environment. Skipping live smoke test."
)
def test_live_railradar_train_search():
    """Live smoke test: search trains between SBC and MAS."""
    provider = RailRadarTrainDataProvider()
    trains = provider.search_trains(
        origin_station_code="SBC",
        destination_station_code="MAS",
        journey_date="2026-10-25",
    )
    assert isinstance(trains, list)
    print(f"\n[LIVE SMOKE] Live train search SBC -> MAS returned {len(trains)} trains.")
    if trains:
        t0 = trains[0]
        print(f"[LIVE SMOKE] First train: {t0.train_name} ({t0.train_number}) - Departs {t0.departure_time} Arrives {t0.arrival_time}")


@pytest.mark.skipif(
    not os.getenv("RAILRADAR_API_KEY") and not RAILRADAR_API_KEY,
    reason="RAILRADAR_API_KEY not configured in environment. Skipping live smoke test."
)
def test_live_railradar_fare_lookup():
    """Live smoke test: fare lookup for train 20608 CC."""
    provider = RailRadarTrainDataProvider()
    fare = provider.get_fare(
        train_number="20608",
        source_station_code="SBC",
        destination_station_code="MAS",
        journey_date="2026-10-25",
        class_code="CC",
        quota_code="GN",
    )
    if fare:
        print(f"\n[LIVE SMOKE] Live fare lookup 20608 CC: Total ₹{fare.total_fare} ({fare.data_source})")
        assert fare.total_fare > 0
    else:
        print("\n[LIVE SMOKE] Live fare lookup returned None (record absent or unavailable).")
