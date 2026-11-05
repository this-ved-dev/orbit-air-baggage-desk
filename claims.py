"""Claim rules: filing, validation, deadlines, status changes, escalation and history.

Nothing here reads the clock. Every function that needs the time takes `now`.
"""

from datetime import datetime, timedelta

TYPES = ("delayed", "lost", "damaged")
TIER_HOURS = {"gold": 4, "silver": 24, "standard": 72}
STATUSES = ("open", "assigned", "escalated", "resolved", "closed")
ALLOWED = {
    "open": {"assigned", "escalated"},
    "assigned": {"resolved", "escalated"},
    "escalated": {"assigned", "resolved"},
    "resolved": {"closed"},
    "closed": set(),
}


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


def is_overdue(deadline, now):
    return now > deadline


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


def assign(conn, claim_id, agent, *, by, now):
    if not agent or not agent.strip():
        raise ClaimError("agent name cannot be blank")
    _change_status(conn, claim_id, "assigned", by, now, agent=agent)


def resolve(conn, claim_id, *, by, now):
    _change_status(conn, claim_id, "resolved", by, now)


def close(conn, claim_id, *, by, now):
    _change_status(conn, claim_id, "closed", by, now)


def escalate(conn, claim_id, *, by, now):
    _change_status(conn, claim_id, "escalated", by, now)


def escalate_overdue(conn, *, by, now):
    candidates = conn.execute(
        "SELECT id, deadline FROM claims WHERE status IN ('open', 'assigned') ORDER BY id"
    ).fetchall()
    escalated = []
    for claim in candidates:
        if is_overdue(datetime.fromisoformat(claim["deadline"]), now):
            escalate(conn, claim["id"], by=by, now=now)
            escalated.append(claim["id"])
    return escalated


def _change_status(conn, claim_id, new_status, by, now, agent=None):
    claim = get_claim(conn, claim_id)
    old_status = claim["status"]
    if new_status not in ALLOWED[old_status]:
        raise ClaimError(f"cannot change claim {claim_id} from {old_status} to {new_status}")
    if new_status == "escalated" and not is_overdue(datetime.fromisoformat(claim["deadline"]), now):
        raise ClaimError(f"cannot escalate claim {claim_id}: it is not overdue until after {claim['deadline']}")
    with conn:
        conn.execute(
            "UPDATE claims SET status = ?, agent = COALESCE(?, agent) WHERE id = ?",
            (new_status, agent, claim_id),
        )
        _record_history(conn, claim_id, old_status, new_status, by, now)


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
