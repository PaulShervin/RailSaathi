"""
RailSathi AI — Journey Planner Orchestrator

End-to-end deterministic pipeline for planning goal-based train journeys.
Connects requirement extraction, location resolution, timetable discovery,
feasibility evaluation, ranking, and official booking handoffs.
"""

import re
import uuid
import logging
from datetime import datetime, date, timedelta
from typing import Any

from backend.journey.models import (
    TripRequirements,
    ResolvedLocation,
    StationCandidate,
    LastMileEstimate,
    TrainService,
    JourneyEvaluation,
    JourneyPlanResponse,
    QuotaInfo,
)
from backend.journey.location import LocationResolutionService
from backend.journey.timetable import TrainSearchService
from backend.journey.feasibility import JourneyFeasibilityEvaluator
from backend.journey.ranking import JourneyRankingEngine
from backend.journey.connecting import ConnectingTrainDiscoveryService
from backend.journey.quota import format_reset_time_with_timezone
from backend.journey.railradar_client import (
    RailRadarError,
    RailRadarAuthError,
    RailRadarRateLimitError,
    RailRadarUnavailableError,
    RailRadarQuotaExhaustedError,
    RailRadarRateLimitWaitError,
)

logger = logging.getLogger("railsaathi.journey.planner")




from zoneinfo import ZoneInfo

# Supported Indian metro and regional cities
SUPPORTED_CITIES = [
    "chennai", "bengaluru", "bangalore", "delhi", "new delhi", "mumbai",
    "hyderabad", "secunderabad", "kolkata", "pune", "coimbatore", "mysuru",
    "mysore", "tirunelveli", "madurai", "tiruchirappalli", "trichy", "salem",
    "thiruvananthapuram", "trivandrum", "kochi", "ernakulam", "ahmedabad",
    "jaipur", "lucknow", "kanpur", "patna", "chandigarh"
]


def resolve_date_from_text(text: str, current_dt: datetime | None = None) -> str:
    """
    Deterministically resolve target journey/meeting date from natural language text.
    Uses Asia/Kolkata timezone and handles relative keywords, slash dates, month names, and ISO dates.
    """
    t_lower = text.strip().lower()
    
    # 1. Base reference date in Asia/Kolkata
    if current_dt is not None:
        if current_dt.tzinfo is None:
            now_ist = current_dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        else:
            now_ist = current_dt.astimezone(ZoneInfo("Asia/Kolkata"))
    else:
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        
    ref_date = now_ist.date()

    # 2. Relative keywords
    if "day after tomorrow" in t_lower:
        return (ref_date + timedelta(days=2)).strftime("%Y-%m-%d")
    if "tomorrow" in t_lower:
        return (ref_date + timedelta(days=1)).strftime("%Y-%m-%d")
    if "today" in t_lower or "tonight" in t_lower:
        return ref_date.strftime("%Y-%m-%d")

    # 3. Weekday references (e.g. "this friday", "next monday", "on wednesday")
    weekdays = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }
    weekday_match = re.search(r"\b(?:this|next|coming|on)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", t_lower)
    if weekday_match:
        target_wd = weekdays[weekday_match.group(1)]
        current_wd = ref_date.weekday()
        days_ahead = target_wd - current_wd
        if days_ahead <= 0:  # Target day already happened this week, move to next week
            days_ahead += 7
        if "next" in weekday_match.group(0) and days_ahead < 7:
            days_ahead += 7
        return (ref_date + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # 4. ISO date (YYYY-MM-DD)
    iso_date_match = re.search(r"\b(202\d-\d{2}-\d{2})\b", text)
    if iso_date_match:
        return iso_date_match.group(1)

    # 5. Slash or dash dates: DD/MM/YYYY, DD-MM-YYYY, or MM/DD/YYYY
    slash_match = re.search(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](202\d|\d{2})\b", text)
    if slash_match:
        p1 = int(slash_match.group(1))
        p2 = int(slash_match.group(2))
        raw_year = int(slash_match.group(3))
        year = raw_year if raw_year > 100 else 2000 + raw_year

        # Indian railway standard is DD/MM/YYYY. If p2 > 12, p1 is month (MM/DD/YYYY)
        if p2 > 12:
            month, day = p1, p2
        else:
            day, month = p1, p2

        try:
            parsed = date(year, month, day)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 6. Month name dates: "25 October 2026", "25th Oct", "11 Oct"
    month_match = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(?:\s+(202\d))?",
        t_lower
    )
    if month_match:
        day = int(month_match.group(1))
        month_str = month_match.group(2)[:3]
        year = int(month_match.group(3)) if month_match.group(3) else ref_date.year
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
        }
        m_num = months.get(month_str, 10)
        try:
            return f"{year:04d}-{m_num:02d}-{day:02d}"
        except Exception:
            pass

    # Fallback to tomorrow if no date specified
    return (ref_date + timedelta(days=1)).strftime("%Y-%m-%d")


def parse_requirements_from_text(text: str, current_dt: datetime | None = None) -> TripRequirements:
    """
    Deterministic rule-based requirement extractor from natural language prompts.
    Extracts origin, destination venue, date, time, buffer, preferred train, class, and budget.
    """
    t = text.strip()
    t_lower = t.lower()

    # 1. Origin extraction
    origin = "Bengaluru"  # default if not detected
    origin_matches = re.findall(
        r"(?:from|leaving|departing|travelling from|traveling from|start from)\s+([A-Za-z\s]+?)(?:\s+to|\s+at|\s+on|\.|\,|$)",
        t,
        re.IGNORECASE
    )
    if origin_matches:
        origin = origin_matches[0].strip().title()
    else:
        for c in SUPPORTED_CITIES:
            if f"from {c}" in t_lower:
                origin = c.title()
                break

    # 2. Destination Venue extraction
    destination_venue = "Tidel Park"
    venue_matches = re.findall(
        r"(?:meeting at|appointment at|event at|reaching|reach|destination|venue)\s+([A-Za-z0-9\s\,\-]+?)(?:\s+in|\s+at|\s+on|\s+before|\.|$)",
        t,
        re.IGNORECASE
    )
    if venue_matches:
        destination_venue = venue_matches[0].strip().title()
    elif "tidel park, pattabiram" in t_lower or "tidel park pattabiram" in t_lower:
        destination_venue = "Tidel Park, Pattabiram"
    elif "tidel park, chennai" in t_lower or "tidel park chennai" in t_lower:
        destination_venue = "Tidel Park, Chennai"
    elif "tidel park, coimbatore" in t_lower or "tidel park coimbatore" in t_lower:
        destination_venue = "Tidel Park, Coimbatore"
    elif "tidel park, madurai" in t_lower or "tidel park madurai" in t_lower:
        destination_venue = "Tidel Park, Madurai"
    elif "tidel park, trichy" in t_lower or "tidel park trichy" in t_lower or "tidel park tiruchirappalli" in t_lower:
        destination_venue = "Tidel Park, Tiruchirappalli"
    elif "tidel park" in t_lower:
        destination_venue = "Tidel Park"
    elif "iit madras" in t_lower:
        destination_venue = "IIT Madras"
    elif "whitefield" in t_lower:
        destination_venue = "Whitefield"
    elif "electronic city" in t_lower:
        destination_venue = "Electronic City"
    elif "cyber city" in t_lower:
        destination_venue = "Cyber City Gurugram"
    elif "bkc" in t_lower or "bandra kurla" in t_lower:
        destination_venue = "Bandra Kurla Complex (BKC)"
    elif "hitec city" in t_lower:
        destination_venue = "HITEC City"
    elif "tirunelveli" in t_lower:
        destination_venue = "Tirunelveli"

    # Destination City extraction
    dest_city = None
    for c in SUPPORTED_CITIES:
        if f"in {c}" in t_lower or f"to {c}" in t_lower:
            dest_city = c.title()
            break
    if not dest_city:
        for c in SUPPORTED_CITIES:
            if c in t_lower and c != origin.lower():
                dest_city = c.title()
                break

    # 3. Deterministic Date extraction
    meeting_date = resolve_date_from_text(text, current_dt=current_dt)

    # 4. Time extraction (e.g. 10:00 AM, 10 AM, 14:30)
    meeting_time = "10:00"
    time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", t_lower)
    if time_match:
        hour = int(time_match.group(1))
        mins = int(time_match.group(2)) if time_match.group(2) else 0
        ampm = time_match.group(3).replace(".", "")
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        meeting_time = f"{hour:02d}:{mins:02d}"
    else:
        # 24-hr format like 10:00 or 14:30
        time_24_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
        if time_24_match:
            meeting_time = f"{int(time_24_match.group(1)):02d}:{int(time_24_match.group(2)):02d}"

    # 5. Buffer minutes (e.g. "45 minutes early", "at least 1 hour early", "30 mins buffer")
    buffer_minutes = 45
    buffer_match = re.search(r"(\d+)\s*(?:minutes?|mins?)\s*(?:early|buffer|before)", t_lower)
    if buffer_match:
        buffer_minutes = int(buffer_match.group(1))
    elif "1 hour early" in t_lower or "an hour early" in t_lower:
        buffer_minutes = 60
    elif "2 hours early" in t_lower:
        buffer_minutes = 120

    # 6. Preferred Class (e.g. "AC 3-tier", "3A", "CC", "2A", "Sleeper", "SL")
    preferred_class = None
    if re.search(r"\b(ac\s*3[\s-]*tier|3a|3[\s-]*ac|third\s*ac)\b", t_lower):
        preferred_class = "3A"
    elif re.search(r"\b(ac\s*2[\s-]*tier|2a|2[\s-]*ac|second\s*ac)\b", t_lower):
        preferred_class = "2A"
    elif re.search(r"\b(ac\s*chair\s*car|cc|chair\s*car)\b", t_lower):
        preferred_class = "CC"
    elif re.search(r"\b(1a|1[\s-]*ac|first\s*ac)\b", t_lower):
        preferred_class = "1A"
    elif re.search(r"\b(sleeper|sl)\b", t_lower):
        preferred_class = "SL"
    elif re.search(r"\b(3e|3[\s-]*economy|ac\s*3\s*economy)\b", t_lower):
        preferred_class = "3E"

    # 7. Preferred Train (e.g. "Vande Bharat", "Shatabdi", "12678", "Lalbagh")
    preferred_train = None
    if "vande bharat" in t_lower:
        preferred_train = "Vande Bharat"
    elif "shatabdi" in t_lower:
        preferred_train = "Shatabdi"
    elif "brindavan" in t_lower:
        preferred_train = "Brindavan Express"
    elif "lalbagh" in t_lower:
        preferred_train = "Lalbagh Express"
    elif "kanyakumari" in t_lower:
        preferred_train = "Kanyakumari Express"
    elif "nellai" in t_lower:
        preferred_train = "Nellai Superfast"
    elif "ananthapuri" in t_lower:
        preferred_train = "Ananthapuri Express"
    elif "tiruchendur" in t_lower:
        preferred_train = "Tiruchendur Express"
    elif "chennai mail" in t_lower:
        preferred_train = "Chennai Mail"
    elif "rajdhani" in t_lower:
        preferred_train = "Rajdhani Express"
    
    # Train number pattern (5 digits)
    train_num_match = re.search(r"\b(1\d{4}|2\d{4})\b", t)
    if train_num_match:
        preferred_train = train_num_match.group(1)

    # 8. Budget constraints (e.g. "under 1500", "budget of 1000", "affordable")
    budget_max = None
    budget_match = re.search(r"(?:under|less than|budget of|max(?:imum)?|within|below)\s*(?:rs\.?|inr|₹)?\s*(\d+)", t_lower)
    if budget_match:
        budget_max = float(budget_match.group(1))

    soft_preferences = []
    if "affordable" in t_lower or "cheap" in t_lower:
        soft_preferences.append("prefer_affordable")
    if preferred_class:
        soft_preferences.append(f"prefer_class_{preferred_class}")
    if preferred_train:
        soft_preferences.append(f"prefer_train_{preferred_train}")

    missing_fields = []
    if not origin:
        missing_fields.append("origin")
    if not destination_venue:
        missing_fields.append("destination_venue")

    return TripRequirements(
        origin=origin,
        destination_venue=destination_venue,
        destination_city=dest_city,
        meeting_date=meeting_date,
        meeting_time=meeting_time,
        timezone="Asia/Kolkata",
        required_arrival_buffer_minutes=buffer_minutes,
        preferred_train_name_or_number=preferred_train,
        preferred_class=preferred_class,
        budget_max=budget_max,
        hard_constraints=["deadline", "arrival_buffer"],
        soft_preferences=soft_preferences,
        missing_required_fields=missing_fields,
    )


class JourneyPlanner:
    """End-to-end Goal-Based Train Journey Planner."""

    def __init__(self):
        self.location_service = LocationResolutionService()
        self.train_service = TrainSearchService()
        self.feasibility_evaluator = JourneyFeasibilityEvaluator()
        self.ranking_engine = JourneyRankingEngine()
        self.connecting_service = ConnectingTrainDiscoveryService(self.train_service)

    def _get_current_quota_info(self, usable_cached: bool = False) -> QuotaInfo:
        """Construct a QuotaInfo snapshot from the active train provider's client if available."""
        used = 0
        rem = 100
        limit = 100
        reserve = 5
        reset_date = None
        reset_formatted = None
        src = "local_sqlite_durable"
        is_ex = False
        last_retrieval = None

        if hasattr(self.train_service.provider, "client"):
            client = self.train_service.provider.client
            if hasattr(client, "get_quota_report"):
                try:
                    rep = client.get_quota_report()
                    if hasattr(rep, "used_requests") and isinstance(rep.used_requests, int):
                        used = rep.used_requests
                        rem = int(rep.remaining_requests)
                        limit = int(rep.monthly_limit)
                        reserve = int(rep.reserve_held)
                        if isinstance(rep.reset_date, str):
                            reset_date = rep.reset_date
                            reset_formatted = format_reset_time_with_timezone(reset_date)
                        if isinstance(rep.source, str):
                            src = rep.source
                        if hasattr(rep, "available_for_standard") and isinstance(rep.available_for_standard, int):
                            is_ex = rep.available_for_standard <= 0
                except Exception:
                    pass
            if hasattr(client, "last_successful_schedule_retrieval"):
                raw_retrieval = getattr(client, "last_successful_schedule_retrieval", None)
                if isinstance(raw_retrieval, str):
                    last_retrieval = raw_retrieval

        return QuotaInfo(
            used_requests=used,
            remaining_requests=rem,
            monthly_limit=limit,
            reserve_held=reserve,
            reset_date=reset_date,
            reset_date_formatted=reset_formatted,
            source=src,
            is_exhausted=is_ex,
            usable_cached_results_exist=usable_cached,
            last_successful_retrieval_at=last_retrieval,
        )

    def plan_journey(
        self,
        requirements: TripRequirements,
        trace_id: str | None = None,
    ) -> JourneyPlanResponse:
        """
        Execute full journey planning workflow:
        1. Check spatial conflicts between venue and destination city
        2. Resolve origin & destination locations
        3. Find candidate stations
        4. Search train schedules (including overnight departures)
        5. Calculate last mile & evaluate feasibility
        6. Discover connecting train routes via intermediate interchange hubs
        7. Rank candidates & synthesize recommendations
        """
        tid = trace_id or f"trace-plan-{uuid.uuid4().hex[:10]}"

        # Step 0: Detect Spatial Conflict between venue and destination city
        has_conflict, conflict_msg = self.location_service.detect_location_conflict(
            requirements.destination_venue,
            requirements.destination_city,
        )
        if has_conflict and conflict_msg:
            return JourneyPlanResponse(
                status="clarification_required",
                summary=conflict_msg,
                trip_requirements=requirements,
                resolved_origin=self.location_service.resolve_location(requirements.origin),
                resolved_destination=None,
                candidate_origin_stations=[],
                candidate_destination_stations=[],
                best_match=None,
                feasible_alternatives=[],
                infeasible_options=[],
                connecting_options=[],
                clarification_question=conflict_msg,
                missing_fields=["destination_venue_city_conflict"],
                tradeoff_explanation="Please clarify whether your destination is the metropolitan area of the venue or the specified city.",
                trace_id=tid,
                trace=[
                    {"stage": "spatial_conflict_check", "status": "conflict_detected", "details": conflict_msg}
                ],
                tool_calls_made=1,
                rounds_used=1,
            )

        # Step 1: Resolve Locations
        resolved_origin = self.location_service.resolve_location(requirements.origin)
        resolved_dest = self.location_service.resolve_location(
            requirements.destination_venue,
            context_city=requirements.destination_city
        )

        # Disambiguation / Clarification check for destination venue
        if resolved_dest.requires_user_clarification or resolved_dest.latitude is None:
            clarification_msg = (
                resolved_dest.resolution_error
                or f"Please clarify the exact location of '{requirements.destination_venue}'."
            )
            if resolved_dest.clarification_options:
                clarification_msg += "\n\nPossible options:\n" + "\n".join(f"• {opt}" for opt in resolved_dest.clarification_options)

            return JourneyPlanResponse(
                status="clarification_required",
                summary=clarification_msg,
                trip_requirements=requirements,
                resolved_origin=resolved_origin,
                resolved_destination=resolved_dest,
                candidate_origin_stations=[],
                candidate_destination_stations=[],
                best_match=None,
                feasible_alternatives=[],
                infeasible_options=[],
                connecting_options=[],
                clarification_question=clarification_msg,
                missing_fields=["destination_venue_disambiguation"],
                tradeoff_explanation="Multiple locations or unverified coordinates found for this venue. Please select or clarify your destination.",
                trace_id=tid,
                trace=[
                    {"stage": "venue_geocoding", "status": "clarification_required", "details": clarification_msg}
                ],
                location_telemetry={
                    "geocoding_requests": self.location_service.geocoding_requests_count,
                    "geocoding_cache_hits": self.location_service.geocoding_cache_hits_count,
                    "routing_requests": self.location_service.routing_requests_count,
                    "routing_cache_hits": self.location_service.routing_cache_hits_count,
                    "railradar_http_calls_for_location": 0,
                },
                tool_calls_made=1,
                rounds_used=1,
            )

        # Step 2: Find Candidate Stations
        origin_stations = self.location_service.find_nearby_stations(resolved_origin)
        dest_stations = self.location_service.find_nearby_stations(resolved_dest)

        if not origin_stations or not dest_stations:
            return self.ranking_engine.rank_and_assemble_plan(
                requirements=requirements,
                evaluations=[],
                resolved_origin=resolved_origin,
                resolved_destination=resolved_dest,
                candidate_origin_stations=origin_stations,
                candidate_destination_stations=dest_stations,
                trace_id=tid,
                tool_calls_made=3,
                rounds_used=1,
            )

        origin_codes = [s.station_code for s in origin_stations]
        dest_codes = [s.station_code for s in dest_stations]

        # Step 3: Search Verified Train Schedules (accounting for overnight departures)
        # For morning/early afternoon meetings (<= 13:00), also search the previous day's departures
        meeting_date_obj = datetime.strptime(requirements.meeting_date, "%Y-%m-%d").date()
        search_dates = [requirements.meeting_date]
        try:
            m_hour = int(requirements.meeting_time.split(":")[0])
            if m_hour <= 13:
                prev_date = (meeting_date_obj - timedelta(days=1)).strftime("%Y-%m-%d")
                search_dates.append(prev_date)
        except Exception:
            pass

        seen_train_keys: set[str] = set()
        candidate_trains: list[TrainService] = []

        try:
            for s_date in search_dates:
                try:
                    results = self.train_service.search_trains(
                        origin_stations=origin_codes,
                        destination_stations=dest_codes,
                        journey_date=s_date,
                        preferred_class=requirements.preferred_class,
                        preferred_train_query=requirements.preferred_train_name_or_number,
                    )
                    for t in results:
                        # Deduplicate by train number and origin-destination pair
                        t_key = f"{t.train_number}-{t.origin_station_code}-{t.destination_station_code}"
                        if t_key not in seen_train_keys:
                            seen_train_keys.add(t_key)
                            candidate_trains.append(t)
                except RailRadarQuotaExhaustedError as inner_quota_err:
                    if candidate_trains:
                        logger.warning(f"Quota exhausted during secondary search date {s_date}; continuing with {len(candidate_trains)} candidate trains.")
                        break
                    raise inner_quota_err

            # Also search for preferred train explicitly if named and not in initial batch
            if requirements.preferred_train_name_or_number:
                pref_t = self.train_service.get_train_by_number_or_name(
                    requirements.preferred_train_name_or_number
                )
                if pref_t and not any(t.train_number == pref_t.train_number for t in candidate_trains):
                    candidate_trains.append(pref_t)

        except RailRadarQuotaExhaustedError as quota_err:
            logger.warning(f"Monthly quota exhausted: {quota_err}")
            reset_formatted = format_reset_time_with_timezone(quota_err.reset_date)
            last_retrieval = None
            if hasattr(self.train_service.provider, "client") and hasattr(self.train_service.provider.client, "last_successful_schedule_retrieval"):
                last_retrieval = self.train_service.provider.client.last_successful_schedule_retrieval

            q_info = QuotaInfo(
                used_requests=quota_err.used_requests,
                remaining_requests=quota_err.remaining_requests,
                monthly_limit=quota_err.monthly_limit,
                reserve_held=quota_err.reserve_held,
                reset_date=quota_err.reset_date,
                reset_date_formatted=reset_formatted,
                source=quota_err.source,
                is_exhausted=True,
                usable_cached_results_exist=False,
                last_successful_retrieval_at=last_retrieval,
            )

            return JourneyPlanResponse(
                status="monthly_quota_exhausted",
                search_outcome="quota_exhausted",
                summary="Train data request budget exhausted (monthly quota exhausted). We could not verify whether a train meets your deadline. Cached results, if available, are shown separately.",
                trip_requirements=requirements,
                resolved_origin=resolved_origin,
                resolved_destination=resolved_dest,
                candidate_origin_stations=origin_stations,
                candidate_destination_stations=dest_stations,
                best_match=None,
                feasible_alternatives=[],
                infeasible_options=[],
                connecting_options=[],
                quota_info=q_info,
                tradeoff_explanation=(
                    f"Train data request budget exhausted ({quota_err.used_requests}/{quota_err.monthly_limit} requests used). "
                    f"Verified reset time: {reset_formatted}. Feasibility could not be verified because no usable cached schedules were found for {requirements.meeting_date}."
                ),
                trace_id=tid,
                trace=[
                    {"stage": "candidate_retrieval", "status": "monthly_quota_exhausted", "quota": quota_err.to_dict()}
                ],
                tool_calls_made=1,
                rounds_used=1,
            )
        except RailRadarRateLimitWaitError as wait_err:
            logger.warning(f"Rate limit wait triggered: {wait_err}")
            q_info = self._get_current_quota_info(usable_cached=False)
            return JourneyPlanResponse(
                status="rate_limit_wait",
                search_outcome="search_data_unavailable",
                summary=f"RailRadar per-minute rate limit active. Please wait {wait_err.wait_seconds:.1f}s before retrying.",
                trip_requirements=requirements,
                resolved_origin=resolved_origin,
                resolved_destination=resolved_dest,
                candidate_origin_stations=origin_stations,
                candidate_destination_stations=dest_stations,
                best_match=None,
                feasible_alternatives=[],
                infeasible_options=[],
                connecting_options=[],
                quota_info=q_info,
                tradeoff_explanation=f"Per-minute rate limit reached. Next token in {wait_err.wait_seconds:.2f}s.",
                trace_id=tid,
                trace=[
                    {"stage": "candidate_retrieval", "status": "rate_limit_wait", "wait_seconds": wait_err.wait_seconds}
                ],
                tool_calls_made=1,
                rounds_used=1,
            )
        except (RailRadarAuthError, RailRadarRateLimitError, RailRadarUnavailableError) as prov_err:
            logger.error(f"Train search provider failed: {prov_err}")
            q_info = self._get_current_quota_info(usable_cached=False)
            return JourneyPlanResponse(
                status="provider_unavailable",
                search_outcome="search_data_unavailable",
                summary=f"Upstream train data provider unavailable: {prov_err.message}",
                trip_requirements=requirements,
                resolved_origin=resolved_origin,
                resolved_destination=resolved_dest,
                candidate_origin_stations=origin_stations,
                candidate_destination_stations=dest_stations,
                best_match=None,
                feasible_alternatives=[],
                infeasible_options=[],
                connecting_options=[],
                quota_info=q_info,
                tradeoff_explanation=f"Provider error ({type(prov_err).__name__}): {prov_err.message}. Feasibility could not be verified.",
                trace_id=tid,
                trace=[
                    {"stage": "candidate_retrieval", "status": "provider_error", "error": str(prov_err)}
                ],
                tool_calls_made=1,
                rounds_used=1,
            )

        # If live search returned 0 train services across all corridors
        if not candidate_trains:
            q_info = self._get_current_quota_info(usable_cached=False)
            return JourneyPlanResponse(
                status="insufficient_data",
                search_outcome="search_data_unavailable",
                summary=f"No scheduled train services found between {requirements.origin} and {requirements.destination_venue} corridors for {requirements.meeting_date}.",
                trip_requirements=requirements,
                resolved_origin=resolved_origin,
                resolved_destination=resolved_dest,
                candidate_origin_stations=origin_stations,
                candidate_destination_stations=dest_stations,
                best_match=None,
                feasible_alternatives=[],
                infeasible_options=[],
                connecting_options=[],
                quota_info=q_info,
                tradeoff_explanation=(
                    f"The train timetable provider returned no train services between the candidate stations "
                    f"({', '.join(origin_codes)} to {', '.join(dest_codes)}) on {requirements.meeting_date}. "
                    f"Train feasibility could not be determined because no train schedules were available to evaluate."
                ),
                trace_id=tid,
                trace=[
                    {"stage": "candidate_retrieval", "status": "no_trains_found", "count": 0}
                ],
                tool_calls_made=len(origin_codes) * len(dest_codes) + 1,
                rounds_used=1,
            )

        # Step 4: Calculate Last-Mile & Evaluate Feasibility for Direct Trains
        evaluations: list[JourneyEvaluation] = []
        last_mile_ref = None
        for train in candidate_trains:
            # Calculate last mile from this train's destination station to the venue
            last_mile = self.location_service.estimate_last_mile(
                station_code=train.destination_station_code,
                destination_venue=requirements.destination_venue,
                venue_location=resolved_dest,
            )
            if last_mile_ref is None:
                last_mile_ref = last_mile

            ev = self.feasibility_evaluator.evaluate_candidate(
                train=train,
                requirements=requirements,
                last_mile=last_mile,
            )
            evaluations.append(ev)

        # Step 4.5: Bounded Fare Enrichment for Shortlisted Direct Candidates
        # Avoid fare lookup if quota is exhausted
        is_quota_depleted = False
        try:
            if hasattr(self.train_service.provider, "client") and hasattr(self.train_service.provider.client, "quota_manager"):
                qm = getattr(self.train_service.provider.client, "quota_manager")
                if hasattr(qm, "check_quota_available"):
                    check_res = qm.check_quota_available(1, allow_reserve=False)
                    if isinstance(check_res, tuple) and len(check_res) >= 2:
                        is_quota_depleted = not bool(check_res[0])
        except Exception:
            is_quota_depleted = False

        if not is_quota_depleted:
            try:
                self.train_service.enrich_candidate_fares(
                    evaluations=evaluations,
                    requirements=requirements,
                )
            except RailRadarQuotaExhaustedError:
                logger.warning("Quota exhausted during fare enrichment; continuing with schedule data")
            except Exception as fare_err:
                logger.warning(f"Fare enrichment skipped: {fare_err}")

        # Step 5: Discover Multi-Leg Connecting Trains via Intermediate Hubs
        # Explore connecting routes only when direct options cannot meet the hard constraints
        # or when explicitly requested, conserving API quota budget.
        has_feasible_direct = any(ev.is_feasible for ev in evaluations)
        connecting_options = []

        if not has_feasible_direct and not is_quota_depleted:
            if last_mile_ref is None and dest_codes:
                last_mile_ref = self.location_service.estimate_last_mile(
                    station_code=dest_codes[0],
                    destination_venue=requirements.destination_venue,
                    venue_location=resolved_dest,
                )

            try:
                connecting_options = self.connecting_service.discover_connecting_journeys(
                    origin_codes=origin_codes,
                    dest_codes=dest_codes,
                    requirements=requirements,
                    last_mile=last_mile_ref,
                    max_results=5,
                )
            except (RailRadarQuotaExhaustedError, RailRadarRateLimitWaitError, RailRadarError) as conn_err:
                logger.warning(f"Connecting trains lookup stopped due to quota/provider error: {conn_err}")

        # Step 6: Deterministic Ranking & Assembly
        response = self.ranking_engine.rank_and_assemble_plan(
            requirements=requirements,
            evaluations=evaluations,
            resolved_origin=resolved_origin,
            resolved_destination=resolved_dest,
            candidate_origin_stations=origin_stations,
            candidate_destination_stations=dest_stations,
            trace_id=tid,
            tool_calls_made=len(candidate_trains) + 4,
            rounds_used=1,
        )

        # Attach connecting train options
        response.connecting_options = connecting_options

        # Attach quota info
        any_cached_candidates = any("Cached" in (t.data_source or "") for t in candidate_trains)
        q_info = self._get_current_quota_info(usable_cached=any_cached_candidates)
        response.quota_info = q_info

        # If quota is exhausted but results were evaluated from cached schedules, inform passenger
        if q_info.is_exhausted and any_cached_candidates:
            if response.best_match:
                response.summary += " [Evaluated from cached schedule data; live request budget is exhausted]"
            if response.tradeoff_explanation:
                response.tradeoff_explanation += (
                    f" (Evaluated from cached schedule data because provider request quota is currently exhausted. "
                    f"Verified reset time: {q_info.reset_date_formatted})"
                )

        # If no feasible direct trains but feasible connecting options exist, inform passenger
        if response.status == "no_feasible_journey" and any(c.is_feasible for c in connecting_options):
            feasible_conns = [c for c in connecting_options if c.is_feasible]
            best_c = feasible_conns[0]
            response.summary = (
                f"No feasible direct trains met your exact deadline, but {len(feasible_conns)} feasible "
                f"connecting route(s) via {best_c.interchange_station_name} were found!"
            )

        # Attach structured privacy-safe trace
        response.trace = [
            {
                "stage": "date_resolution",
                "resolved_journey_date": requirements.meeting_date,
                "timezone": "Asia/Kolkata",
                "search_departure_dates": search_dates,
            },
            {
                "stage": "station_discovery",
                "origin_stations": origin_codes,
                "destination_stations": dest_codes,
            },
            {
                "stage": "candidate_retrieval",
                "direct_candidates_retrieved": len(candidate_trains),
                "evaluations_count": len(evaluations),
                "feasible_direct_count": len(response.feasible_alternatives) + (1 if response.best_match else 0),
                "infeasible_direct_count": len(response.infeasible_options),
                "connecting_options_count": len(connecting_options),
                "feasible_connecting_count": sum(1 for c in connecting_options if c.is_feasible),
            },
        ]

        response.location_telemetry = {
            "geocoding_requests": self.location_service.geocoding_requests_count,
            "geocoding_cache_hits": self.location_service.geocoding_cache_hits_count,
            "routing_requests": self.location_service.routing_requests_count,
            "routing_cache_hits": self.location_service.routing_cache_hits_count,
            "railradar_http_calls_for_location": 0,
        }

        return response


