#!/usr/bin/env bash
# PreToolUse guard: allow the agent to push FEATURE branches freely, but block any
# push of main/master locally. Belt; branch protection on the remote is suspenders.
#
# Wired in .claude/settings.json under hooks.PreToolUse with matcher "Bash".
# Exit 2 = deny (Claude Code blocks the tool and shows stderr to Claude). Exit 0 = pass.
# Fail-secure: if this is a push and we cannot determine the branch, we DENY.
set -uo pipefail

payload="$(cat 2>/dev/null || true)"
cmd="$(printf '%s' "$payload" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' \
  2>/dev/null || echo "")"

# Only inspect git push commands; everything else passes instantly.
case "$cmd" in
  *"git push"*) : ;;
  *) exit 0 ;;
esac

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"

# 1) On a protected branch, a bare `git push` would push it — deny.
if [[ "$branch" == "main" || "$branch" == "master" ]]; then
  echo "pre-push-guard: refusing to push protected branch '$branch'. Work on a feature branch; reach main only via a PR you merge." >&2
  exit 2
fi

# 2) Command explicitly targets main/master (e.g. 'git push origin main',
#    'git push origin HEAD:main') — deny. Bounded so 'maintenance'/'feature-main' don't match.
if printf '%s' "$cmd" | grep -Eq '(^|[[:space:]])(origin[[:space:]]+)?(HEAD:)?(main|master)([[:space:]]|:|$)'; then
  echo "pre-push-guard: refusing to push to main/master directly. Use a feature branch + PR." >&2
  exit 2
fi

# 3) Fail-secure: couldn't determine branch on a push — deny rather than guess.
if [[ -z "$branch" ]]; then
  echo "pre-push-guard: could not determine current branch; denying push (fail-secure)." >&2
  exit 2
fi

exit 0