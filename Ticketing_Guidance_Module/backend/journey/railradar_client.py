"""
RailSathi AI — RailRadar API Client

High-performance, secure, resilient client adapter for RailRadar (api.railradar.in).
Handles authentication, query building, bounded retries, rate limit awareness,
safe credential-redacted logging, response parsing, and tiered in-memory caching.
"""

import time
import re
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, quote

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    requests = None  # type: ignore

logger = logging.getLogger("railsaathi.railradar")


# =====================================================================
# Exceptions (Strict Typed Hierarchy with Safe Redacted Messages)
# =====================================================================

class RailRadarError(Exception):
    """Base exception for all RailRadar API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, trace_id: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.trace_id = trace_id


class RailRadarConfigurationError(RailRadarError):
    """Raised when RailRadar is selected but credentials or URLs are improperly configured."""
    pass


class RailRadarAuthError(RailRadarError):
    """Raised on HTTP 401 / 403 authentication or permission failures."""
    pass


class RailRadarBadRequestError(RailRadarError):
    """Raised on HTTP 400 invalid query parameters or bad request envelopes."""
    pass


class RailRadarNotFoundError(RailRadarError):
    """Raised on HTTP 404 when requested train, station, or fare record is absent."""
    pass


class RailRadarRateLimitError(RailRadarError):
    """Raised on HTTP 429 rate limit exhaustion or quota depletion."""
    def __init__(self, message: str, retry_after: Optional[int] = None, trace_id: Optional[str] = None):
        super().__init__(message, status_code=429, trace_id=trace_id)
        self.retry_after = retry_after


class RailRadarUnavailableError(RailRadarError):
    """Raised on HTTP 500 / 502 / 503 / 504 server outages."""
    pass


class RailRadarNetworkError(RailRadarError):
    """Raised on socket timeouts, DNS resolution failures, or connection drops."""
    pass


class RailRadarSchemaError(RailRadarError):
    """Raised when the response envelope or body does not match expected schema."""
    pass


# =====================================================================
# In-Memory Thread-Safe Tiered Cache
# =====================================================================

class RailRadarCache:
    """
    Tiered in-memory cache for RailRadar responses.
    Maintains independent TTLs for stations (static), schedules (hourly), and fares (30m).
    """

    def __init__(
        self,
        enabled: bool = True,
        ttl_stations: int = 86400,
        ttl_trains: int = 3600,
        ttl_fares: int = 1800,
        max_entries: int = 1000,
    ):
        self.enabled = enabled
        self.ttl_stations = ttl_stations
        self.ttl_trains = ttl_trains
        self.ttl_fares = ttl_fares
        self.max_entries = max_entries
        self._store: Dict[str, Tuple[float, Any, str]] = {}  # key -> (expiry_time, data, retrieval_iso)
        self._lock = threading.Lock()

    def _get_ttl(self, category: str) -> int:
        if category == "stations":
            return self.ttl_stations
        elif category == "trains":
            return self.ttl_trains
        elif category == "fares":
            return self.ttl_fares
        return 3600

    def get(self, category: str, key: str) -> Optional[Tuple[Any, str]]:
        """Retrieve cached item if enabled and not expired. Returns (data, retrieved_at_iso)."""
        if not self.enabled:
            return None

        full_key = f"{category}:{key}"
        with self._lock:
            entry = self._store.get(full_key)
            if not entry:
                return None
            expiry, data, retrieved_at = entry
            if time.time() > expiry:
                # Expired
                self._store.pop(full_key, None)
                return None
            return data, retrieved_at

    def set(self, category: str, key: str, data: Any) -> str:
        """Store item in cache with category TTL. Returns ISO timestamp of storage."""
        if not self.enabled:
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        full_key = f"{category}:{key}"
        ttl = self._get_ttl(category)
        expiry = time.time() + ttl
        retrieved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with self._lock:
            if len(self._store) >= self.max_entries:
                # Evict 10% oldest
                keys_to_remove = sorted(self._store.keys(), key=lambda k: self._store[k][0])[: max(1, self.max_entries // 10)]
                for k in keys_to_remove:
                    self._store.pop(k, None)
            self._store[full_key] = (expiry, data, retrieved_at)

        return retrieved_at

    def clear(self) -> None:
        """Purge all entries from the cache."""
        with self._lock:
            self._store.clear()


# =====================================================================
# RailRadar API Client Adapter
# =====================================================================

class RailRadarClient:
    """
    Production-grade client for RailRadar API.
    
    Supported Endpoints:
    - Trains Between Stations: GET /v1/trains/between/{from}/{to}
    - Station Lookup / Autocomplete: GET /v1/lookup/search/stations
    - Train Fare Calculator: GET /v1/trains/{number}/fare
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.railradar.in",
        timeout_seconds: float = 10.0,
        max_retries: int = 1,
        cache_enabled: bool = True,
        ttl_stations: int = 86400,
        ttl_trains: int = 3600,
        ttl_fares: int = 1800,
        session: Optional[Any] = None,
    ):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://api.railradar.in").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, min(max_retries, 3))

        self.cache = RailRadarCache(
            enabled=cache_enabled,
            ttl_stations=ttl_stations,
            ttl_trains=ttl_trains,
            ttl_fares=ttl_fares,
        )

        # Internal performance & telemetry metrics
        self.metrics = {
            "train_searches_made": 0,
            "station_searches_made": 0,
            "fare_lookups_made": 0,
            "cache_hits": 0,
            "api_errors": 0,
            "last_request_time": None,
        }
        self._metrics_lock = threading.Lock()

        # Initialize HTTP Session
        if session is not None:
            self._session = session
        elif requests is not None:
            self._session = requests.Session()
            adapter = HTTPAdapter(
                max_retries=0,  # We manage bounded retries explicitly with backoff & Retry-After
                pool_connections=10,
                pool_maxsize=20,
            )
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)
        else:
            self._session = None

    def _increment_metric(self, metric_name: str) -> None:
        with self._metrics_lock:
            self.metrics[metric_name] = self.metrics.get(metric_name, 0) + 1
            self.metrics["last_request_time"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def get_metrics(self) -> Dict[str, Any]:
        """Return shallow copy of internal usage metrics."""
        with self._metrics_lock:
            return dict(self.metrics)

    def _get_headers(self) -> Dict[str, str]:
        """Construct sanitized request headers."""
        if not self.api_key:
            raise RailRadarConfigurationError(
                "RAILRADAR_API_KEY is not configured. Please set RAILRADAR_API_KEY in your environment or .env file."
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "RailSathi-AI/1.0 (Goal-Based Train Journey Planner)",
        }

    def _sanitize_log_url(self, url: str) -> str:
        """Redact sensitive query parameters if any."""
        return re.sub(r"(key|token|auth)=[^&]+", r"\1=[REDACTED]", url)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Execute an HTTP request against the RailRadar API with bounded retry logic.
        Returns: (parsed_json_dict, trace_id)
        """
        if self._session is None:
            raise RailRadarError("Python 'requests' library is not available.")

        url = f"{self.base_url}{path}"
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        headers = self._get_headers()

        attempts = 0
        max_attempts = 1 + self.max_retries
        last_exception: Optional[Exception] = None

        while attempts < max_attempts:
            attempts += 1
            try:
                logger.debug(f"RailRadar HTTP {method} {self._sanitize_log_url(url)} (attempt {attempts}/{max_attempts})")
                
                resp = self._session.request(
                    method=method,
                    url=url,
                    params=clean_params,
                    headers=headers,
                    timeout=(3.0, self.timeout_seconds),  # (connect_timeout, read_timeout)
                )

                status_code = resp.status_code
                trace_id: Optional[str] = resp.headers.get("X-Trace-Id") or resp.headers.get("x-request-id")

                # Try parsing JSON body safely
                try:
                    body = resp.json() if resp.text else {}
                except Exception as json_err:
                    body = {}
                    if status_code >= 400:
                        raise RailRadarSchemaError(
                            f"RailRadar returned invalid JSON (HTTP {status_code})",
                            status_code=status_code,
                            trace_id=trace_id,
                        )

                if isinstance(body, dict) and "meta" in body and isinstance(body["meta"], dict):
                    trace_id = body["meta"].get("traceId", trace_id)

                # --- 200 OK ---
                if status_code == 200:
                    if isinstance(body, dict):
                        # Verify success envelope if present
                        if "success" in body and body["success"] is False:
                            err_msg = body.get("message") or body.get("error") or "RailRadar returned success=false"
                            raise RailRadarBadRequestError(f"RailRadar API error: {err_msg}", status_code=200, trace_id=trace_id)
                        return body, trace_id
                    raise RailRadarSchemaError("Unexpected response body type: expected JSON object", status_code=200, trace_id=trace_id)

                # --- 400 Bad Request ---
                if status_code == 400:
                    self._increment_metric("api_errors")
                    msg = body.get("message") or body.get("error") or "Invalid request parameters"
                    raise RailRadarBadRequestError(f"RailRadar Bad Request: {msg}", status_code=400, trace_id=trace_id)

                # --- 401 / 403 Unauthorized ---
                if status_code in (401, 403):
                    self._increment_metric("api_errors")
                    raise RailRadarAuthError(
                        "RailRadar authentication failed. Please verify that your RAILRADAR_API_KEY is valid and active.",
                        status_code=status_code,
                        trace_id=trace_id,
                    )

                # --- 404 Not Found ---
                if status_code == 404:
                    self._increment_metric("api_errors")
                    msg = body.get("message") or body.get("error") or "Resource not found"
                    raise RailRadarNotFoundError(f"RailRadar Not Found: {msg}", status_code=404, trace_id=trace_id)

                # --- 429 Rate Limited ---
                if status_code == 429:
                    self._increment_metric("api_errors")
                    retry_after_hdr = resp.headers.get("Retry-After")
                    retry_after_sec = int(retry_after_hdr) if retry_after_hdr and retry_after_hdr.isdigit() else None
                    msg = body.get("message") or "RailRadar rate limit or quota exceeded"
                    raise RailRadarRateLimitError(f"RailRadar Rate Limit Exceeded: {msg}", retry_after=retry_after_sec, trace_id=trace_id)

                # --- 500 / 502 / 503 / 504 Transient Server Errors ---
                if status_code in (500, 502, 503, 504):
                    self._increment_metric("api_errors")
                    if attempts < max_attempts:
                        logger.warning(f"RailRadar transient server error {status_code}. Retrying ({attempts}/{max_attempts})...")
                        time.sleep(0.5 * attempts)
                        continue
                    raise RailRadarUnavailableError(
                        f"RailRadar server unavailable (HTTP {status_code})",
                        status_code=status_code,
                        trace_id=trace_id,
                    )

                # Other HTTP errors
                self._increment_metric("api_errors")
                raise RailRadarError(
                    f"RailRadar request failed with HTTP {status_code}",
                    status_code=status_code,
                    trace_id=trace_id,
                )

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as net_err:
                last_exception = net_err
                self._increment_metric("api_errors")
                if attempts < max_attempts:
                    logger.warning(f"RailRadar network timeout/connection error: {type(net_err).__name__}. Retrying ({attempts}/{max_attempts})...")
                    time.sleep(0.5 * attempts)
                    continue
                break
            except (RailRadarAuthError, RailRadarBadRequestError, RailRadarNotFoundError, RailRadarRateLimitError):
                # Never retry deterministic client/auth/quota errors
                raise
            except RailRadarError:
                raise
            except Exception as unk_err:
                self._increment_metric("api_errors")
                raise RailRadarError(f"Unexpected RailRadar client error: {type(unk_err).__name__}: {str(unk_err)}")

        # If loop exited on network error
        if last_exception is not None:
            raise RailRadarNetworkError(
                f"RailRadar network connection failed after {max_attempts} attempts: {type(last_exception).__name__}"
            )
        raise RailRadarError("RailRadar request failed unexpectedly.")

    # =================================================================
    # Public API Operations
    # =================================================================

    def search_trains(
        self,
        origin_station_code: str,
        destination_station_code: str,
        journey_date: Optional[str] = None,
        train_type: Optional[str] = None,
        category: Optional[str] = None,
        by_city: Optional[bool] = None,
        live: bool = False,
    ) -> Dict[str, Any]:
        """
        Search trains between two railway stations.
        Endpoint: GET /v1/trains/between/{from}/{to}
        """
        src = origin_station_code.strip().upper()
        dst = destination_station_code.strip().upper()

        if not re.match(r"^[A-Z0-9]{2,6}$", src):
            raise RailRadarBadRequestError(f"Invalid origin station code: '{origin_station_code}'")
        if not re.match(r"^[A-Z0-9]{2,6}$", dst):
            raise RailRadarBadRequestError(f"Invalid destination station code: '{destination_station_code}'")

        if journey_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", journey_date):
            raise RailRadarBadRequestError(f"Invalid journey_date format: '{journey_date}'. Expected YYYY-MM-DD.")

        cache_key = f"{src}:{dst}:{journey_date or 'any'}:{train_type or 'all'}:{live}"
        cached = self.cache.get("trains", cache_key)
        if cached is not None:
            self._increment_metric("cache_hits")
            data, retrieved_at = cached
            return {"data": data, "cached": True, "retrieved_at": retrieved_at}

        self._increment_metric("train_searches_made")
        path = f"/v1/trains/between/{quote(src)}/{quote(dst)}"
        params: Dict[str, Any] = {}
        if journey_date:
            params["date"] = journey_date
        if train_type:
            params["type"] = train_type
        if category:
            params["category"] = category
        if by_city is not None:
            params["byCity"] = "true" if by_city else "false"
        if live:
            params["live"] = "true"

        resp_body, trace_id = self._request("GET", path, params)
        data = resp_body.get("data", {})

        retrieved_at = self.cache.set("trains", cache_key, data)
        return {
            "data": data,
            "meta": resp_body.get("meta", {}),
            "trace_id": trace_id,
            "cached": False,
            "retrieved_at": retrieved_at,
        }

    def search_stations(
        self,
        query: str,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Lookup stations by name or code.
        Endpoint: GET /v1/lookup/search/stations
        """
        q = query.strip()
        if not q:
            return {"data": [], "cached": False}

        valid_limit = 10
        if limit in (5, 10, 20, 50):
            valid_limit = limit
        elif limit <= 5:
            valid_limit = 5
        elif limit <= 20:
            valid_limit = 20
        else:
            valid_limit = 50

        cache_key = f"{q.upper()}:{valid_limit}"
        cached = self.cache.get("stations", cache_key)
        if cached is not None:
            self._increment_metric("cache_hits")
            data, retrieved_at = cached
            return {"data": data, "cached": True, "retrieved_at": retrieved_at}

        self._increment_metric("station_searches_made")
        path = "/v1/lookup/search/stations"
        params = {"q": q, "limit": valid_limit}

        resp_body, trace_id = self._request("GET", path, params)
        data = resp_body.get("data", [])

        retrieved_at = self.cache.set("stations", cache_key, data)
        return {
            "data": data,
            "meta": resp_body.get("meta", {}),
            "trace_id": trace_id,
            "cached": False,
            "retrieved_at": retrieved_at,
        }

    def get_fare(
        self,
        train_number: str,
        source_station_code: str,
        destination_station_code: str,
        journey_date: str,
        class_code: str,
        quota_code: str = "GN",
    ) -> Dict[str, Any]:
        """
        Calculate journey-specific fare for a train, class, and date.
        Endpoint: GET /v1/trains/{number}/fare
        """
        t_num = train_number.strip()
        src = source_station_code.strip().upper()
        dst = destination_station_code.strip().upper()
        cls_code = class_code.strip().upper()
        q_code = (quota_code or "GN").strip().upper()

        if not t_num:
            raise RailRadarBadRequestError("Missing train_number for fare calculation")
        if not re.match(r"^[A-Z0-9]{2,6}$", src):
            raise RailRadarBadRequestError(f"Invalid source station code: '{source_station_code}'")
        if not re.match(r"^[A-Z0-9]{2,6}$", dst):
            raise RailRadarBadRequestError(f"Invalid destination station code: '{destination_station_code}'")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", journey_date):
            raise RailRadarBadRequestError(f"Invalid journey_date format: '{journey_date}'. Expected YYYY-MM-DD.")

        cache_key = f"{t_num}:{src}:{dst}:{journey_date}:{cls_code}:{q_code}"
        cached = self.cache.get("fares", cache_key)
        if cached is not None:
            self._increment_metric("cache_hits")
            data, retrieved_at = cached
            return {"data": data, "cached": True, "retrieved_at": retrieved_at}

        self._increment_metric("fare_lookups_made")
        path = f"/v1/trains/{quote(t_num)}/fare"
        params = {
            "source": src,
            "destination": dst,
            "journeyDate": journey_date,
            "classCode": cls_code,
            "quotaCode": q_code,
        }

        resp_body, trace_id = self._request("GET", path, params)
        data = resp_body.get("data", {})

        retrieved_at = self.cache.set("fares", cache_key, data)
        return {
            "data": data,
            "meta": resp_body.get("meta", {}),
            "trace_id": trace_id,
            "cached": False,
            "retrieved_at": retrieved_at,
        }
