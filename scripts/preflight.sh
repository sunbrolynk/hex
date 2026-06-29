#!/usr/bin/env bash
#
# Pre-push gate: run everything CI runs, locally, before pushing.
#
# Why this exists: the bug/test/security reviewers are static and read the code diff — they
# can't catch GitHub Actions *runtime* failures (e.g. pip-audit vs an editable package, or an
# action that needs a token). Run this before any push, especially when you touch
# .github/workflows/, dependencies, or the build.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
run()   { echo "+ $*";              "$@"               || { echo "  ✗ FAILED"; fail=1; }; }
runfe() { echo "+ (frontend) $*"; ( cd frontend && "$@" ) || { echo "  ✗ FAILED"; fail=1; }; }

echo "== backend: lint / format / types / tests =="
run uv run ruff check .
run uv run ruff format --check .
run uv run mypy
run uv run pyright
run uv run pytest

echo "== backend: security-critical coverage (secrets + setup + audit + oidc/auth + authentik + break-glass >= 95%) =="
# grep guards against a silent no-op if the include glob ever matches zero files.
# The Alembic migration round-trip is Postgres-only and runs in CI (the backend pg job).
run bash -c "set -o pipefail; uv run coverage report --include='*/hex/secrets/*,*/hex/setup/*,*/hex/audit/*,*/hex/oidc/*,*/hex/breakglass/*,*/hex/providers/*,*/hex/authentik/admin_client.py,*/hex/authentik/errors.py,*/hex/authentik/runtime_config.py,*/hex/authentik/wiring_client.py,*/hex/authentik/management_client.py,*/hex/authentik/orchestrator.py,*/hex/database/setup_manager.py,*/hex/database/audit_manager.py,*/hex/database/ledger_manager.py,*/hex/database/invite_manager.py,*/hex/database/authentik_integration_manager.py,*/hex/database/user_manager.py,*/hex/database/session_manager.py,*/hex/database/login_state_manager.py,*/hex/api/auth_routes/*,*/hex/api/invite_routes/*,*/hex/api/breakglass_routes/*,*/hex/api/dashboard_routes/*,*/hex/api/guards.py' --fail-under=95 | grep -E 'hex/secrets|hex/setup|hex/audit|hex/oidc|hex/breakglass|hex/providers|hex/authentik|setup_manager|audit_manager|ledger_manager|invite_manager|authentik_integration_manager|user_manager|session_manager|login_state_manager|auth_routes|invite_routes|breakglass_routes|dashboard_routes|guards'"

echo "== backend: dependency audit (mirrors CI dependency-scan) =="
run bash -c 'uv export --frozen --no-dev --no-emit-project --format requirements-txt -o /tmp/hex-reqs.txt && uvx pip-audit -r /tmp/hex-reqs.txt'

echo "== frontend: lint / types / format / tests / build / audit =="
runfe npm run -s lint
runfe npm run -s typecheck
runfe npm run -s format:check
runfe npm run -s test:unit
runfe npm run -s build
runfe npm audit --audit-level=high

echo "== workflow lint =="
if command -v actionlint >/dev/null 2>&1; then run actionlint
else echo "  (skip: actionlint not installed — https://github.com/rhysd/actionlint)"; fi

echo
if [ "$fail" -eq 0 ]; then echo "✅ preflight passed — safe to push"; else
  echo "❌ preflight FAILED — do not push"; exit 1; fi

# NOTE: action-environment requirements (an action needing a token, runner-only behavior) are
# NOT fully reproducible here. For those, run the workflow with \`act\`, or treat the first PR
# run after a CI change as a shakedown.
