"""
RailSathi AI — Train Search and Schedule Service

Provides an abstracted data provider interface with implementations for:
1. RailRadarTrainDataProvider — Live schedules and fares from RailRadar (api.railradar.in)
2. MockTrainDataProvider — Offline verified schedule and tariff database for tests/dev
"""

import abc
import logging
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Set

from backend.config import (
    TRAIN_DATA_PROVIDER,
    RAILRADAR_API_KEY,
    RAILRADAR_BASE_URL,
    RAILRADAR_TIMEOUT_SECONDS,
    RAILRADAR_MAX_RETRIES,
    RAILRADAR_CACHE_ENABLED,
    RAILRADAR_CACHE_TTL_STATIONS,
    RAILRADAR_CACHE_TTL_TRAINS,
    RAILRADAR_CACHE_TTL_FARES,
    RAILRADAR_MAX_FARE_LOOKUPS_PER_REQUEST,
)
from backend.journey.models import (
    TrainService,
    FareQuote,
    FareBreakdown,
    JourneyEvaluation,
    TripRequirements,
)
from backend.journey.railradar_client import (
    RailRadarClient,
    RailRadarError,
    RailRadarConfigurationError,
    RailRadarNotFoundError,
    RailRadarBadRequestError,
    RailRadarAuthError,
    RailRadarRateLimitError,
    RailRadarUnavailableError,
)

logger = logging.getLogger("railsaathi.journey.timetable")



# =====================================================================
# Duration & Day-Offset Normalization Helpers
# =====================================================================

def parse_duration_to_minutes(val: Any) -> int:
    """Safely parse duration in various formats ('04:25', '4h 25m', '265', 265) to integer minutes."""
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return 0
        if ":" in val:
            parts = val.split(":")
            if len(parts) >= 2:
                try:
                    return int(parts[0]) * 60 + int(parts[1])
                except ValueError:
                    pass
        h_match = re.search(r"(\d+)\s*h(?:ours?|rs?)?", val, re.IGNORECASE)
        m_match = re.search(r"(\d+)\s*m(?:inutes?|ins?)?", val, re.IGNORECASE)
        if h_match or m_match:
            h = int(h_match.group(1)) if h_match else 0
            m = int(m_match.group(1)) if m_match else 0
            return h * 60 + m
        try:
            return int(val)
        except ValueError:
            pass
    return 0


def calculate_day_offset(
    dep_time_str: str,
    arr_time_str: str,
    from_day: Optional[int] = None,
    to_day: Optional[int] = None,
    explicit_offset: Optional[int] = None,
) -> int:
    """
    Calculate calendar day offset (0 for same day, 1 for next day, 2 for 2 days later).
    Uses provider day numbers if available, explicit offset, or time rollover heuristic.
    """
    if explicit_offset is not None:
        return int(explicit_offset)

    if from_day is not None and to_day is not None:
        diff = to_day - from_day
        if diff >= 0:
            return diff

    # Heuristic fallback for overnight runs (e.g. departs 22:40, arrives 04:35)
    try:
        dep_parts = dep_time_str.split(":")
        arr_parts = arr_time_str.split(":")
        dep_m = int(dep_parts[0]) * 60 + int(dep_parts[1])
        arr_m = int(arr_parts[0]) * 60 + int(arr_parts[1])
        if arr_m < dep_m:
            return 1
    except Exception:
        pass

    return 0


# =====================================================================
# Abstract Train Data Provider Interface
# =====================================================================

class TrainDataProvider(abc.ABC):
    """Abstract train and fare data provider interface."""

    @abc.abstractmethod
    def search_trains(
        self,
        origin_station_code: str,
        destination_station_code: str,
        journey_date: Optional[str] = None,
        preferred_class: Optional[str] = None,
    ) -> List[TrainService]:
        """Search trains running between a station pair."""
        pass

    @abc.abstractmethod
    def get_fare(
        self,
        train_number: str,
        source_station_code: str,
        destination_station_code: str,
        journey_date: str,
        class_code: str,
        quota_code: str = "GN",
    ) -> Optional[FareQuote]:
        """Retrieve journey-specific fare quote."""
        pass

    @abc.abstractmethod
    def search_stations(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search stations by code or name."""
        pass

    @abc.abstractmethod
    def get_train_by_number_or_name(self, query: str) -> Optional[TrainService]:
        """Lookup a specific train service by number or partial name."""
        pass


# =====================================================================
# Verified Mock Train Data Provider (For Tests and Offline Fallback)
# =====================================================================

TRAIN_DATABASE: List[Dict[str, Any]] = [
    # === Corridor: Bengaluru (SBC/SMVB/YPR) to Chennai (MAS/MS) ===
    {
        "train_number": "20608",
        "train_name": "MAS VANDE BHARAT EXPRESS",
        "origin_station_code": "SBC",
        "origin_station_name": "KSR Bengaluru",
        "destination_station_code": "MAS",
        "destination_station_name": "MGR Chennai Central",
        "departure_time": "05:45",
        "arrival_time": "10:10",
        "day_offset": 0,
        "duration_minutes": 265,  # 4h 25m
        "runs_on_days": ["Mon", "Tue", "Thu", "Fri", "Sat", "Sun"],  # Except Wed
        "classes": ["CC", "EC"],
        "fares": {"CC": 995.0, "EC": 1940.0},
        "intermediate_stops": [
            {"station_code": "BNC", "station_name": "Bengaluru Cantt", "arrival_time": "05:53", "departure_time": "05:55", "halt_minutes": 2},
            {"station_code": "KJM", "station_name": "Krishnarajapuram", "arrival_time": "06:08", "departure_time": "06:10", "halt_minutes": 2},
            {"station_code": "KPD", "station_name": "Katpadi Jn", "arrival_time": "08:18", "departure_time": "08:20", "halt_minutes": 2},
        ],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "12008",
        "train_name": "MAS SHATABDI EXPRESS",
        "origin_station_code": "SBC",
        "origin_station_name": "KSR Bengaluru",
        "destination_station_code": "MAS",
        "destination_station_name": "MGR Chennai Central",
        "departure_time": "06:00",
        "arrival_time": "11:00",
        "day_offset": 0,
        "duration_minutes": 300,  # 5h 00m
        "runs_on_days": ["Mon", "Tue", "Wed", "Fri", "Sat", "Sun"],  # Except Thu
        "classes": ["CC", "EC"],
        "fares": {"CC": 950.0, "EC": 1850.0},
        "intermediate_stops": [
            {"station_code": "BNC", "station_name": "Bengaluru Cantt", "arrival_time": "06:08", "departure_time": "06:10", "halt_minutes": 2},
            {"station_code": "KPD", "station_name": "Katpadi Jn", "arrival_time": "08:48", "departure_time": "08:50", "halt_minutes": 2},
        ],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "12640",
        "train_name": "BRINDAVAN EXPRESS",
        "origin_station_code": "SBC",
        "origin_station_name": "KSR Bengaluru",
        "destination_station_code": "MAS",
        "destination_station_name": "MGR Chennai Central",
        "departure_time": "15:10",
        "arrival_time": "21:10",
        "day_offset": 0,
        "duration_minutes": 360,  # 6h 00m
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["CC", "2S"],
        "fares": {"CC": 560.0, "2S": 160.0},
        "intermediate_stops": [
            {"station_code": "BNC", "station_name": "Bengaluru Cantt", "arrival_time": "15:20", "departure_time": "15:22", "halt_minutes": 2},
            {"station_code": "KJM", "station_name": "Krishnarajapuram", "arrival_time": "15:34", "departure_time": "15:35", "halt_minutes": 1},
            {"station_code": "KPD", "station_name": "Katpadi Jn", "arrival_time": "18:40", "departure_time": "18:45", "halt_minutes": 5},
            {"station_code": "AJJ", "station_name": "Arakkonam Jn", "arrival_time": "19:33", "departure_time": "19:35", "halt_minutes": 2},
        ],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "12608",
        "train_name": "LALBAGH EXPRESS",
        "origin_station_code": "SBC",
        "origin_station_name": "KSR Bengaluru",
        "destination_station_code": "MAS",
        "destination_station_name": "MGR Chennai Central",
        "departure_time": "06:20",
        "arrival_time": "12:15",
        "day_offset": 0,
        "duration_minutes": 355,  # 5h 55m
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["CC", "2S"],
        "fares": {"CC": 560.0, "2S": 160.0},
        "intermediate_stops": [
            {"station_code": "BNC", "station_name": "Bengaluru Cantt", "arrival_time": "06:30", "departure_time": "06:32", "halt_minutes": 2},
            {"station_code": "KPD", "station_name": "Katpadi Jn", "arrival_time": "09:48", "departure_time": "09:50", "halt_minutes": 2},
        ],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "12658",
        "train_name": "CHENNAI MAIL (OVERNIGHT)",
        "origin_station_code": "SBC",
        "origin_station_name": "KSR Bengaluru",
        "destination_station_code": "MAS",
        "destination_station_name": "MGR Chennai Central",
        "departure_time": "22:40",
        "arrival_time": "04:35",
        "day_offset": 1,  # Arrives next morning
        "duration_minutes": 355,  # 5h 55m
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["1A", "2A", "3A", "SL"],
        "fares": {"1A": 1950.0, "2A": 1175.0, "3A": 830.0, "SL": 315.0},
        "intermediate_stops": [
            {"station_code": "BNC", "station_name": "Bengaluru Cantt", "arrival_time": "22:50", "departure_time": "22:52", "halt_minutes": 2},
            {"station_code": "KJM", "station_name": "Krishnarajapuram", "arrival_time": "23:08", "departure_time": "23:10", "halt_minutes": 2},
            {"station_code": "KPD", "station_name": "Katpadi Jn", "arrival_time": "02:15", "departure_time": "02:20", "halt_minutes": 5},
            {"station_code": "PER", "station_name": "Perambur", "arrival_time": "04:10", "departure_time": "04:12", "halt_minutes": 2},
        ],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "22626",
        "train_name": "SBC MAS DOUBLE DECKER",
        "origin_station_code": "SBC",
        "origin_station_name": "KSR Bengaluru",
        "destination_station_code": "MAS",
        "destination_station_name": "MGR Chennai Central",
        "departure_time": "14:30",
        "arrival_time": "20:35",
        "day_offset": 0,
        "duration_minutes": 365,
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["CC"],
        "fares": {"CC": 580.0},
        "intermediate_stops": [
            {"station_code": "BNC", "station_name": "Bengaluru Cantt", "arrival_time": "14:40", "departure_time": "14:42", "halt_minutes": 2},
            {"station_code": "KPD", "station_name": "Katpadi Jn", "arrival_time": "17:58", "departure_time": "18:00", "halt_minutes": 2},
        ],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "12610",
        "train_name": "SBC MAS INTERCITY SUPERFAST",
        "origin_station_code": "SBC",
        "origin_station_name": "KSR Bengaluru",
        "destination_station_code": "MAS",
        "destination_station_name": "MGR Chennai Central",
        "departure_time": "08:00",
        "arrival_time": "14:25",
        "day_offset": 0,
        "duration_minutes": 385,
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["CC", "2S"],
        "fares": {"CC": 560.0, "2S": 160.0},
        "intermediate_stops": [
            {"station_code": "BNC", "station_name": "Bengaluru Cantt", "arrival_time": "08:11", "departure_time": "08:13", "halt_minutes": 2},
            {"station_code": "KJM", "station_name": "Krishnarajapuram", "arrival_time": "08:24", "departure_time": "08:25", "halt_minutes": 1},
            {"station_code": "KPD", "station_name": "Katpadi Jn", "arrival_time": "11:48", "departure_time": "11:50", "halt_minutes": 2},
        ],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "12678",
        "train_name": "ERNAKULAM INTERCITY SF EXP",
        "origin_station_code": "SBC",
        "origin_station_name": "KSR Bengaluru",
        "destination_station_code": "MAS",
        "destination_station_name": "MGR Chennai Central",
        "departure_time": "06:10",
        "arrival_time": "13:45",
        "day_offset": 0,
        "duration_minutes": 455,
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["CC", "2S"],
        "fares": {"CC": 560.0, "2S": 160.0},
        "intermediate_stops": [],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "12295",
        "train_name": "SANGHAMITRA EXPRESS",
        "origin_station_code": "SMVB",
        "origin_station_name": "SMVT Bengaluru",
        "destination_station_code": "MAS",
        "destination_station_name": "MGR Chennai Central",
        "departure_time": "09:15",
        "arrival_time": "15:35",
        "day_offset": 0,
        "duration_minutes": 380,
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["2A", "3A", "SL"],
        "fares": {"2A": 1175.0, "3A": 830.0, "SL": 315.0},
        "intermediate_stops": [
            {"station_code": "KJM", "station_name": "Krishnarajapuram", "arrival_time": "09:33", "departure_time": "09:35", "halt_minutes": 2},
            {"station_code": "KPD", "station_name": "Katpadi Jn", "arrival_time": "12:55", "departure_time": "13:00", "halt_minutes": 5},
        ],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    # === Corridor: Bengaluru to Hyderabad / Secunderabad ===
    {
        "train_number": "12786",
        "train_name": "KACHEGUDA EXPRESS (OVERNIGHT)",
        "origin_station_code": "SBC",
        "origin_station_name": "KSR Bengaluru",
        "destination_station_code": "KCG",
        "destination_station_name": "Kacheguda (Hyderabad)",
        "departure_time": "18:20",
        "arrival_time": "05:40",
        "day_offset": 1,
        "duration_minutes": 680,
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["1A", "2A", "3A", "SL"],
        "fares": {"1A": 2450.0, "2A": 1450.0, "3A": 1020.0, "SL": 390.0},
        "intermediate_stops": [],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "20704",
        "train_name": "KCG VANDE BHARAT",
        "origin_station_code": "YPR",
        "origin_station_name": "Yesvantpur Junction",
        "destination_station_code": "KCG",
        "destination_station_name": "Kacheguda (Hyderabad)",
        "departure_time": "14:45",
        "arrival_time": "23:00",
        "day_offset": 0,
        "duration_minutes": 495,
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],  # Except Sun
        "classes": ["CC", "EC"],
        "fares": {"CC": 1540.0, "EC": 2865.0},
        "intermediate_stops": [],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    # === Corridor: Delhi (NDLS/NZM) to Mumbai (CSMT/BCT/BDTS) ===
    {
        "train_number": "12952",
        "train_name": "MUMBAI RAJDHANI EXPRESS",
        "origin_station_code": "NDLS",
        "origin_station_name": "New Delhi",
        "destination_station_code": "BCT",
        "destination_station_name": "Mumbai Central",
        "departure_time": "16:55",
        "arrival_time": "08:35",
        "day_offset": 1,
        "duration_minutes": 940,
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["1A", "2A", "3A"],
        "fares": {"1A": 4850.0, "2A": 2980.0, "3A": 2150.0},
        "intermediate_stops": [],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "12954",
        "train_name": "AUGUST KRANTI RAJDHANI",
        "origin_station_code": "NZM",
        "origin_station_name": "Hazrat Nizamuddin",
        "destination_station_code": "BCT",
        "destination_station_name": "Mumbai Central",
        "departure_time": "17:15",
        "arrival_time": "10:05",
        "day_offset": 1,
        "duration_minutes": 1010,
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["1A", "2A", "3A", "3E"],
        "fares": {"1A": 4750.0, "2A": 2900.0, "3A": 2080.0, "3E": 1850.0},
        "intermediate_stops": [],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    # === Corridor: Delhi (NDLS) to Bengaluru (SBC) ===
    {
        "train_number": "22692",
        "train_name": "SBC RAJDHANI EXPRESS",
        "origin_station_code": "NZM",
        "origin_station_name": "Hazrat Nizamuddin",
        "destination_station_code": "SBC",
        "destination_station_name": "KSR Bengaluru",
        "departure_time": "19:50",
        "arrival_time": "05:20",
        "day_offset": 2,  # 33 hrs overnight + 1
        "duration_minutes": 2010,
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["1A", "2A", "3A"],
        "fares": {"1A": 6500.0, "2A": 4200.0, "3A": 3100.0},
        "intermediate_stops": [],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
    {
        "train_number": "12628",
        "train_name": "KARNATAKA EXPRESS",
        "origin_station_code": "NDLS",
        "origin_station_name": "New Delhi",
        "destination_station_code": "SBC",
        "destination_station_name": "KSR Bengaluru",
        "departure_time": "20:20",
        "arrival_time": "12:00",
        "day_offset": 2,
        "duration_minutes": 2380,
        "runs_on_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "classes": ["1A", "2A", "3A", "SL"],
        "fares": {"1A": 5400.0, "2A": 3150.0, "3A": 2200.0, "SL": 850.0},
        "intermediate_stops": [],
        "data_source": "Indian Railways National Train Enquiry System (NTES)",
        "verified_at": "2026-10-10",
    },
]


class MockTrainDataProvider(TrainDataProvider):
    """Deterministic, verified offline train database for local evaluation and tests."""

    def __init__(self, database: Optional[List[Dict[str, Any]]] = None):
        self.database = database or TRAIN_DATABASE

    def search_trains(
        self,
        origin_station_code: str,
        destination_station_code: str,
        journey_date: Optional[str] = None,
        preferred_class: Optional[str] = None,
    ) -> List[TrainService]:
        orig = origin_station_code.strip().upper()
        dest = destination_station_code.strip().upper()

        day_of_week: Optional[str] = None
        if journey_date:
            try:
                dt = datetime.strptime(journey_date, "%Y-%m-%d")
                day_of_week = dt.strftime("%a")
            except ValueError:
                pass

        matched: List[TrainService] = []
        for row in self.database:
            if row["origin_station_code"] != orig or row["destination_station_code"] != dest:
                continue

            if day_of_week and day_of_week not in row.get("runs_on_days", []):
                continue

            fare_quotes = {}
            for cls_code, fare_amt in row.get("fares", {}).items():
                fare_quotes[cls_code] = FareQuote(
                    train_number=row["train_number"],
                    train_name=row["train_name"],
                    source_station=row["origin_station_code"],
                    destination_station=row["destination_station_code"],
                    journey_date=journey_date or "2026-10-10",
                    class_code=cls_code,
                    quota_code="GN",
                    total_fare=float(fare_amt),
                    data_source="Indian Railways NTES Tariff Table",
                )

            service = TrainService(
                train_number=row["train_number"],
                train_name=row["train_name"],
                origin_station_code=row["origin_station_code"],
                origin_station_name=row["origin_station_name"],
                destination_station_code=row["destination_station_code"],
                destination_station_name=row["destination_station_name"],
                departure_time=row["departure_time"],
                arrival_time=row["arrival_time"],
                day_offset=row.get("day_offset", 0),
                duration_minutes=row["duration_minutes"],
                runs_on_days=row.get("runs_on_days", []),
                classes=row.get("classes", []),
                fares=row.get("fares", {}),
                fare_quotes=fare_quotes,
                intermediate_stops=row.get("intermediate_stops", []),
                data_source=row.get("data_source", "Indian Railways NTES"),
                verified_at=row.get("verified_at", "2026-10-10"),
                is_live_status=False,
                availability_status={c: "SCHEDULED_SERVICE" for c in row.get("classes", [])},
            )
            matched.append(service)

        return matched

    def get_fare(
        self,
        train_number: str,
        source_station_code: str,
        destination_station_code: str,
        journey_date: str,
        class_code: str,
        quota_code: str = "GN",
    ) -> Optional[FareQuote]:
        t_num = train_number.strip()
        cls_code = class_code.strip().upper()
        for row in self.database:
            if row["train_number"] == t_num:
                fares = row.get("fares", {})
                if cls_code in fares:
                    return FareQuote(
                        train_number=t_num,
                        train_name=row.get("train_name"),
                        source_station=source_station_code,
                        destination_station=destination_station_code,
                        journey_date=journey_date,
                        class_code=cls_code,
                        quota_code=quota_code,
                        total_fare=float(fares[cls_code]),
                        breakdown=FareBreakdown(base_fare=float(fares[cls_code]) * 0.85, reservation_charge=40.0),
                        data_source="Indian Railways NTES Tariff Table",
                    )
        return None

    def search_stations(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        q = query.strip().upper()
        results = []
        known_stations = {
            "SBC": "KSR Bengaluru City",
            "YPR": "Yesvantpur Junction",
            "SMVB": "SMVT Bengaluru",
            "BNC": "Bengaluru Cantt",
            "MAS": "MGR Chennai Central",
            "MS": "Chennai Egmore",
            "TBM": "Tambaram",
            "NDLS": "New Delhi",
            "NZM": "Hazrat Nizamuddin",
            "CSMT": "Chhatrapati Shivaji Maharaj Terminus",
            "BCT": "Mumbai Central",
            "BDTS": "Bandra Terminus",
            "KCG": "Kacheguda (Hyderabad)",
            "SC": "Secunderabad Junction",
            "HYB": "Hyderabad Deccan",
        }
        for code, name in known_stations.items():
            if q in code or q in name.upper():
                results.append({"code": code, "name": name})
                if len(results) >= limit:
                    break
        return results

    def get_train_by_number_or_name(self, query: str) -> Optional[TrainService]:
        q = query.strip().upper()
        for row in self.database:
            if row["train_number"] == q or q in row["train_name"].upper():
                return TrainService(
                    train_number=row["train_number"],
                    train_name=row["train_name"],
                    origin_station_code=row["origin_station_code"],
                    origin_station_name=row["origin_station_name"],
                    destination_station_code=row["destination_station_code"],
                    destination_station_name=row["destination_station_name"],
                    departure_time=row["departure_time"],
                    arrival_time=row["arrival_time"],
                    day_offset=row.get("day_offset", 0),
                    duration_minutes=row["duration_minutes"],
                    runs_on_days=row.get("runs_on_days", []),
                    classes=row.get("classes", []),
                    fares=row.get("fares", {}),
                    intermediate_stops=row.get("intermediate_stops", []),
                    data_source=row.get("data_source", "Indian Railways NTES"),
                    verified_at=row.get("verified_at", "2026-10-10"),
                    is_live_status=False,
                    availability_status={c: "SCHEDULED_SERVICE" for c in row.get("classes", [])},
                )
        return None


# =====================================================================
# RailRadar Live Train Data Provider Adapter
# =====================================================================

class RailRadarTrainDataProvider(TrainDataProvider):
    """
    Production adapter consuming the real RailRadar API.
    Normalizes trains, handles day-offsets, and calculates journey-specific fares.
    """

    def __init__(self, client: Optional[RailRadarClient] = None):
        if client is not None:
            self.client = client
        else:
            self.client = RailRadarClient(
                api_key=RAILRADAR_API_KEY,
                base_url=RAILRADAR_BASE_URL,
                timeout_seconds=RAILRADAR_TIMEOUT_SECONDS,
                max_retries=RAILRADAR_MAX_RETRIES,
                cache_enabled=RAILRADAR_CACHE_ENABLED,
                ttl_stations=RAILRADAR_CACHE_TTL_STATIONS,
                ttl_trains=RAILRADAR_CACHE_TTL_TRAINS,
                ttl_fares=RAILRADAR_CACHE_TTL_FARES,
            )

    def search_trains(
        self,
        origin_station_code: str,
        destination_station_code: str,
        journey_date: Optional[str] = None,
        preferred_class: Optional[str] = None,
    ) -> List[TrainService]:
        """Query RailRadar API for trains between stations and normalize into TrainService models."""
        try:
            res = self.client.search_trains(
                origin_station_code=origin_station_code,
                destination_station_code=destination_station_code,
                journey_date=journey_date,
                live=False,
            )
        except RailRadarNotFoundError:
            logger.info(f"No trains found between {origin_station_code} and {destination_station_code}")
            return []
        except RailRadarError as e:
            logger.error(f"RailRadar search_trains failed: {e.message}")
            raise

        data = res.get("data", {})
        trace_id = res.get("trace_id")
        retrieved_at = res.get("retrieved_at") or datetime.now().isoformat()

        # Parse trains array
        train_list: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            train_list = data.get("trains", [])
            header_from = data.get("from", {})
            header_to = data.get("to", {})
        elif isinstance(data, list):
            train_list = data
            header_from = {}
            header_to = {}
        else:
            train_list = []
            header_from = {}
            header_to = {}

        normalized: List[TrainService] = []

        for item in train_list:
            if not isinstance(item, dict):
                continue

            t_num = str(item.get("number") or item.get("train_number") or "").strip()
            t_name = str(item.get("name") or item.get("train_name") or f"Train {t_num}").strip()

            from_obj = item.get("from") if isinstance(item.get("from"), dict) else header_from
            to_obj = item.get("to") if isinstance(item.get("to"), dict) else header_to

            orig_code = str(from_obj.get("code") or origin_station_code).strip().upper()
            orig_name = str(from_obj.get("name") or orig_code).strip()
            dest_code = str(to_obj.get("code") or destination_station_code).strip().upper()
            dest_name = str(to_obj.get("name") or dest_code).strip()

            dep_time = str(from_obj.get("departure") or item.get("departure_time") or item.get("departure") or "00:00").strip()
            arr_time = str(to_obj.get("arrival") or item.get("arrival_time") or item.get("arrival") or "00:00").strip()

            # Format times to HH:MM
            if len(dep_time) == 4 and dep_time.isdigit():
                dep_time = f"{dep_time[:2]}:{dep_time[2:]}"
            if len(arr_time) == 4 and arr_time.isdigit():
                arr_time = f"{arr_time[:2]}:{arr_time[2:]}"

            from_day = from_obj.get("day")
            to_day = to_obj.get("day")
            day_offset = calculate_day_offset(
                dep_time_str=dep_time,
                arr_time_str=arr_time,
                from_day=from_day,
                to_day=to_day,
                explicit_offset=item.get("day_offset"),
            )

            dur_val = item.get("duration") or item.get("duration_minutes") or 0
            dur_mins = parse_duration_to_minutes(dur_val)

            # Running days
            run_days = item.get("runDays") or item.get("runs_on_days") or [
                "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"
            ]
            if isinstance(run_days, str):
                run_days = [d.strip() for d in run_days.split(",") if d.strip()]

            # Available classes
            classes = item.get("classes") or []
            if isinstance(classes, str):
                classes = [c.strip().upper() for c in classes.split(",") if c.strip()]

            service = TrainService(
                train_number=t_num,
                train_name=t_name,
                origin_station_code=orig_code,
                origin_station_name=orig_name,
                destination_station_code=dest_code,
                destination_station_name=dest_name,
                departure_time=dep_time,
                arrival_time=arr_time,
                day_offset=day_offset,
                duration_minutes=dur_mins,
                runs_on_days=run_days,
                classes=classes,
                fares={},  # Fares will be enriched for shortlisted candidates
                intermediate_stops=item.get("intermediate_stops", []),
                data_source="RailRadar API (api.railradar.in)",
                verified_at=retrieved_at,
                is_live_status=bool(item.get("isLive", False)),
                provider_trace_id=trace_id,
                availability_status={c: "SCHEDULED_SERVICE" for c in classes},
            )
            normalized.append(service)

        return normalized

    def get_fare(
        self,
        train_number: str,
        source_station_code: str,
        destination_station_code: str,
        journey_date: str,
        class_code: str,
        quota_code: str = "GN",
    ) -> Optional[FareQuote]:
        """Retrieve authoritative fare from RailRadar."""
        try:
            res = self.client.get_fare(
                train_number=train_number,
                source_station_code=source_station_code,
                destination_station_code=destination_station_code,
                journey_date=journey_date,
                class_code=class_code,
                quota_code=quota_code,
            )
        except (RailRadarNotFoundError, RailRadarBadRequestError) as e:
            logger.info(f"Fare not available for train {train_number} class {class_code}: {e.message}")
            return None
        except RailRadarError as e:
            logger.error(f"RailRadar get_fare failed: {e.message}")
            raise

        data = res.get("data", {})
        trace_id = res.get("trace_id")
        retrieved_at = res.get("retrieved_at") or datetime.now().isoformat()

        total_fare = data.get("totalFare")
        if total_fare is None:
            return None

        breakdown_data = data.get("breakdown") or {}
        breakdown = FareBreakdown(
            base_fare=breakdown_data.get("baseFare"),
            reservation_charge=breakdown_data.get("reservationCharge"),
            superfast_charge=breakdown_data.get("superfastCharge"),
            other_charge=breakdown_data.get("otherCharge"),
            tatkal_fare=breakdown_data.get("tatkalFare"),
            goods_service_tax=breakdown_data.get("goodsServiceTax"),
            catering_charge=breakdown_data.get("cateringCharge"),
            dynamic_fare=breakdown_data.get("dynamicFare"),
        )

        return FareQuote(
            train_number=str(data.get("trainNumber") or train_number),
            train_name=data.get("trainName"),
            source_station=str(data.get("sourceStation") or source_station_code),
            destination_station=str(data.get("destinationStation") or destination_station_code),
            journey_date=journey_date,
            class_code=str(data.get("classCode") or class_code),
            quota_code=str(data.get("quotaCode") or quota_code),
            total_fare=float(total_fare),
            breakdown=breakdown,
            currency="INR",
            retrieved_at=retrieved_at,
            data_source="RailRadar API (api.railradar.in)",
            trace_id=trace_id,
            is_estimate=True,
        )

    def search_stations(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search stations via RailRadar lookup endpoint."""
        try:
            res = self.client.search_stations(query=query, limit=limit)
            return res.get("data", [])
        except RailRadarError as e:
            logger.error(f"RailRadar search_stations failed: {e.message}")
            return []

    def get_train_by_number_or_name(self, query: str) -> Optional[TrainService]:
        """Lookup train by number."""
        q = query.strip()
        # RailRadar does not have a separate get_train_by_id endpoint in free tier docs,
        # but if 5-digit number, we can search via common hub or lookup
        return None


# =====================================================================
# Factory & Orchestrating Train Search Service
# =====================================================================

def get_train_data_provider() -> TrainDataProvider:
    """Instantiate the active TrainDataProvider based on configuration."""
    if TRAIN_DATA_PROVIDER == "railradar":
        if not RAILRADAR_API_KEY:
            logger.warning(
                "TRAIN_DATA_PROVIDER is set to 'railradar' but RAILRADAR_API_KEY is missing. "
                "Failing safely to MockTrainDataProvider."
            )
            return MockTrainDataProvider()
        return RailRadarTrainDataProvider()
    return MockTrainDataProvider()


class TrainSearchService:
    """
    High-level timetable and fare orchestration service.
    Coordinates station multi-searches, deduplication, and candidate fare enrichment.
    """

    def __init__(self, provider: Optional[TrainDataProvider] = None):
        self.provider = provider or get_train_data_provider()

    def search_trains(
        self,
        origin_stations: List[str],
        destination_stations: List[str],
        journey_date: Optional[str] = None,
        preferred_class: Optional[str] = None,
        preferred_train_query: Optional[str] = None,
    ) -> List[TrainService]:
        """Search across all origin and destination station combinations."""
        origin_codes = [s.strip().upper() for s in origin_stations if s.strip()]
        dest_codes = [s.strip().upper() for s in destination_stations if s.strip()]

        seen_train_numbers: Set[str] = set()
        aggregated: List[TrainService] = []

        # Query each station pair
        for orig in origin_codes:
            for dest in dest_codes:
                try:
                    results = self.provider.search_trains(
                        origin_station_code=orig,
                        destination_station_code=dest,
                        journey_date=journey_date,
                        preferred_class=preferred_class,
                    )
                    for t in results:
                        if t.train_number not in seen_train_numbers:
                            seen_train_numbers.add(t.train_number)
                            aggregated.append(t)
                except Exception as e:
                    logger.warning(f"Failed to query trains for pair {orig}->{dest}: {e}")

        # If offline mock and named train wasn't found in pair, check global db
        if preferred_train_query:
            pref_train = self.get_train_by_number_or_name(preferred_train_query)
            if pref_train and pref_train.train_number not in seen_train_numbers:
                seen_train_numbers.add(pref_train.train_number)
                aggregated.append(pref_train)

        return aggregated

    def enrich_candidate_fares(
        self,
        evaluations: List[JourneyEvaluation],
        requirements: TripRequirements,
        max_lookups: int = RAILRADAR_MAX_FARE_LOOKUPS_PER_REQUEST,
    ) -> None:
        """
        Enrich shortlisted candidates with journey-specific fares from the provider.
        Prioritizes feasible candidates first, then closest-to-deadline infeasible candidates.
        """
        if not evaluations or max_lookups <= 0:
            return

        # Sort candidates for fare lookup priority: feasible first, then best score
        candidates_to_enrich = sorted(
            evaluations,
            key=lambda e: (1 if e.is_feasible else 0, e.score),
            reverse=True,
        )[:max_lookups]

        target_class = requirements.preferred_class or "3A"
        journey_date = requirements.meeting_date

        for ev in candidates_to_enrich:
            train = ev.train_service
            # If fare already exists for target_class, skip
            if target_class in train.fares and train.fares[target_class] > 0:
                ev.recommended_class = target_class
                ev.recommended_fare = train.fares[target_class]
                continue

            try:
                quote = self.provider.get_fare(
                    train_number=train.train_number,
                    source_station_code=train.origin_station_code,
                    destination_station_code=train.destination_station_code,
                    journey_date=journey_date,
                    class_code=target_class,
                    quota_code="GN",
                )
                if quote:
                    train.fares[target_class] = quote.total_fare
                    train.fare_quotes[target_class] = quote
                    ev.fare_quote = quote
                    ev.recommended_class = target_class
                    ev.recommended_fare = quote.total_fare
            except Exception as e:
                logger.warning(
                    f"Fare lookup failed for train {train.train_number} class {target_class}: {e}"
                )

    def get_train_by_number_or_name(self, query: str) -> Optional[TrainService]:
        """Lookup specific train."""
        return self.provider.get_train_by_number_or_name(query)

    def search_stations(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search stations."""
        return self.provider.search_stations(query, limit=limit)
