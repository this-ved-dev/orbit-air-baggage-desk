"""Command line interface for the Orbit Air baggage desk. The rules live in claims.py."""

import argparse
import csv
import sys
from datetime import datetime

import claims
import db

SEED_COLUMNS = ["passenger", "flight", "type", "tier", "note"]
CLAIM_ROW = "{:>3}  {:<9}  {:<8}  {:<7}  {:<7}  {:<16}  {:<10}  {:<19}  {}"


def parse_time(text):
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an ISO timestamp: {text!r}") from None
    # stored times are naive local time, so convert an explicit offset instead of mixing the two
    return moment.astimezone().replace(tzinfo=None) if moment.tzinfo else moment


def build_parser():
    parser = argparse.ArgumentParser(prog="main.py", description="Orbit Air baggage claims desk")
    parser.add_argument("--now", type=parse_time, help="ISO timestamp to use instead of the real clock")
    parser.add_argument("--by", default="desk", help="who is making the change (default: desk)")
    commands = parser.add_subparsers(dest="command", required=True)

    file_cmd = commands.add_parser("file", help="file a new claim")
    file_cmd.add_argument("passenger")
    file_cmd.add_argument("flight")
    file_cmd.add_argument("type", help="delayed, lost or damaged")
    file_cmd.add_argument("tier", help="standard, silver or gold")
    file_cmd.add_argument("--note", default="")

    list_cmd = commands.add_parser("list", help="list claims")
    list_cmd.add_argument("--status")
    list_cmd.add_argument("--tier")

    assign_cmd = commands.add_parser("assign", help="assign an open or escalated claim to an agent")
    assign_cmd.add_argument("id", type=int)
    assign_cmd.add_argument("agent")

    for name, help_text in [
        ("resolve", "resolve an assigned or escalated claim"),
        ("close", "close a resolved claim"),
        ("history", "show the history of one claim"),
    ]:
        commands.add_parser(name, help=help_text).add_argument("id", type=int)

    commands.add_parser("escalate", help="escalate every overdue open or assigned claim")
    commands.add_parser("seed", help="load claims from a CSV file").add_argument("path")
    commands.add_parser("report", help="open and overdue counts by tier")
    return parser


def seed(conn, path, *, by, now):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != SEED_COLUMNS:
            raise claims.ClaimError(f"{path} must have the columns {', '.join(SEED_COLUMNS)}")
        rows = list(reader)
    # check every row before saving any, so a bad file loads nothing
    for line, row in enumerate(rows, start=2):
        try:
            claims.validate(row["passenger"], row["flight"], row["type"], row["tier"])
        except claims.ClaimError as error:
            raise claims.ClaimError(f"{path} line {line}: {error}") from None
    for row in rows:
        claims.file_claim(conn, row["passenger"], row["flight"], row["type"], row["tier"], row["note"], by=by, now=now)
    return len(rows)


def print_claims(rows):
    if not rows:
        print("No claims.")
        return
    print(CLAIM_ROW.format("id", "status", "tier", "type", "flight", "passenger", "agent", "deadline", "note"))
    for c in rows:
        print(CLAIM_ROW.format(
            c["id"], c["status"], c["tier"], c["type"], c["flight"], c["passenger"], c["agent"] or "-", c["deadline"],
            c["note"],
        ))


def run(conn, args, now):
    if args.command == "file":
        claim = claims.get_claim(conn, claims.file_claim(
            conn, args.passenger, args.flight, args.type, args.tier, args.note, by=args.by, now=now,
        ))
        print(f"Filed claim {claim['id']} ({claim['tier']} {claim['type']}), deadline {claim['deadline']}")
    elif args.command == "list":
        print_claims(claims.list_claims(conn, status=args.status, tier=args.tier))
    elif args.command == "assign":
        claims.assign(conn, args.id, args.agent, by=args.by, now=now)
        print(f"Claim {args.id} assigned to {args.agent}")
    elif args.command == "resolve":
        claims.resolve(conn, args.id, by=args.by, now=now)
        print(f"Claim {args.id} resolved")
    elif args.command == "close":
        claims.close(conn, args.id, by=args.by, now=now)
        print(f"Claim {args.id} closed")
    elif args.command == "escalate":
        ids = claims.escalate_overdue(conn, by=args.by, now=now)
        print(f"Escalated claims: {', '.join(map(str, ids))}" if ids else "No overdue claims to escalate.")
    elif args.command == "history":
        for h in claims.history(conn, args.id):
            print(f"{h['changed_at']}  {h['old_status'] or '-':>9} -> {h['new_status']:<9}  by {h['changed_by']}")
    elif args.command == "seed":
        print(f"Loaded {seed(conn, args.path, by=args.by, now=now)} claims from {args.path}")
    elif args.command == "report":
        print(f"{'tier':<8}  {'open':>4}  {'overdue':>7}")
        for tier, counts in claims.report(conn, now).items():
            print(f"{tier:<8}  {counts['open']:>4}  {counts['overdue']:>7}")
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    now = args.now or datetime.now().replace(microsecond=0)  # the only place the real clock is read
    conn = db.connect()
    try:
        return run(conn, args, now)
    except (claims.ClaimError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
