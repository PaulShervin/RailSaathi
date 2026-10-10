"""
RailSathi AI — Journey Planner Data Models

Strictly typed Pydantic models for goal-based journey planning,
location resolution, train schedules, feasibility evaluations, and booking handoffs.
"""

from datetime import date, time, datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


class TripRequirements(BaseModel):
    """Structured travel requirements extracted from passenger query or form."""
    origin: str = Field(..., description="Starting city, town, or origin location (e.g., 'Bengaluru', 'Mysuru').")
    destination_venue: str = Field(..., description="Target venue or landmark name (e.g., 'Tidel Park', 'IIT Madras').")
    destination_address: str | None = Field(default=None, description="Street address or locality (e.g., 'Taramani, Chennai').")
    destination_city: str | None = Field(default=None, description="Resolved destination city (e.g., 'Chennai').")
    
    meeting_date: str = Field(..., description="Target meeting or arrival date in YYYY-MM-DD format.")
    meeting_time: str = Field(..., description="Target meeting start time in HH:MM 24-hour format.")
    timezone: str = Field(default="Asia/Kolkata", description="Timezone of the journey (default: Asia/Kolkata).")
    
    required_arrival_buffer_minutes: int = Field(
        default=45,
        ge=0,
        le=720,
        description="Desired buffer time at venue before the meeting starts (in minutes)."
    )
    
    preferred_train_name_or_number: str | None = Field(
        default=None,
        description="Explicit train name or 5-digit number preferred by the passenger (if any)."
    )
    preferred_class: str | None = Field(
        default=None,
        description="Preferred travel class code (e.g., '3A', '2A', '1A', 'CC', 'SL', '3E', '2S', 'EC')."
    )
    budget_min: float | None = Field(default=None, ge=0, description="Minimum budget in INR.")
    budget_max: float | None = Field(default=None, ge=0, description="Maximum budget in INR.")
    currency: str = Field(default="INR", description="Currency code (default: INR).")
    
    maximum_journey_duration_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Maximum acceptable journey duration in minutes."
    )
    maximum_transfers: int = Field(default=0, ge=0, description="Maximum acceptable train interchanges (default 0 for direct).")
    accessibility_requirements: list[str] = Field(default_factory=list, description="Specific accessibility requirements.")
    
    hard_constraints: list[str] = Field(
        default_factory=lambda: ["deadline", "arrival_buffer"],
        description="Non-negotiable constraints that must be satisfied for feasibility."
    )
    soft_preferences: list[str] = Field(
        default_factory=list,
        description="Preferences to maximize score when ranking feasible candidates."
    )
    missing_required_fields: list[str] = Field(
        default_factory=list,
        description="List of essential fields that could not be determined and need clarification."
    )
    assumptions_requiring_confirmation: list[str] = Field(
        default_factory=list,
        description="Assumptions made (e.g., default buffer) requiring user awareness."
    )

    @field_validator("preferred_class", mode="before")
    @classmethod
    def normalize_class(cls, v: Any) -> str | None:
        if isinstance(v, str):
            clean = v.strip().upper()
            return clean if clean else None
        return None


class GeocodedPlaceCandidate(BaseModel):
    """Normalized candidate place record returned by geocoding providers."""
    place_name: str
    formatted_address: str
    latitude: float
    longitude: float
    city: str | None = None
    state: str | None = None
    country: str = "India"
    provider: str = "Nominatim (OpenStreetMap)"
    provider_place_id: str | None = None
    confidence: float = 0.8
    is_ambiguous: bool = False
    retrieved_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class ResolvedLocation(BaseModel):
    """Geographic resolution for a venue or city."""
    query: str
    display_name: str
    city: str
    state: str = "India"
    country: str = "India"
    latitude: float | None = None
    longitude: float | None = None
    provider: str = "RailSathi Place Registry"
    provider_place_id: str | None = None
    confidence: float = 1.0
    resolved_address: str | None = None
    is_cached: bool = False
    requires_user_clarification: bool = False
    clarification_options: list[str] = Field(default_factory=list)
    candidates: list[GeocodedPlaceCandidate] = Field(default_factory=list)
    resolution_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    resolution_error: str | None = None


class StationCandidate(BaseModel):
    """A railway station candidate serving an origin or destination area."""
    station_code: str
    station_name: str
    city: str
    latitude: float
    longitude: float
    distance_to_venue_km: float | None = None
    estimated_last_mile_minutes: int | None = None
    last_mile_mode: str | None = None  # e.g., 'cab', 'auto', 'metro', 'transit'
    is_major_hub: bool = True
    station_type: str = "major_intercity_terminal"  # 'major_intercity_terminal', 'intercity_junction', 'intercity_halt', 'suburban_halt', 'metro'
    supports_intercity: bool = True
    provider: str = "RailSathi Station Registry"


class LastMileEstimate(BaseModel):
    """Last-mile journey estimate from railway station to venue."""
    origin_station_code: str
    destination_venue: str
    distance_km: float | None = None
    duration_minutes: int | None = None
    transit_mode: str = "cab"
    confidence: str = "verified_estimate"  # 'verified_estimate', 'cached_estimate', 'heuristic_estimate', 'unknown'
    provider: str = "RailSathi Transit Estimator"
    source_type: str = "heuristic_urban_model"  # 'routing_provider', 'heuristic_urban_model', 'cached_route'
    is_heuristic: bool = True
    is_cached: bool = False
    source_url: str = "https://enquiry.indianrail.gov.in"
    verified_at: str = "2026-10-10"


class IntermediateStop(BaseModel):
    """Intermediate station stop details."""
    station_code: str
    station_name: str
    arrival_time: str
    departure_time: str
    halt_minutes: int
    day_number: int = 1


class FareBreakdown(BaseModel):
    """Granular fare breakdown charges returned by RailRadar or tariff tables."""
    base_fare: float | None = None
    reservation_charge: float | None = None
    superfast_charge: float | None = None
    other_charge: float | None = None
    tatkal_fare: float | None = None
    goods_service_tax: float | None = None
    catering_charge: float | None = None
    dynamic_fare: float | None = None


class FareQuote(BaseModel):
    """Specific fare quote for a train, class, route, and date."""
    train_number: str
    train_name: str | None = None
    source_station: str
    destination_station: str
    journey_date: str
    class_code: str
    quota_code: str = "GN"
    total_fare: float
    breakdown: FareBreakdown | None = None
    currency: str = "INR"
    retrieved_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    data_source: str = "RailRadar API (api.railradar.in)"
    trace_id: str | None = None
    is_estimate: bool = True


class TrainService(BaseModel):
    """Authoritative train schedule and fare data."""
    train_number: str
    train_name: str
    origin_station_code: str
    origin_station_name: str
    destination_station_code: str
    destination_station_name: str
    departure_time: str  # HH:MM (24-hr)
    arrival_time: str    # HH:MM (24-hr)
    day_offset: int = 0  # 0 for same day, 1 for next day arrival
    duration_minutes: int
    runs_on_days: list[str] = Field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    classes: list[str] = Field(default_factory=list)
    fares: dict[str, float] = Field(default_factory=dict)
    fare_quotes: dict[str, FareQuote] = Field(default_factory=dict)
    intermediate_stops: list[dict] = Field(default_factory=list)
    data_source: str = "Indian Railways National Train Enquiry System (NTES)"
    verified_at: str = "2026-10-10"
    is_live_status: bool = False
    provider_trace_id: str | None = None
    availability_status: dict[str, str] = Field(default_factory=dict)  # e.g., {"3A": "SCHEDULED_SERVICE"}


class BookingHandoff(BaseModel):
    """Validated official booking handoff payload."""
    official_provider: str = "IRCTC (Indian Railway Catering and Tourism Corporation)"
    booking_url: str
    is_url_allowlisted: bool = True
    train_number: str
    train_name: str
    from_station_code: str
    to_station_code: str
    journey_date: str
    recommended_class: str
    estimated_fare_inr: float | None = None
    disclaimer: str = (
        "RailSathi AI provides booking guidance. Clicking this link redirects you to the official "
        "IRCTC portal to complete your reservation. No automated transactions are performed."
    )


class JourneyEvaluation(BaseModel):
    """Deterministic evaluation of a candidate train against passenger constraints."""
    candidate_id: str
    train_service: TrainService
    journey_date: str
    departure_datetime_iso: str
    arrival_datetime_iso: str
    meeting_datetime_iso: str
    
    last_mile_origin_station: str
    last_mile_destination_venue: str
    last_mile_duration_minutes: int | None
    last_mile_distance_km: float | None
    last_mile_mode: str | None
    
    latest_acceptable_station_arrival_iso: str
    actual_arrival_buffer_minutes: int | None
    
    is_feasible: bool
    is_preferred_train: bool = False
    class_match: bool = True
    budget_match: bool = True
    duration_match: bool = True
    
    hard_constraint_violations: list[str] = Field(default_factory=list)
    soft_preference_matches: list[str] = Field(default_factory=list)
    soft_preference_penalties: list[str] = Field(default_factory=list)
    
    score: float = 0.0
    rank: int = 0
    match_category: Literal["best_match", "feasible_alternative", "infeasible", "insufficient_data"]
    explanation: str
    recommended_class: str | None = None
    recommended_fare: float | None = None
    fare_quote: FareQuote | None = None
    booking_handoff: BookingHandoff | None = None



class ConnectingJourneyLeg(BaseModel):
    """Single leg of a multi-train connecting journey."""
    leg_number: int  # 1 or 2
    train_service: TrainService
    from_station_code: str
    from_station_name: str
    to_station_code: str
    to_station_name: str
    departure_datetime_iso: str
    arrival_datetime_iso: str
    duration_minutes: int
    recommended_class: str | None = None
    fare_quote: FareQuote | None = None
    booking_handoff: BookingHandoff | None = None


class ConnectingJourneyEvaluation(BaseModel):
    """Multi-leg train journey evaluation with transfer layover validation."""
    candidate_id: str
    leg_1: ConnectingJourneyLeg
    leg_2: ConnectingJourneyLeg
    interchange_station_code: str
    interchange_station_name: str
    layover_minutes: int
    total_journey_duration_minutes: int
    
    last_mile_origin_station: str
    last_mile_destination_venue: str
    last_mile_duration_minutes: int | None
    last_mile_distance_km: float | None
    
    departure_datetime_iso: str
    arrival_datetime_iso: str
    latest_acceptable_station_arrival_iso: str
    actual_arrival_buffer_minutes: int | None
    
    is_feasible: bool
    total_estimated_fare: float | None = None
    score: float = 0.0
    rank: int = 0
    match_category: Literal["best_match", "feasible_alternative", "infeasible", "insufficient_data"] = "feasible_alternative"
    explanation: str


class QuotaInfo(BaseModel):
    """Structured provider quota status attached to journey responses."""
    used_requests: int = 0
    remaining_requests: int = 0
    monthly_limit: int = 100
    reserve_held: int = 5
    reset_date: str | None = None
    reset_date_formatted: str | None = None
    source: str = "local_sqlite_durable"
    is_exhausted: bool = False
    usable_cached_results_exist: bool = False
    last_successful_retrieval_at: str | None = None


class JourneyPlanResponse(BaseModel):
    """Complete structured journey plan response."""
    status: Literal[
        "answered",
        "clarification_required",
        "no_feasible_journey",
        "insufficient_data",
        "provider_unavailable",
        "execution_limit_reached",
        "invalid_request",
        "monthly_quota_exhausted",
        "rate_limit_wait",
        "no_schedule_data",
    ]
    search_outcome: Literal[
        "feasible_options_found",
        "no_feasible_options",
        "search_data_unavailable",
        "quota_exhausted",
        "partial_results",
    ] | None = None
    summary: str
    trip_requirements: TripRequirements
    resolved_origin: ResolvedLocation | None = None
    resolved_destination: ResolvedLocation | None = None
    candidate_origin_stations: list[StationCandidate] = Field(default_factory=list)
    candidate_destination_stations: list[StationCandidate] = Field(default_factory=list)
    
    best_match: JourneyEvaluation | None = None
    feasible_alternatives: list[JourneyEvaluation] = Field(default_factory=list)
    infeasible_options: list[JourneyEvaluation] = Field(default_factory=list)
    connecting_options: list[ConnectingJourneyEvaluation] = Field(default_factory=list)
    
    selected_station: str | None = None
    station_selection_reason: str | None = None
    last_mile_distance: float | None = None
    last_mile_duration_minutes: int | None = None
    last_mile_source: str | None = None
    location_telemetry: dict[str, Any] = Field(default_factory=dict)
    quota_info: QuotaInfo | None = None
    
    clarification_question: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    tradeoff_explanation: str | None = None
    
    sources: list[dict] = Field(default_factory=list)
    trace_id: str
    trace: list[dict] = Field(default_factory=list)
    tool_calls_made: int = 0
    rounds_used: int = 0

