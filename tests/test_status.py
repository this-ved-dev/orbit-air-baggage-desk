from datetime import datetime, timedelta

import pytest

import claims

NOW = datetime(2026, 11, 2, 8, 0)
LATER = NOW + timedelta(minutes=30)


def new_claim(conn):
    return claims.file_claim(conn, "Ana Ruiz", "OA101", "lost", "gold", by="desk", now=NOW)


def set_status(conn, claim_id, status):
    # Puts a claim straight into a starting status, so each test checks one change.
    with conn:
        conn.execute("UPDATE claims SET status = ? WHERE id = ?", (status, claim_id))


def status_of(conn, claim_id):
    return claims.get_claim(conn, claim_id)["status"]


def change(conn, claim_id, target):
    if target == "assigned":
        claims.assign(conn, claim_id, "Priya", by="desk", now=LATER)
    elif target == "resolved":
        claims.resolve(conn, claim_id, by="desk", now=LATER)
    elif target == "closed":
        claims.close(conn, claim_id, by="desk", now=LATER)


def test_assign_open_claim_records_agent(conn):
    claim_id = new_claim(conn)

    claims.assign(conn, claim_id, "Priya", by="desk", now=LATER)

    claim = claims.get_claim(conn, claim_id)
    assert claim["status"] == "assigned"
    assert claim["agent"] == "Priya"


def test_resolve_assigned_claim(conn):
    claim_id = new_claim(conn)
    set_status(conn, claim_id, "assigned")

    claims.resolve(conn, claim_id, by="desk", now=LATER)

    assert status_of(conn, claim_id) == "resolved"


def test_close_resolved_claim(conn):
    claim_id = new_claim(conn)
    set_status(conn, claim_id, "resolved")

    claims.close(conn, claim_id, by="desk", now=LATER)

    assert status_of(conn, claim_id) == "closed"


def test_allowed_changes_table_matches_spec():
    assert claims.ALLOWED == {
        "open": {"assigned", "escalated"},
        "assigned": {"resolved", "escalated"},
        "escalated": {"assigned", "resolved"},
        "resolved": {"closed"},
        "closed": set(),
    }


@pytest.mark.parametrize(
    "start, target",
    [
        ("open", "assigned"),
        ("assigned", "resolved"),
        ("escalated", "assigned"),
        ("escalated", "resolved"),
        ("resolved", "closed"),
    ],
)
def test_allowed_changes_work(conn, start, target):
    claim_id = new_claim(conn)
    set_status(conn, claim_id, start)

    change(conn, claim_id, target)

    assert status_of(conn, claim_id) == target


@pytest.mark.parametrize(
    "start, target",
    [
        ("open", "closed"),
        ("open", "resolved"),
        ("assigned", "closed"),
        ("resolved", "assigned"),
        ("closed", "assigned"),
        ("closed", "resolved"),
    ],
)
def test_disallowed_changes_rejected_and_claim_unchanged(conn, start, target):
    claim_id = new_claim(conn)
    set_status(conn, claim_id, start)

    with pytest.raises(claims.ClaimError, match=f"from {start} to {target}"):
        change(conn, claim_id, target)

    assert status_of(conn, claim_id) == start
    assert len(claims.history(conn, claim_id)) == 1  # only the filing entry


def test_full_lifecycle_writes_complete_history(conn):
    claim_id = new_claim(conn)
    claims.assign(conn, claim_id, "Priya", by="maria", now=NOW + timedelta(hours=1))
    claims.resolve(conn, claim_id, by="priya", now=NOW + timedelta(hours=2))
    claims.close(conn, claim_id, by="maria", now=NOW + timedelta(hours=3))

    rows = [
        (h["old_status"], h["new_status"], h["changed_by"], datetime.fromisoformat(h["changed_at"]))
        for h in claims.history(conn, claim_id)
    ]

    assert rows == [
        (None, "open", "desk", NOW),
        ("open", "assigned", "maria", NOW + timedelta(hours=1)),
        ("assigned", "resolved", "priya", NOW + timedelta(hours=2)),
        ("resolved", "closed", "maria", NOW + timedelta(hours=3)),
    ]


@pytest.mark.parametrize("agent", ["", "   "])
def test_blank_agent_rejected(conn, agent):
    claim_id = new_claim(conn)

    with pytest.raises(claims.ClaimError, match="agent"):
        claims.assign(conn, claim_id, agent, by="desk", now=LATER)

    assert status_of(conn, claim_id) == "open"


def test_unknown_claim_id_rejected(conn):
    with pytest.raises(claims.ClaimError, match="999"):
        claims.resolve(conn, 999, by="desk", now=LATER)
