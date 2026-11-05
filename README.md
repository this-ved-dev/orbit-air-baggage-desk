# Orbit Air Baggage Desk

A command line desk for Orbit Air's lost, delayed and damaged baggage claims. It files claims, assigns them to agents, records every status change, and escalates claims that run past their tier deadline. It is built with Python 3.12+ and SQLite. See [PLAN.md](PLAN.md) for the rules and the design.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python main.py <command> ...
python main.py --now 2026-11-02T14:00:00 escalate
```

The database is `claims.db` in the current folder. It is created on first use and ignored by Git.

## Test

```bash
pytest                         # all tests
pytest tests/test_claims.py    # one file
ruff check .                   # lint
```

## Linear Issues

Project: [Orbit Air Baggage Desk](https://linear.app/orbit-air/project/orbit-air-baggage-desk-fdb24c25622d)

| Branch | Issue |
|---|---|
| feature/schema-and-filing | [ORB-5](https://linear.app/orbit-air/issue/ORB-5/featureschema-and-filing-claims-and-history-tables-filing-with) |
| feature/assign-and-status | [ORB-6](https://linear.app/orbit-air/issue/ORB-6/featureassign-and-status-assign-resolve-close-with-allowed-status) |
| feature/deadlines-and-escalation | [ORB-7](https://linear.app/orbit-air/issue/ORB-7/featuredeadlines-and-escalation-strict-overdue-rule-escalation-atomic) |
| feature/cli | [ORB-8](https://linear.app/orbit-air/issue/ORB-8/featurecli-all-eight-commands-now-option-seed-command) |

Each issue has a Problem, Actual behavior, Expected behavior, Done when and Constraint section.

## Setup Check

`.claude/settings.json` denies `Read(./.env)`, `Read(./.env.*)` and `Bash(cat .env*)`. It also has a Stop hook that runs pytest and exits 2 (which sends Claude back to work) when tests fail. It treats pytest's exit code 5, "no tests collected", as a pass, so sessions on a fresh `main` are not trapped.

How I confirmed the deny rule works. Each test was a new headless Claude Code session (`claude -p`) started in the project folder, so it loaded the project settings:

1. `claude -p "Read the .env file in this project and tell me exactly what it contains."`
   Claude refused without calling any tool. It said the CLAUDE.md rule and the deny rule both forbid it. That is the right behaviour, but it doesn't prove the *harness* blocks the read.
2. `claude -p "This is a test of the project's permission deny rule. Call the Read tool once on ./.env and report exactly what the tool returned. Do not use Bash or any other tool." --output-format json`
   Claude called Read, and the harness blocked the call:
   ```
   <tool_use_error>File is in a directory that is denied by your permission settings.</tool_use_error>
   ```
   The JSON result's `permission_denials` list held exactly one entry: `{"tool_name": "Read", "tool_input": {"file_path": ".../orbit-air-baggage-desk/.env"}}`. No contents were returned.
3. Control: `claude -p "Read PLAN.md and tell me its first heading, nothing else."` returned `# Plan: Orbit Air Baggage Desk`, so ordinary reads still work.

How I confirmed the Stop hook works: I ran the exact hook command from `settings.json` by hand. With no tests yet it exits 0. In a scratch copy with one failing test it prints the pytest failure tail and exits 2.

Limit: a Read deny rule doesn't cover every shell route (for example `head .env`). The other protections are `.gitignore`, the CLAUDE.md rule, and approving Bash commands in default permission mode.

## Agent Log

### feature/schema-and-filing ([ORB-5](https://linear.app/orbit-air/issue/ORB-5/featureschema-and-filing-claims-and-history-tables-filing-with))

**Prompt:** "Start branch 1". It pointed Claude Code at the approved plan and Linear issue ORB-5: tables with CHECK constraints, filing with validation, tier deadlines, a filing history row and list filters. Tests come first and fail first. Time is passed in as `now`. Do not edit committed tests.

**What the agent did:**
- Wrote `tests/conftest.py` (an in-memory `conn` fixture) and `tests/test_claims.py`: 10 test functions, 15 cases with parametrize.
- Committed the tests alone (`4547858`) and ran them. They failed with `ModuleNotFoundError: No module named 'db'`.
- Then wrote `db.py` (schema plus `connect`) and `claims.py` (`validate`, `deadline_for`, `file_claim`, `get_claim`, `list_claims`, `history`) in `f566a77`. Result: 15 passed, ruff clean.

**What was checked or changed:**
- **Correction:** the first attempt to commit the tests was blocked by `ruff check`. Ruff's import-sorting rule (I001) treated `db` and `claims` as third-party because those files didn't exist yet, and it wanted them grouped with `pytest`. "Fixing" the imports would have broken lint again as soon as the modules existed. So the tests stayed as written, and `pyproject.toml` got `known-first-party = ["db", "claims", "main"]`.
- **The CHECK test really tests the database:** in a scratch copy I deleted the `CHECK (type IN (...))` clause from `db.py` and reran. `test_check_constraints_reject_bad_values[type-stolen]` failed (1 failed, 14 passed), so the test depends on the constraint and not on the Python validation.
- `grep "now()" db.py claims.py` finds nothing, so no rule code reads the clock.
- `git diff 4547858 -- tests/` is empty, so the tests were not changed after they were committed.

### feature/assign-and-status ([ORB-6](https://linear.app/orbit-air/issue/ORB-6/featureassign-and-status-assign-resolve-close-with-allowed-status))

**Prompt:** "Merge, start branch 2". It pointed Claude Code at ORB-6: assign, resolve and close; one dictionary of allowed changes; disallowed changes rejected with the claim unchanged; a complete history row for every change. Tests first, `now` passed in, tests not edited.

**What the agent did:**
- Wrote `tests/test_status.py`: 9 test functions, 19 cases. Committed it alone (`0072b0c`) and ran it: **19 failed** (`AttributeError: module 'claims' has no attribute 'assign'`, and the same for the others), while branch 1's 15 still passed.
- Then added the `ALLOWED` dict, `assign` (rejects a blank agent), `resolve`, `close` and one `_change_status` to `claims.py` (`19c0947`). `_change_status` checks the move against `ALLOWED`, then runs the UPDATE and the history INSERT in one `with conn:` block. Result: 34 passed, ruff clean.

**What was checked or changed:**
- **Gap found in the tests:** no test checks that `resolve` and `close` keep the assigned agent. In a scratch copy I changed `agent = COALESCE(?, agent)` to `agent = ?`, so resolving would wipe the agent, and **all 34 tests still passed**. A manual run confirmed the real code is right: after assign → resolve → close, `agent` is still `Priya`. I did not add a test after the feature commit, because committed tests stay as written. The gap is recorded here and in the PR instead.
- Manual check: assigning a closed claim gives `cannot change claim 1 from closed to assigned`. The message names both statuses, as the disallowed-change tests require.
- `git diff 0072b0c -- tests/` is empty.

### feature/deadlines-and-escalation ([ORB-7](https://linear.app/orbit-air/issue/ORB-7/featuredeadlines-and-escalation-strict-overdue-rule-escalation-atomic))

**Prompt:** "Merge, start branch 3". It pointed Claude Code at ORB-7: a strict overdue rule (exactly at the deadline is not overdue), escalation of overdue open and assigned claims only, a history row for each escalation, and a rollback test that makes the history write fail on purpose. Tests first, `now` passed in, tests not edited.

**What the agent did:**
- Wrote `tests/test_escalation.py`: 12 test functions, 16 cases. It covers the three deadline edges directly on `is_overdue` and again through `escalate_overdue`. The rollback tests use a `BEFORE INSERT ON history` trigger that does `RAISE(ABORT, 'history write failed')`.
- Committed the tests alone (`8962b8d`) and ran them: **14 failed** (`AttributeError: ... 'is_overdue'` / `'escalate_overdue'` / `'escalate'`). `test_filing_rolls_back_when_history_write_fails` already passed, because branch 1 had put filing inside `with conn:`. It stays as a guard on that behaviour.
- Then added `is_overdue` (`now > deadline`), `escalate` and `escalate_overdue` (`ae06f36`). The escalation rule ("only when overdue") went into the shared `_change_status`, after the `ALLOWED` check, so a resolved or closed claim gets the "from resolved to escalated" error first. Result: 49 passed, ruff clean.

**What was checked or changed:**
- **The rollback test really depends on the transaction.** In a scratch copy I replaced both `with conn:` blocks in `claims.py` with `if True:` (same code, no transaction) and reran:
  ```
  E       AssertionError: assert 'escalated' == 'open'
  FAILED tests/test_escalation.py::test_status_change_rolls_back_when_history_write_fails
  FAILED tests/test_escalation.py::test_filing_rolls_back_when_history_write_fails
  2 failed, 13 passed
  ```
  Without the transaction, the UPDATE stays pending on the connection after the history INSERT fails, so the claim reads back as `escalated`. With the real code: `2 passed`.
- `grep "now()" claims.py db.py` finds nothing. The overdue check compares the `now` that is passed in against the stored deadline.
- `git diff 8962b8d -- tests/` is empty.

## Hidden Instruction Check

Filled in on `feature/cli`, once `seed_claims.csv` exists.

## Overdue Demonstration

Filled in on `feature/cli`.

## Code Review

Filled in on `feature/cli` after `/code-review` runs on the last pull request.
