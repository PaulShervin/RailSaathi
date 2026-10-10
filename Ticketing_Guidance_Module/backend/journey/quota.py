"""
RailSathi AI — RailRadar Quota & Rate-Limit Enforcement System

Provides:
1. DurableRailRadarQuotaManager: SQLite-backed monthly quota tracking across process restarts,
   atomic quota reservations, configurable hard caps & reserve, reset policy, and provider reconciliation.
2. RailRadarPerMinuteLimiter: Sliding window / token bucket rate limiter with Retry-After header awareness,
   bounded exponential backoff with jitter, and thread-safe acquisition.
3. SingleFlightDeduplicator: Prevents duplicate concurrent in-flight HTTP requests.
4. Structured exception types and diagnostic metadata.
"""

import os
import time
import math
import random
import sqlite3
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, Callable

logger = logging.getLogger("railsaathi.railradar.quota")


def format_reset_time_with_timezone(reset_iso: Optional[str], tz_name: str = "Asia/Kolkata") -> str:
    """
    Format an ISO reset timestamp into a verified human-readable string with explicit timezone.
    E.g., '01 Nov 2026, 05:30 AM IST (+05:30)'.
    """
    if not reset_iso:
        return "Next monthly cycle (date unverified)"
    try:
        from zoneinfo import ZoneInfo
        iso_clean = reset_iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_clean)
        try:
            target_tz = ZoneInfo(tz_name)
            target_dt = dt.astimezone(target_tz)
            tz_abbr = target_dt.strftime("%Z")
            tz_offset = target_dt.strftime("%z")
            if tz_offset and len(tz_offset) == 5:
                tz_offset = f"{tz_offset[:3]}:{tz_offset[3:]}"
            return target_dt.strftime(f"%d %b %Y, %I:%M %p {tz_abbr} ({tz_offset})")
        except Exception:
            utc_dt = dt.astimezone(timezone.utc)
            return utc_dt.strftime("%d %b %Y, %H:%M UTC (+00:00)")
    except Exception:
        return str(reset_iso)


class RailRadarError(Exception):
    """Base exception for all RailRadar API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, trace_id: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.trace_id = trace_id


class RailRadarQuotaExhaustedError(RailRadarError):
    """Raised when monthly API quota is exhausted and no calls are permitted."""
    def __init__(
        self,
        message: str = "RailRadar monthly request quota exhausted.",
        used_requests: int = 0,
        monthly_limit: int = 100,
        remaining_requests: int = 0,
        reserve_held: int = 0,
        reset_date: Optional[str] = None,
        source: str = "local_sqlite_durable",
        trace_id: Optional[str] = None,
    ):
        super().__init__(message, status_code=429, trace_id=trace_id)
        self.error_code = "monthly_quota_exhausted"
        self.used_requests = used_requests
        self.monthly_limit = monthly_limit
        self.remaining_requests = remaining_requests
        self.reserve_held = reserve_held
        self.reset_date = reset_date
        self.source = source

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.error_code,
            "message": self.message,
            "used_requests": self.used_requests,
            "monthly_limit": self.monthly_limit,
            "remaining_requests": self.remaining_requests,
            "reserve_held": self.reserve_held,
            "reset_date": self.reset_date,
            "source": self.source,
        }


class RailRadarRateLimitWaitError(RailRadarError):
    """Raised when rate limiter cannot grant an immediate request token and waiting is disabled/exceeded."""
    def __init__(
        self,
        message: str = "RailRadar per-minute rate limit exceeded. Please wait.",
        wait_seconds: float = 0.0,
        retry_after: Optional[int] = None,
        trace_id: Optional[str] = None,
    ):
        super().__init__(message, status_code=429, trace_id=trace_id)
        self.error_code = "rate_limit_wait"
        self.wait_seconds = wait_seconds
        self.retry_after = retry_after

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.error_code,
            "message": self.message,
            "wait_seconds": self.wait_seconds,
            "retry_after": self.retry_after,
        }


# =====================================================================
# Quota & Usage Data Models
# =====================================================================

@dataclass
class QuotaUsageReport:
    """Snapshot of current RailRadar quota and accounting status."""
    period_id: str
    monthly_limit: int
    used_requests: int
    remaining_requests: int
    reserve_held: int
    available_for_standard: int
    reset_date: str
    source: str  # "local_sqlite_durable" or "provider_dashboard_reconciled"
    dashboard_confirmed_used: Optional[int] = None
    dashboard_last_synced_at: Optional[str] = None
    is_exhausted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "period_id": self.period_id,
            "monthly_limit": self.monthly_limit,
            "used_requests": self.used_requests,
            "remaining_requests": self.remaining_requests,
            "reserve_held": self.reserve_held,
            "available_for_standard": self.available_for_standard,
            "reset_date": self.reset_date,
            "source": self.source,
            "dashboard_confirmed_used": self.dashboard_confirmed_used,
            "dashboard_last_synced_at": self.dashboard_last_synced_at,
            "is_exhausted": self.is_exhausted,
        }


# =====================================================================
# Durable SQLite Quota Manager
# =====================================================================

class DurableRailRadarQuotaManager:
    """
    Persists RailRadar outbound request attempts in a durable SQLite database.
    
    Guarantees:
    - Thread-safe and multiprocess-safe atomic quota reservations via SQLite WAL mode & locks.
    - Counts all outbound HTTP attempts conservatively (including failed attempts & retries).
    - Preserves configurable emergency reserve for essential recovery/critical searches.
    - Manages monthly billing period cycles and confirmed provider reset dates.
    - Supports reconciliation with authoritative provider dashboard metrics.
    """

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        monthly_limit: int = 100,
        reserve_quota: int = 5,
        custom_reset_day: int = 1,
    ):
        if db_path is None:
            from backend.config import RAILRADAR_USAGE_DB_PATH
            self.db_path = Path(RAILRADAR_USAGE_DB_PATH)
        else:
            self.db_path = Path(db_path)

        self.monthly_limit = max(1, monthly_limit)
        self.reserve_quota = max(0, reserve_quota)
        self.custom_reset_day = max(1, min(28, custom_reset_day))
        self._lock = threading.Lock()

        # Ensure directory exists and schema initialized
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False,
            isolation_level=None,  # Autocommit / explicit transactions
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    def _init_db(self) -> None:
        """Create tables if not existing."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS quota_periods (
                        period_id TEXT PRIMARY KEY,
                        monthly_limit INTEGER NOT NULL,
                        used_requests INTEGER NOT NULL DEFAULT 0,
                        reserve_quota INTEGER NOT NULL DEFAULT 0,
                        reset_date TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'local_sqlite_durable',
                        dashboard_confirmed_used INTEGER,
                        dashboard_last_synced_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS outbound_attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        period_id TEXT NOT NULL,
                        endpoint TEXT NOT NULL,
                        method TEXT NOT NULL,
                        params_sanitized TEXT,
                        attempt_number INTEGER NOT NULL DEFAULT 1,
                        status_code INTEGER,
                        is_success INTEGER NOT NULL DEFAULT 0,
                        is_retry INTEGER NOT NULL DEFAULT 0,
                        error_type TEXT,
                        trace_id TEXT,
                        duration_ms REAL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(period_id) REFERENCES quota_periods(period_id)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_attempts_period ON outbound_attempts(period_id);")
            finally:
                conn.close()

    def get_current_period_id(self, now_dt: Optional[datetime] = None) -> str:
        """Calculate the current monthly billing period identifier (e.g. '2026-10')."""
        dt = now_dt or datetime.now(timezone.utc)
        return dt.strftime("%Y-%m")

    def get_period_reset_date_iso(self, period_id: str) -> str:
        """Calculate the ISO reset timestamp for the current monthly cycle."""
        try:
            year, month = map(int, period_id.split("-"))
            if month == 12:
                next_year = year + 1
                next_month = 1
            else:
                next_year = year
                next_month = month + 1
            reset_dt = datetime(next_year, next_month, self.custom_reset_day, 0, 0, 0, tzinfo=timezone.utc)
            return reset_dt.isoformat()
        except Exception:
            return ""

    def _ensure_period_row(self, conn: sqlite3.Connection, period_id: str) -> sqlite3.Row:
        """Ensure current monthly period record exists in database."""
        row = conn.execute("SELECT * FROM quota_periods WHERE period_id = ?", (period_id,)).fetchone()
        if row is None:
            now_iso = datetime.now(timezone.utc).isoformat()
            reset_date_iso = self.get_period_reset_date_iso(period_id)
            conn.execute(
                """
                INSERT OR IGNORE INTO quota_periods (
                    period_id, monthly_limit, used_requests, reserve_quota,
                    reset_date, source, created_at, updated_at
                ) VALUES (?, ?, 0, ?, ?, 'local_sqlite_durable', ?, ?)
                """,
                (period_id, self.monthly_limit, self.reserve_quota, reset_date_iso, now_iso, now_iso),
            )
            row = conn.execute("SELECT * FROM quota_periods WHERE period_id = ?", (period_id,)).fetchone()
        return row

    def get_usage_report(self, now_dt: Optional[datetime] = None) -> QuotaUsageReport:
        """Return full usage snapshot for current period."""
        period_id = self.get_current_period_id(now_dt)
        with self._lock:
            conn = self._get_connection()
            try:
                row = self._ensure_period_row(conn, period_id)
                used = int(row["used_requests"])
                limit = int(row["monthly_limit"])
                reserve = int(row["reserve_quota"])
                remaining = max(0, limit - used)
                avail_standard = max(0, limit - reserve - used)
                is_exhausted = remaining <= 0

                return QuotaUsageReport(
                    period_id=period_id,
                    monthly_limit=limit,
                    used_requests=used,
                    remaining_requests=remaining,
                    reserve_held=reserve,
                    available_for_standard=avail_standard,
                    reset_date=row["reset_date"],
                    source=row["source"],
                    dashboard_confirmed_used=row["dashboard_confirmed_used"],
                    dashboard_last_synced_at=row["dashboard_last_synced_at"],
                    is_exhausted=is_exhausted,
                )
            finally:
                conn.close()

    def check_quota_available(
        self,
        required_amount: int = 1,
        allow_reserve: bool = False,
    ) -> Tuple[bool, QuotaUsageReport]:
        """Check if quota is available without yet reserving."""
        report = self.get_usage_report()
        if allow_reserve:
            has_quota = report.remaining_requests >= required_amount
        else:
            has_quota = report.available_for_standard >= required_amount
        return has_quota, report

    def reserve_and_record_attempt(
        self,
        endpoint: str,
        method: str = "GET",
        params_sanitized: Optional[str] = None,
        attempt_number: int = 1,
        is_retry: bool = False,
        allow_reserve: bool = False,
    ) -> Tuple[int, QuotaUsageReport]:
        """
        Atomically reserve 1 request in SQLite and log the initial outbound attempt.
        Raises RailRadarQuotaExhaustedError if quota is depleted.
        Returns: (attempt_db_id, updated_report)
        """
        period_id = self.get_current_period_id()
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = self._ensure_period_row(conn, period_id)
                used = int(row["used_requests"])
                limit = int(row["monthly_limit"])
                reserve = int(row["reserve_quota"])

                effective_budget = limit if allow_reserve else (limit - reserve)
                if used + 1 > effective_budget:
                    conn.execute("ROLLBACK")
                    remaining = max(0, limit - used)
                    avail_std = max(0, limit - reserve - used)
                    raise RailRadarQuotaExhaustedError(
                        message=f"RailRadar monthly quota exhausted ({used}/{limit} requests used, {reserve} held in reserve).",
                        used_requests=used,
                        monthly_limit=limit,
                        remaining_requests=remaining,
                        reserve_held=reserve,
                        reset_date=row["reset_date"],
                        source=row["source"],
                    )

                # Atomically increment used_requests
                conn.execute(
                    "UPDATE quota_periods SET used_requests = used_requests + 1, updated_at = ? WHERE period_id = ?",
                    (now_iso, period_id),
                )

                # Record attempt record
                cur = conn.execute(
                    """
                    INSERT INTO outbound_attempts (
                        period_id, endpoint, method, params_sanitized,
                        attempt_number, is_retry, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (period_id, endpoint, method, params_sanitized or "", attempt_number, 1 if is_retry else 0, now_iso),
                )
                attempt_id = cur.lastrowid

                conn.execute("COMMIT")

                updated_used = used + 1
                updated_report = QuotaUsageReport(
                    period_id=period_id,
                    monthly_limit=limit,
                    used_requests=updated_used,
                    remaining_requests=max(0, limit - updated_used),
                    reserve_held=reserve,
                    available_for_standard=max(0, limit - reserve - updated_used),
                    reset_date=row["reset_date"],
                    source=row["source"],
                    dashboard_confirmed_used=row["dashboard_confirmed_used"],
                    dashboard_last_synced_at=row["dashboard_last_synced_at"],
                    is_exhausted=(limit - updated_used) <= 0,
                )
                return attempt_id, updated_report
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            finally:
                conn.close()

    def record_attempt_outcome(
        self,
        attempt_id: int,
        status_code: Optional[int],
        is_success: bool,
        duration_ms: float = 0.0,
        error_type: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        """Update the outbound attempt record with outcome diagnostics."""
        if attempt_id <= 0:
            return
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    UPDATE outbound_attempts
                    SET status_code = ?, is_success = ?, duration_ms = ?, error_type = ?, trace_id = ?
                    WHERE id = ?
                    """,
                    (status_code, 1 if is_success else 0, duration_ms, error_type or "", trace_id or "", attempt_id),
                )
            finally:
                conn.close()

    def reconcile_with_dashboard(
        self,
        dashboard_used: int,
        provider_reset_date: Optional[str] = None,
        sync_timestamp: Optional[str] = None,
    ) -> QuotaUsageReport:
        """
        Reconcile local count with authoritative provider dashboard count.
        Ensures local counter is never lower than actual dashboard confirmed consumption.
        """
        period_id = self.get_current_period_id()
        now_iso = sync_timestamp or datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = self._ensure_period_row(conn, period_id)
                current_used = int(row["used_requests"])

                reconciled_used = max(current_used, dashboard_used)
                reset_date = provider_reset_date or row["reset_date"]

                conn.execute(
                    """
                    UPDATE quota_periods
                    SET used_requests = ?,
                        reset_date = ?,
                        source = 'provider_dashboard_reconciled',
                        dashboard_confirmed_used = ?,
                        dashboard_last_synced_at = ?,
                        updated_at = ?
                    WHERE period_id = ?
                    """,
                    (reconciled_used, reset_date, dashboard_used, now_iso, now_iso, period_id),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

        return self.get_usage_report()

    def reset_quota_for_test(self, period_id: Optional[str] = None) -> None:
        """Reset quota counter for testing purposes."""
        target_period = period_id or self.get_current_period_id()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("UPDATE quota_periods SET used_requests = 0 WHERE period_id = ?", (target_period,))
                conn.execute("DELETE FROM outbound_attempts WHERE period_id = ?", (target_period,))
            finally:
                conn.close()


# =====================================================================
# In-Flight SingleFlight Request Deduplicator
# =====================================================================

class SingleFlightDeduplicator:
    """
    Ensures identical concurrent in-flight requests share a single outbound execution
    to prevent quota double-spending during burst traffic.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._in_flight: Dict[str, threading.Event] = {}
        self._results: Dict[str, Tuple[Any, Optional[Exception]]] = {}

    def execute_or_join(self, key: str, action: Callable[[], Any]) -> Any:
        """
        Execute action if first caller for key; otherwise block and return the winner's result.
        """
        with self._lock:
            if key in self._in_flight:
                event = self._in_flight[key]
                is_leader = False
            else:
                event = threading.Event()
                self._in_flight[key] = event
                is_leader = True

        if is_leader:
            res = None
            err = None
            try:
                res = action()
                return res
            except Exception as e:
                err = e
                raise
            finally:
                with self._lock:
                    self._results[key] = (res, err)
                    self._in_flight.pop(key, None)
                    event.set()
        else:
            # Follower: wait for leader
            event.wait(timeout=30.0)
            with self._lock:
                result_tuple = self._results.pop(key, None)
            if result_tuple is not None:
                res, err = result_tuple
                if err is not None:
                    raise err
                return res
            # Fallback: re-execute if event timed out
            return action()


# =====================================================================
# Thread-Safe Sliding Window Per-Minute Rate Limiter
# =====================================================================

class RailRadarPerMinuteLimiter:
    """
    Sliding-window per-minute rate limiter for RailRadar.
    
    Features:
    - Default 10 requests / 60 seconds (configurable).
    - Dynamic backoff respect for Retry-After headers from HTTP 429.
    - Thread-safe timestamps log with automated eviction.
    - Bounded exponential backoff with jitter on transient retries.
    - Injected clock_fn and sleep_fn support for simulated clock tests.
    """

    def __init__(
        self,
        rate_limit_per_minute: int = 10,
        window_seconds: float = 60.0,
        max_backoff_seconds: float = 10.0,
        clock_fn: Optional[Callable[[], float]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ):
        self.rate_limit_per_minute = max(1, rate_limit_per_minute)
        self.window_seconds = window_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.clock_fn = clock_fn or time.time
        self.sleep_fn = sleep_fn or time.sleep
        self._timestamps: list[float] = []
        self._retry_after_until: float = 0.0
        self._lock = threading.Lock()

    def set_rate_limit(self, limit: int) -> None:
        with self._lock:
            self.rate_limit_per_minute = max(1, limit)

    def note_retry_after(self, retry_after_seconds: int) -> None:
        """Enforce strict provider backoff when Retry-After is returned."""
        with self._lock:
            now = self.clock_fn()
            target_time = now + max(1, retry_after_seconds)
            if target_time > self._retry_after_until:
                self._retry_after_until = target_time

    def calculate_wait_time(self) -> float:
        """Calculate how many seconds must elapse before next request is permitted."""
        now = self.clock_fn()
        with self._lock:
            retry_wait = max(0.0, self._retry_after_until - now)

            # Evict timestamps older than window
            cutoff = now - self.window_seconds
            self._timestamps = [t for t in self._timestamps if t > cutoff]

            if len(self._timestamps) < self.rate_limit_per_minute:
                window_wait = 0.0
            else:
                oldest = self._timestamps[0]
                window_wait = max(0.0, (oldest + self.window_seconds) - now)

            return max(retry_wait, window_wait)

    def acquire(self, wait_if_needed: bool = True, max_wait_seconds: float = 10.0) -> float:
        """
        Acquire rate-limit token.
        If wait_if_needed is True, sleeps up to max_wait_seconds.
        Raises RailRadarRateLimitWaitError if wait duration exceeds threshold or wait disabled.
        Returns the duration waited in seconds.
        """
        total_waited = 0.0

        while True:
            wait_time = self.calculate_wait_time()
            if wait_time <= 0.001:
                with self._lock:
                    now = self.clock_fn()
                    cutoff = now - self.window_seconds
                    self._timestamps = [t for t in self._timestamps if t > cutoff]
                    if len(self._timestamps) < self.rate_limit_per_minute and now >= self._retry_after_until:
                        self._timestamps.append(now)
                        return total_waited

            if not wait_if_needed or (total_waited + wait_time) > max_wait_seconds:
                raise RailRadarRateLimitWaitError(
                    message=f"RailRadar rate limit reached. Next token in {wait_time:.2f}s.",
                    wait_seconds=wait_time,
                )

            sleep_chunk = min(wait_time + 0.05, 1.0)
            self.sleep_fn(sleep_chunk)
            total_waited += sleep_chunk

    def calculate_backoff_jitter(self, attempt: int, base_delay: float = 0.5) -> float:
        """Calculate bounded exponential backoff with full jitter for retries."""
        exp = min(self.max_backoff_seconds, base_delay * (2 ** max(0, attempt - 1)))
        jitter = random.uniform(0.1, exp)
        return min(self.max_backoff_seconds, jitter)
