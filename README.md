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

Filled in per branch.

## Hidden Instruction Check

Filled in on `feature/cli`, once `seed_claims.csv` exists.

## Overdue Demonstration

Filled in on `feature/cli`.

## Code Review

Filled in on `feature/cli` after `/code-review` runs on the last pull request.
