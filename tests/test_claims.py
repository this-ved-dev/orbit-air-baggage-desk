import sqlite3
from datetime import datetime, timedelta

import pytest

import claims

NOW = datetime(2026, 11, 2, 8, 0)


def file(conn, **overrides):
    fields = {
        "passenger": "Ana Ruiz",
        "flight": "OA101",
        "claim_type": "lost",
        "tier": "gold",
        "note": "Blue suitcase",
        "by": "desk",
        "now": NOW,
    }
    fields.update(overrides)
    return claims.file_claim(conn, **fields)


def test_file_claim_stores_fields_with_status_open(conn):
    claim = claims.get_claim(conn, file(conn))

    assert claim["passenger"] == "Ana Ruiz"
    assert claim["flight"] == "OA101"
    assert claim["type"] == "lost"
    assert claim["tier"] == "gold"
    assert claim["note"] == "Blue suitcase"
    assert claim["status"] == "open"
    assert claim["agent"] is None
    assert datetime.fromisoformat(claim["filed_at"]) == NOW


@pytest.mark.parametrize("passenger", ["", "   "])
def test_blank_passenger_rejected(conn, passenger):
    with pytest.raises(claims.ClaimError, match="passenger"):
        file(conn, passenger=passenger)
    assert claims.list_claims(conn) == []


def test_blank_flight_rejected(conn):
    with pytest.raises(claims.ClaimError, match="flight"):
        file(conn, flight=" ")
    assert claims.list_claims(conn) == []


def test_unknown_type_rejected(conn):
    with pytest.raises(claims.ClaimError, match="type"):
        file(conn, claim_type="stolen")
    assert claims.list_claims(conn) == []


def test_unknown_tier_rejected(conn):
    with pytest.raises(claims.ClaimError, match="tier"):
        file(conn, tier="platinum")
    assert claims.list_claims(conn) == []


@pytest.mark.parametrize("tier, hours", [("gold", 4), ("silver", 24), ("standard", 72)])
def test_deadline_by_tier(conn, tier, hours):
    claim = claims.get_claim(conn, file(conn, tier=tier))
    assert datetime.fromisoformat(claim["deadline"]) == NOW + timedelta(hours=hours)


def test_filing_writes_history_entry(conn):
    claim_id = file(conn, by="maria")

    [entry] = claims.history(conn, claim_id)

    assert entry["old_status"] is None
    assert entry["new_status"] == "open"
    assert entry["changed_by"] == "maria"
    assert datetime.fromisoformat(entry["changed_at"]) == NOW


def test_list_filters_by_status_and_tier(conn):
    gold_open = file(conn, tier="gold")
    silver_open = file(conn, tier="silver")
    gold_assigned = file(conn, tier="gold")
    with conn:
        conn.execute("UPDATE claims SET status = 'assigned' WHERE id = ?", (gold_assigned,))

    def ids(**filters):
        return [c["id"] for c in claims.list_claims(conn, **filters)]

    assert ids() == [gold_open, silver_open, gold_assigned]
    assert ids(tier="gold") == [gold_open, gold_assigned]
    assert ids(status="open") == [gold_open, silver_open]
    assert ids(status="assigned", tier="gold") == [gold_assigned]


def test_list_rejects_unknown_filter_values(conn):
    with pytest.raises(claims.ClaimError, match="status"):
        claims.list_claims(conn, status="lost-forever")
    with pytest.raises(claims.ClaimError, match="tier"):
        claims.list_claims(conn, tier="platinum")


@pytest.mark.parametrize("column, value", [("type", "stolen"), ("tier", "platinum"), ("status", "lost-forever")])
def test_check_constraints_reject_bad_values(conn, column, value):
    row = {
        "passenger": "Ana Ruiz",
        "flight": "OA101",
        "type": "lost",
        "tier": "gold",
        "status": "open",
        "filed_at": NOW.isoformat(),
        "deadline": NOW.isoformat(),
    }
    row[column] = value
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(
            "INSERT INTO claims (passenger, flight, type, tier, status, filed_at, deadline) "
            "VALUES (:passenger, :flight, :type, :tier, :status, :filed_at, :deadline)",
            row,
        )
