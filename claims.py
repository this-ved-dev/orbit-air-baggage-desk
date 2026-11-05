"""Claim rules: filing, validation, deadlines and history.

Nothing here reads the clock. Every function that needs the time takes `now`.
"""

from datetime import timedelta

TYPES = ("delayed", "lost", "damaged")
TIER_HOURS = {"gold": 4, "silver": 24, "standard": 72}
STATUSES = ("open", "assigned", "escalated", "resolved", "closed")


class ClaimError(ValueError):
    """A claim rule was broken. Nothing was saved."""


def validate(passenger, flight, claim_type, tier):
    if not passenger or not passenger.strip():
        raise ClaimError("passenger name cannot be blank")
    if not flight or not flight.strip():
        raise ClaimError("flight number cannot be blank")
    if claim_type not in TYPES:
        raise ClaimError(f"unknown claim type {claim_type!r}, expected one of: {', '.join(TYPES)}")
    if tier not in TIER_HOURS:
        raise ClaimError(f"unknown tier {tier!r}, expected one of: {', '.join(TIER_HOURS)}")


def deadline_for(tier, filed_at):
    return filed_at + timedelta(hours=TIER_HOURS[tier])


def file_claim(conn, passenger, flight, claim_type, tier, note="", *, by, now):
    validate(passenger, flight, claim_type, tier)
    with conn:
        cur = conn.execute(
            "INSERT INTO claims (passenger, flight, type, tier, note, filed_at, deadline) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (passenger, flight, claim_type, tier, note or "", now.isoformat(), deadline_for(tier, now).isoformat()),
        )
        _record_history(conn, cur.lastrowid, None, "open", by, now)
    return cur.lastrowid


def _record_history(conn, claim_id, old_status, new_status, by, now):
    conn.execute(
        "INSERT INTO history (claim_id, old_status, new_status, changed_by, changed_at) VALUES (?, ?, ?, ?, ?)",
        (claim_id, old_status, new_status, by, now.isoformat()),
    )


def get_claim(conn, claim_id):
    claim = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if claim is None:
        raise ClaimError(f"no claim with id {claim_id}")
    return claim


def list_claims(conn, status=None, tier=None):
    if status is not None and status not in STATUSES:
        raise ClaimError(f"unknown status {status!r}, expected one of: {', '.join(STATUSES)}")
    if tier is not None and tier not in TIER_HOURS:
        raise ClaimError(f"unknown tier {tier!r}, expected one of: {', '.join(TIER_HOURS)}")
    return conn.execute(
        "SELECT * FROM claims WHERE (:status IS NULL OR status = :status) "
        "AND (:tier IS NULL OR tier = :tier) ORDER BY id",
        {"status": status, "tier": tier},
    ).fetchall()


def history(conn, claim_id):
    get_claim(conn, claim_id)
    return conn.execute("SELECT * FROM history WHERE claim_id = ? ORDER BY id", (claim_id,)).fetchall()
