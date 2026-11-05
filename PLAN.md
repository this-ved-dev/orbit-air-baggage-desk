# Plan: Orbit Air Baggage Desk

## The problem

Orbit Air tracks lost, delayed and damaged bags in spreadsheets and email.
Nobody can see which claims are close to their response deadline, so claims
go past it without anyone noticing. Nobody can tell who changed a claim or when, either.

We are building a small command line desk on top of SQLite. It lets staff file a claim,
hand it to an agent, move it through its statuses, and see its full history.
One command finds every claim that is past its deadline and escalates it.

## Deadline rules

When a claim is filed we store the filed time and work out a deadline from the passenger's tier:

- gold: filed time + 4 hours
- silver: filed time + 24 hours
- standard: filed time + 72 hours

A claim is overdue only once the current time is strictly after the deadline.
At the exact deadline minute it is still on time. The rule code never reads the clock itself:
the current time is always passed in. `main.py` takes it from `--now`, or from the real clock
when `--now` is not given.

## Status changes

Every claim starts as `open`. These are the only moves allowed. Anything else is an error,
and nothing is saved.

- open can go to assigned or escalated
- assigned can go to resolved or escalated
- escalated can go to assigned or resolved
- resolved can go to closed
- closed is final

Escalation has an extra rule: only an open or assigned claim can be escalated, and only
when it is overdue.

Every change, including the filing itself, writes a history row. The status change and its
history row are saved in the same transaction. If the history row fails, the claim stays as it was.

## Tables

`claims`

| column | notes |
|---|---|
| id | integer primary key |
| passenger | text, not blank |
| flight | text, not blank |
| type | CHECK in delayed, lost, damaged |
| tier | CHECK in standard, silver, gold |
| status | CHECK in open, assigned, escalated, resolved, closed; default open |
| agent | text, empty until assigned |
| note | free text, may be empty |
| filed_at | ISO timestamp |
| deadline | ISO timestamp, filed_at + tier hours |

`history`

| column | notes |
|---|---|
| id | integer primary key |
| claim_id | references claims(id) |
| old_status | NULL for the filing entry |
| new_status | status after the change |
| changed_by | who made the change |
| changed_at | ISO timestamp of the change |

## Branches and planned tests

Each branch starts with a commit that holds only the tests. I run them and watch them fail,
and only then is the feature code added. Each branch is merged with its own pull request,
as a merge commit.

1. `feature/schema-and-filing`: tables, filing, validation, deadline by tier, list with filters
   - filing stores every field, with status open
   - blank passenger rejected
   - blank flight rejected
   - unknown type rejected
   - unknown tier rejected
   - deadline is filed + 4 / 24 / 72 hours for gold / silver / standard
   - filing writes a history row (none -> open, who, when)
   - list filters by status and by tier
   - the database CHECK constraint rejects a bad type even without the Python checks
2. `feature/assign-and-status`: assign, resolve, close, allowed changes, history
   - assign moves open -> assigned and records the agent
   - resolve moves assigned -> resolved
   - close moves resolved -> closed
   - every allowed non-escalation move works, including from escalated
   - disallowed moves are rejected and leave the claim unchanged
     (close an open claim, resolve an open claim, assign a closed claim)
   - a full lifecycle leaves four complete history rows
   - blank agent rejected
   - unknown claim id rejected
3. `feature/deadlines-and-escalation`: overdue rule, escalation, its history, rollback
   - one minute before the deadline: not overdue
   - exactly at the deadline: not overdue
   - one minute after the deadline: overdue
   - escalate picks up overdue open and assigned claims and reports their ids
   - resolved, closed and not-yet-due claims are left alone
   - running escalate twice does nothing the second time
   - escalation writes a history row
   - escalating a claim that is not overdue is rejected
   - rollback: force the history insert to fail, and check the claim status did not change
4. `feature/cli`: all eight commands, the `--now` option, the seed command
   - file then list shows the claim
   - `--now` controls what escalate picks up
   - seed loads `seed_claims.csv`
   - bad input exits with a clear error
   - report prints open and overdue counts by tier (stretch goal 2)

## Risks and how I handle them

1. **Tests that depend on today's date.** If rule code read the clock, deadline tests would pass
   one day and fail the next. Every rule function takes `now` as a parameter, the tests use
   fixed datetimes, and only `main.py` reads the real clock.
2. **A status change saved without its history row.** The UPDATE and the history INSERT run inside
   one `with conn:` block, so an error rolls both back. A test forces the history insert to fail.
   I will also remove the transaction once to see that test fail.
3. **Leaking the secret in `.env`.** `.env` is in `.gitignore` before the file exists. A deny rule
   in `.claude/settings.json` stops Claude from reading it. Before each push I check that
   `git log --all -- .env` is empty.
4. **The agent changing tests to make them pass.** Tests are committed first and treated as the spec.
   CLAUDE.md says not to edit them, a hook blocks edits under `tests/`, and I review
   `git diff main -- tests/` on every pull request.
5. **Losing the tests-first commit order.** A squash merge would fold the test commit into the
   feature commit, so every pull request is merged with a merge commit.
