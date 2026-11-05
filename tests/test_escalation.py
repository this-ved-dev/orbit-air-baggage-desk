import sqlite3
from datetime import datetime, timedelta

import pytest

import claims

FILED = datetime(2026, 11, 2, 8, 0)
GOLD_DEADLINE = FILED + timedelta(hours=4)
MINUTE = timedelta(minutes=1)


def new_claim(conn, tier="gold"):
    return claims.file_claim(conn, "Ana Ruiz", "OA101", "lost", tier, by="desk", now=FILED)


def set_status(conn, claim_id, status):
    with conn:
        conn.execute("UPDATE claims SET status = ? WHERE id = ?", (status, claim_id))


def status_of(conn, claim_id):
    return claims.get_claim(conn, claim_id)["status"]


def fail_history_writes(conn):
    conn.execute(
        "CREATE TRIGGER fail_history BEFORE INSERT ON history "
        "BEGIN SELECT RAISE(ABORT, 'history write failed'); END"
    )


def test_not_overdue_one_minute_before_deadline():
    assert claims.is_overdue(GOLD_DEADLINE, GOLD_DEADLINE - MINUTE) is False


def test_not_overdue_exactly_at_deadline():
    assert claims.is_overdue(GOLD_DEADLINE, GOLD_DEADLINE) is False


def test_overdue_one_minute_after_deadline():
    assert claims.is_overdue(GOLD_DEADLINE, GOLD_DEADLINE + MINUTE) is True


@pytest.mark.parametrize("offset, escalates", [(-MINUTE, False), (timedelta(0), False), (MINUTE, True)])
def test_escalate_overdue_respects_deadline_edge(conn, offset, escalates):
    claim_id = new_claim(conn)

    escalated = claims.escalate_overdue(conn, by="system", now=GOLD_DEADLINE + offset)

    assert escalated == ([claim_id] if escalates else [])


def test_escalate_overdue_escalates_open_and_assigned_and_returns_ids(conn):
    open_id = new_claim(conn)
    assigned_id = new_claim(conn)
    claims.assign(conn, assigned_id, "Priya", by="desk", now=FILED)

    escalated = claims.escalate_overdue(conn, by="system", now=GOLD_DEADLINE + MINUTE)

    assert escalated == [open_id, assigned_id]
    assert status_of(conn, open_id) == "escalated"
    assert status_of(conn, assigned_id) == "escalated"


def test_escalate_overdue_leaves_resolved_closed_and_not_yet_due_alone(conn):
    resolved_id = new_claim(conn)
    set_status(conn, resolved_id, "resolved")
    closed_id = new_claim(conn)
    set_status(conn, closed_id, "closed")
    silver_id = new_claim(conn, tier="silver")  # due 24 hours after filing

    escalated = claims.escalate_overdue(conn, by="system", now=GOLD_DEADLINE + MINUTE)

    assert escalated == []
    assert status_of(conn, resolved_id) == "resolved"
    assert status_of(conn, closed_id) == "closed"
    assert status_of(conn, silver_id) == "open"


def test_escalate_overdue_second_run_does_nothing(conn):
    claim_id = new_claim(conn)

    assert claims.escalate_overdue(conn, by="system", now=GOLD_DEADLINE + MINUTE) == [claim_id]
    assert claims.escalate_overdue(conn, by="system", now=GOLD_DEADLINE + 2 * MINUTE) == []
    assert len(claims.history(conn, claim_id)) == 2


def test_escalation_writes_history_entry(conn):
    claim_id = new_claim(conn)
    claims.assign(conn, claim_id, "Priya", by="maria", now=FILED)
    when = GOLD_DEADLINE + MINUTE

    claims.escalate_overdue(conn, by="system", now=when)

    last = claims.history(conn, claim_id)[-1]
    assert (last["old_status"], last["new_status"], last["changed_by"]) == ("assigned", "escalated", "system")
    assert datetime.fromisoformat(last["changed_at"]) == when


def test_escalating_claim_that_is_not_overdue_rejected(conn):
    claim_id = new_claim(conn)

    with pytest.raises(claims.ClaimError, match="not overdue"):
        claims.escalate(conn, claim_id, by="desk", now=GOLD_DEADLINE)

    assert status_of(conn, claim_id) == "open"


@pytest.mark.parametrize("status", ["resolved", "closed"])
def test_escalating_resolved_or_closed_claim_rejected(conn, status):
    claim_id = new_claim(conn)
    set_status(conn, claim_id, status)

    with pytest.raises(claims.ClaimError, match=f"from {status} to escalated"):
        claims.escalate(conn, claim_id, by="desk", now=GOLD_DEADLINE + MINUTE)

    assert status_of(conn, claim_id) == status


def test_status_change_rolls_back_when_history_write_fails(conn):
    claim_id = new_claim(conn)
    fail_history_writes(conn)

    with pytest.raises(sqlite3.IntegrityError, match="history write failed"):
        claims.escalate_overdue(conn, by="system", now=GOLD_DEADLINE + MINUTE)

    assert status_of(conn, claim_id) == "open"
    conn.execute("DROP TRIGGER fail_history")
    assert len(claims.history(conn, claim_id)) == 1


def test_filing_rolls_back_when_history_write_fails(conn):
    fail_history_writes(conn)

    with pytest.raises(sqlite3.IntegrityError, match="history write failed"):
        new_claim(conn)

    assert claims.list_claims(conn) == []
