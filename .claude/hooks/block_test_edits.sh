#!/bin/sh
# STRETCH GOAL 1: PreToolUse hook that blocks Claude from editing anything in tests/.
# The tests are the spec: change the code, or ask the human to change the test.
# Claude Code sends the tool call as JSON on stdin; exit code 2 blocks the call and shows stderr to Claude.
path=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')
case "$path" in
  tests/* | */tests/*)
    echo "Blocked: $path is in tests/. Tests are the spec; fix the code instead, or ask the human to change the test." >&2
    exit 2
    ;;
esac
exit 0
