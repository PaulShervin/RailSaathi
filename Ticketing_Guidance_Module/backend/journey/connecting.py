"""
RailSathi AI — Connecting Trains & Multi-Leg Journey Discovery Service

Discovers 1-transfer connecting train routes via verified railway interchange junctions.
Ensures minimum transfer layovers (>= 30 mins) and maximum connection window (<= 6 hours).
Evaluates feasibility of entire multi-leg journey against destination meeting deadlines and last-mile transit.
Validates train operating days, enforces official booking URL allowlists, and handles missing fares safely.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any, Set

from backend.journey.models import (
    TripRequirements,
    TrainService,
    LastMileEstimate,
    ConnectingJourneyLeg,
    ConnectingJourneyEvaluation,
    BookingHandoff,
    FareQuote,
)
from backend.journey.timetable import TrainSearchService
from backend.journey.booking import BookingHandoffService, is_url_safe_and_allowlisted
from backend.journey.location import STATION_REGISTRY

logger = logging.getLogger("railsaathi.journey.connecting")

# Common railway interchange junctions categorized by regional corridors
CORRIDOR_HUBS: Dict[str, List[str]] = {
    # Tamil Nadu & Kerala Corridors
    "CHENNAI_TO_SOUTH_TN": ["TPJ", "MDU", "SA", "ED"],
    "SOUTH_TN_TO_CHENNAI": ["TPJ", "MDU", "SA", "ED"],
    "BENGALURU_TO_TAMILNADU": ["KPD", "SA", "ED", "CBE"],
    "TAMILNADU_TO_BENGALURU": ["KPD", "SA", "ED", "CBE"],
    # North & Central Corridors
    "DELHI_TO_CENTRAL": ["AGC", "GWL", "CNB", "BPL"],
    "CENTRAL_TO_DELHI": ["AGC", "GWL", "CNB", "BPL"],
    # Western Corridors
    "MUMBAI_TO_SOUTH": ["PUNE", "GTL", "WADI"],
    "SOUTH_TO_MUMBAI": ["PUNE", "GTL", "WADI"],
    # Default Major Junctions in India
    "DEFAULT_HUBS": ["TPJ", "MDU", "SA", "ED", "KPD", "CBE", "BZA", "SC", "PUNE", "CNB", "BPL", "AGC", "GTL", "RU"]
}

# Minimum and maximum acceptable layover times between connecting trains (in minutes)
MIN_TRANSFER_LAYOVER_MINUTES = 30
MAX_TRANSFER_LAYOVER_MINUTES = 360  # 6 hours

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ConnectingTrainDiscoveryService:
    """Discovers, validates, and ranks 1-interchange connecting train routes."""

    def __init__(self, train_service: Optional[TrainSearchService] = None):
        self.train_service = train_service or TrainSearchService()
        self.booking_service = BookingHandoffService()

    def get_candidate_hubs(self, origin_codes: List[str], dest_codes: List[str]) -> List[str]:
        """Determine relevant intermediate junction hubs based on origin and destination."""
        candidate_hubs: set[str] = set()

        # Check if journey matches known corridors
        is_chennai_origin = any(c in ["MAS", "MS", "TBM"] for c in origin_codes)
        is_south_tn_dest = any(c in ["TEN", "MDU", "TPJ", "NCJ", "CAPE", "TCN"] for c in dest_codes)
        is_blr_origin = any(c in ["SBC", "SMVB", "YPR"] for c in origin_codes)
        is_delhi_origin = any(c in ["NDLS", "NZM", "DLI", "ANVT"] for c in origin_codes)

        if is_chennai_origin and is_south_tn_dest:
            candidate_hubs.update(CORRIDOR_HUBS["CHENNAI_TO_SOUTH_TN"])
        elif is_blr_origin:
            candidate_hubs.update(CORRIDOR_HUBS["BENGALURU_TO_TAMILNADU"])
        elif is_delhi_origin:
            candidate_hubs.update(CORRIDOR_HUBS["DELHI_TO_CENTRAL"])
        else:
            candidate_hubs.update(CORRIDOR_HUBS["DEFAULT_HUBS"])

        # Exclude origin and destination stations themselves from candidate hubs
        for c in origin_codes + dest_codes:
            candidate_hubs.discard(c)

        return list(candidate_hubs)

    def discover_connecting_journeys(
        self,
        origin_codes: List[str],
        dest_codes: List[str],
        requirements: TripRequirements,
        last_mile: Optional[LastMileEstimate] = None,
        max_results: int = 5,
    ) -> List[ConnectingJourneyEvaluation]:
        """
        Search for connecting trains via candidate intermediate hubs.
        Returns a ranked, deduplicated list of ConnectingJourneyEvaluation candidates.
        """
        meeting_date_obj = datetime.strptime(requirements.meeting_date, "%Y-%m-%d").date()
        meeting_dt = datetime.combine(
            meeting_date_obj,
            datetime.strptime(requirements.meeting_time, "%H:%M").time()
        )

        # Dates to search (previous day overnight + meeting date)
        search_dates = [requirements.meeting_date]
        prev_date = (meeting_date_obj - timedelta(days=1)).strftime("%Y-%m-%d")
        search_dates.insert(0, prev_date)

        hubs = self.get_candidate_hubs(origin_codes, dest_codes)
        logger.info(f"Searching connecting routes {origin_codes} -> Hubs({hubs}) -> {dest_codes}")

        connecting_candidates: List[ConnectingJourneyEvaluation] = []
        seen_candidate_keys: Set[str] = set()

        for hub_code in hubs:
            hub_name = STATION_REGISTRY.get(hub_code, {}).get("station_name", f"{hub_code} Junction")

            # Search Leg 1: Origin -> Hub across search dates
            leg1_trains: List[TrainService] = []
            for s_date in search_dates:
                try:
                    t1_list = self.train_service.search_trains(
                        origin_stations=origin_codes,
                        destination_stations=[hub_code],
                        journey_date=s_date,
                        preferred_class=requirements.preferred_class,
                    )
                    leg1_trains.extend(t1_list)
                except Exception as e:
                    logger.debug(f"Leg 1 search failed for hub {hub_code} on {s_date}: {e}")

            if not leg1_trains:
                continue

            # Search Leg 2: Hub -> Destination across search dates
            leg2_trains: List[TrainService] = []
            for s_date in search_dates:
                try:
                    t2_list = self.train_service.search_trains(
                        origin_stations=[hub_code],
                        destination_stations=dest_codes,
                        journey_date=s_date,
                        preferred_class=requirements.preferred_class,
                    )
                    leg2_trains.extend(t2_list)
                except Exception as e:
                    logger.debug(f"Leg 2 search failed for hub {hub_code} on {s_date}: {e}")

            if not leg2_trains:
                continue

            # Find valid pairs with feasible transfer layover
            for t1 in leg1_trains:
                for leg1_dep_date_str in search_dates:
                    try:
                        leg1_dep_d = datetime.strptime(leg1_dep_date_str, "%Y-%m-%d").date()
                        
                        # Validate Leg 1 running day
                        leg1_weekday = WEEKDAY_NAMES[leg1_dep_d.weekday()]
                        if t1.runs_on_days and leg1_weekday not in t1.runs_on_days:
                            continue

                        leg1_dep_dt = datetime.combine(
                            leg1_dep_d,
                            datetime.strptime(t1.departure_time, "%H:%M").time()
                        )
                        leg1_arr_dt = leg1_dep_dt + timedelta(minutes=t1.duration_minutes)

                        for t2 in leg2_trains:
                            for leg2_dep_date_str in search_dates:
                                try:
                                    leg2_dep_d = datetime.strptime(leg2_dep_date_str, "%Y-%m-%d").date()

                                    # Validate Leg 2 running day
                                    leg2_weekday = WEEKDAY_NAMES[leg2_dep_d.weekday()]
                                    if t2.runs_on_days and leg2_weekday not in t2.runs_on_days:
                                        continue

                                    leg2_dep_dt = datetime.combine(
                                        leg2_dep_d,
                                        datetime.strptime(t2.departure_time, "%H:%M").time()
                                    )

                                    # Layover calculation at hub (must be positive full datetime difference)
                                    layover_seconds = (leg2_dep_dt - leg1_arr_dt).total_seconds()
                                    layover_minutes = int(layover_seconds // 60)

                                    # Validate transfer window (30m <= layover <= 6h)
                                    if not (MIN_TRANSFER_LAYOVER_MINUTES <= layover_minutes <= MAX_TRANSFER_LAYOVER_MINUTES):
                                        continue

                                    # Leg 2 arrival at final destination station
                                    leg2_arr_dt = leg2_dep_dt + timedelta(minutes=t2.duration_minutes)
                                    total_journey_minutes = int((leg2_arr_dt - leg1_dep_dt).total_seconds() // 60)

                                    # Deduplication key
                                    cand_key = f"{t1.train_number}:{hub_code}:{t2.train_number}:{leg1_dep_dt.isoformat()}:{leg2_dep_dt.isoformat()}"
                                    if cand_key in seen_candidate_keys:
                                        continue
                                    seen_candidate_keys.add(cand_key)

                                    # Evaluate destination deadline feasibility
                                    lm_minutes = last_mile.duration_minutes if (last_mile and last_mile.duration_minutes is not None) else None
                                    
                                    if lm_minutes is None:
                                        is_feasible = False
                                        match_cat = "insufficient_data"
                                        actual_buffer = None
                                        latest_acceptable_arr_dt = meeting_dt - timedelta(
                                            minutes=requirements.required_arrival_buffer_minutes
                                        )
                                        explanation = (
                                            f"Connecting via {hub_name} ({t1.train_name} -> {t2.train_name}): "
                                            f"Last-mile transfer duration is unknown; feasibility indeterminate."
                                        )
                                    else:
                                        latest_acceptable_arr_dt = meeting_dt - timedelta(
                                            minutes=(requirements.required_arrival_buffer_minutes + lm_minutes)
                                        )
                                        venue_arrival_dt = leg2_arr_dt + timedelta(minutes=lm_minutes)
                                        actual_buffer = int((meeting_dt - venue_arrival_dt).total_seconds() // 60)

                                        if leg2_arr_dt <= latest_acceptable_arr_dt:
                                            is_feasible = True
                                            match_cat = "feasible_alternative"
                                            explanation = (
                                                f"Feasible connecting route via {hub_name}. "
                                                f"Transfer layover: {layover_minutes}m. "
                                                f"Arrives destination station at {leg2_arr_dt.strftime('%H:%M')} on {leg2_arr_dt.strftime('%d %b')}, "
                                                f"providing {actual_buffer}m buffer before your {requirements.meeting_time} meeting."
                                            )
                                        else:
                                            is_feasible = False
                                            match_cat = "infeasible"
                                            explanation = (
                                                f"Infeasible connecting route via {hub_name}. "
                                                f"Arrives at destination station at {leg2_arr_dt.strftime('%H:%M')} on {leg2_arr_dt.strftime('%d %b')}, "
                                                f"missing the required {requirements.meeting_time} deadline."
                                            )

                                    # Build verified booking handoffs for each leg using BookingHandoffService
                                    target_class = requirements.preferred_class or "3A"
                                    rec_class1 = target_class if (t1.classes and target_class in t1.classes) else (t1.classes[0] if t1.classes else "3A")
                                    rec_class2 = target_class if (t2.classes and target_class in t2.classes) else (t2.classes[0] if t2.classes else "3A")

                                    handoff_leg1 = self.booking_service.create_booking_handoff(
                                        train=t1,
                                        journey_date=leg1_dep_date_str,
                                        recommended_class=rec_class1,
                                        recommended_fare=t1.fares.get(rec_class1) if t1.fares else None,
                                    )

                                    handoff_leg2 = self.booking_service.create_booking_handoff(
                                        train=t2,
                                        journey_date=leg2_dep_date_str,
                                        recommended_class=rec_class2,
                                        recommended_fare=t2.fares.get(rec_class2) if t2.fares else None,
                                    )

                                    # Combined Fare Calculation: ONLY show total when BOTH leg fares are available
                                    fare1 = t1.fares.get(rec_class1) if (t1.fares and t1.fares.get(rec_class1)) else None
                                    fare2 = t2.fares.get(rec_class2) if (t2.fares and t2.fares.get(rec_class2)) else None
                                    total_fare = (fare1 + fare2) if (fare1 is not None and fare2 is not None and fare1 > 0 and fare2 > 0) else None

                                    cand_id = f"conn-{t1.train_number}-{hub_code}-{t2.train_number}-{leg1_dep_date_str}"

                                    conn_eval = ConnectingJourneyEvaluation(
                                        candidate_id=cand_id,
                                        leg_1=ConnectingJourneyLeg(
                                            leg_number=1,
                                            train_service=t1,
                                            from_station_code=t1.origin_station_code,
                                            from_station_name=t1.origin_station_name,
                                            to_station_code=t1.destination_station_code,
                                            to_station_name=t1.destination_station_name,
                                            departure_datetime_iso=leg1_dep_dt.isoformat(),
                                            arrival_datetime_iso=leg1_arr_dt.isoformat(),
                                            duration_minutes=t1.duration_minutes,
                                            recommended_class=rec_class1,
                                            booking_handoff=handoff_leg1,
                                        ),
                                        leg_2=ConnectingJourneyLeg(
                                            leg_number=2,
                                            train_service=t2,
                                            from_station_code=t2.origin_station_code,
                                            from_station_name=t2.origin_station_name,
                                            to_station_code=t2.destination_station_code,
                                            to_station_name=t2.destination_station_name,
                                            departure_datetime_iso=leg2_dep_dt.isoformat(),
                                            arrival_datetime_iso=leg2_arr_dt.isoformat(),
                                            duration_minutes=t2.duration_minutes,
                                            recommended_class=rec_class2,
                                            booking_handoff=handoff_leg2,
                                        ),
                                        interchange_station_code=hub_code,
                                        interchange_station_name=hub_name,
                                        layover_minutes=layover_minutes,
                                        total_journey_duration_minutes=total_journey_minutes,
                                        last_mile_origin_station=t2.destination_station_code,
                                        last_mile_destination_venue=requirements.destination_venue,
                                        last_mile_duration_minutes=lm_minutes,
                                        last_mile_distance_km=last_mile.distance_km if last_mile else None,
                                        departure_datetime_iso=leg1_dep_dt.isoformat(),
                                        arrival_datetime_iso=leg2_arr_dt.isoformat(),
                                        latest_acceptable_station_arrival_iso=latest_acceptable_arr_dt.isoformat(),
                                        actual_arrival_buffer_minutes=actual_buffer,
                                        is_feasible=is_feasible,
                                        total_estimated_fare=total_fare,
                                        score=(100.0 if is_feasible else 0.0) - (layover_minutes * 0.1),
                                        match_category=match_cat,
                                        explanation=explanation,
                                    )
                                    connecting_candidates.append(conn_eval)
                                except Exception as pair_err:
                                    logger.debug(f"Error evaluating connecting pair {t1.train_number} -> {t2.train_number}: {pair_err}")
                    except Exception as leg1_err:
                        logger.debug(f"Error evaluating leg1 date {leg1_dep_date_str}: {leg1_err}")

        # Sort: Feasible first, then highest score / least layover
        sorted_conns = sorted(
            connecting_candidates,
            key=lambda x: (1 if x.is_feasible else 0, x.score, -x.total_journey_duration_minutes),
            reverse=True,
        )

        # Assign ranks
        for idx, item in enumerate(sorted_conns[:max_results], 1):
            item.rank = idx

        return sorted_conns[:max_results]
