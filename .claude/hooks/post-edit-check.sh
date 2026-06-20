#!/usr/bin/env bash
# PostToolUse auto-check for HEx — fast feedback after every Edit/Write.
# Enable by wiring it in .claude/settings.json (see .claude/README.md).
# Designed to be SAFE on a partially-built repo: each step runs only if its
# tool is available, so it won't error before the toolchain exists.
#
# Exit 0 = ok (hook output is advisory). Adjust commands to the real scripts.
set -uo pipefail

run_if() {  # run_if <tool> <command...>
  command -v "$1" >/dev/null 2>&1 || { echo "skip: $1 not installed"; return 0; }
  shift
  echo "+ $*"
  "$@"
}

echo "── HEx post-edit checks ─────────────────────────────"

# Backend (Python): lint + fast tests. Keep these FAST; full suite runs in CI.
run_if ruff   ruff check .
run_if mypy   mypy .
# Prefer a fast/marked subset here, e.g. `pytest -m "not slow" -q`.
run_if pytest pytest -m "not slow" -q

# Frontend (Node): lint + unit tests, only if a package.json is present.
if [ -f package.json ]; then
  run_if npm npm run -s lint --if-present
  run_if npm npm run -s test:unit --if-present
fi

echo "── done ─────────────────────────────────────────────"
# Always succeed: surface failures to the developer without hard-blocking the
# edit. Switch specific checks to a non-zero exit if you want them to BLOCK.
exit 0
