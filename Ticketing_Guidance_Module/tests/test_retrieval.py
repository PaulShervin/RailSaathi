"""
RailSathi AI — Knowledge Retrieval Engine Tests
"""

from backend.knowledge.retrieval import (
    search_guidance,
    normalize_query,
    _check_freshness,
    SUPPORTED_TOPICS,
)


def test_abbreviation_expansion():
    """Verify common railway abbreviations expand to expected keywords in normalize_query."""
    normalized_sl = normalize_query("SL")
    assert "sleeper" in normalized_sl.lower()

    normalized_3a = normalize_query("3A")
    assert "third" in normalized_3a.lower()

    normalized_rac = normalize_query("RAC")
    assert "cancellation" in normalized_rac.lower()

    normalized_wl = normalize_query("WL")
    assert "waitlist" in normalized_wl.lower()

    normalized_cnf = normalize_query("CNF")
    assert "confirmed" in normalized_cnf.lower()


def test_freshness_calculation():
    """Verify freshness check calculates days and stale threshold."""
    # Recent date
    fresh = _check_freshness("2026-10-01")
    assert not fresh["is_stale"]
    assert fresh["warning"] is None

    # Stale date (>180 days)
    stale = _check_freshness("2024-01-01")
    assert stale["is_stale"]
    assert "stale" in stale["warning"].lower() or "verified" in stale["warning"].lower()

    # None or invalid date
    none_date = _check_freshness(None)
    assert none_date["is_stale"]

    invalid_date = _check_freshness("invalid-date-format")
    assert invalid_date["is_stale"]


def test_search_guidance_fts_match(temp_db):
    """Verify full-text search retrieves relevant guidance with source attribution."""
    res = search_guidance(temp_db, query="Sleeper Class", limit=5)
    assert res["retrieval_status"] == "success"
    assert res["evidence_sufficient"] is True
    results = res["results"]
    assert len(results) > 0

    first = results[0]
    assert "answer_text" in first
    assert "source" in first
    assert first["source"] is not None
    assert "source_url" in first["source"]
    assert "retrieval_status" in first["source"]
    assert first["source"]["retrieval_status"] == "success"
    assert "freshness" in first
    assert "conditions" in first


def test_search_guidance_topic_filter(temp_db):
    """Verify topic filtering restricts results to the given topic."""
    res = search_guidance(temp_db, query="cancellation", topic="cancellation_refund")
    assert res["retrieval_status"] == "success"
    for r in res["results"]:
        assert r["topic"] == "cancellation_refund"


def test_search_guidance_abbreviation(temp_db):
    """Verify search expands abbreviations like RAC and returns matching records."""
    res = search_guidance(temp_db, query="RAC", limit=3)
    assert res["retrieval_status"] == "success"
    results = res["results"]
    assert len(results) > 0
    found_rac = any("RAC" in r["answer_text"] or "Reservation Against Cancellation" in r["answer_text"] for r in results)
    assert found_rac


def test_search_guidance_empty_query(temp_db):
    """Verify empty or whitespace query returns appropriate status and empty results."""
    res1 = search_guidance(temp_db, query="")
    assert res1["retrieval_status"] == "error"
    assert res1["results"] == []

    res2 = search_guidance(temp_db, query="   ")
    assert res2["retrieval_status"] == "error"
    assert res2["results"] == []


def test_search_guidance_no_match(temp_db):
    """Verify querying non-existent terms returns empty list and evidence_sufficient False."""
    res = search_guidance(temp_db, query="quantum hyperdrive interstellar")
    assert res["retrieval_status"] == "success"
    assert res["results"] == []
    assert res["evidence_sufficient"] is False
