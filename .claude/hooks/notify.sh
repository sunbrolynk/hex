#!/usr/bin/env bash
# Sends a Claude Code lifecycle event to Gotify so you can step away and get pinged.
# Wired in .claude/settings.json for the Stop and Notification events.
#
# Reads the hook event JSON from stdin (Claude Code pipes it in).
# Requires two env vars set in your shell profile (NEVER commit these):
#   export GOTIFY_URL="https://gotify.your-domain.tld"
#   export GOTIFY_TOKEN="A_your_app_token"
#
# NOTE: this runs as a hook command, not through the agent's Bash tool, so the
# `Bash(curl:*)` deny in settings.json does NOT apply here — curl works.
set -uo pipefail

GOTIFY_URL="${GOTIFY_URL:-}"
GOTIFY_TOKEN="${GOTIFY_TOKEN:-}"

# Fail quietly if not configured — never block Claude Code over a missing notifier.
if [ -z "$GOTIFY_URL" ] || [ -z "$GOTIFY_TOKEN" ]; then
  echo "notify.sh: GOTIFY_URL/GOTIFY_TOKEN not set; skipping notification." >&2
  exit 0
fi

payload="$(cat 2>/dev/null || true)"
event="$(printf '%s' "$payload" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("hook_event_name","event"))' \
  2>/dev/null || echo event)"
proj="$(basename "$(pwd)")"

case "$event" in
  Stop)
    title="✅ Claude Code finished"
    msg="[$proj] Slice ready — review the diff, run it live, then decide."
    prio=5 ;;
  Notification)
    title="⏳ Claude Code needs you"
    msg="[$proj] Waiting on your input or permission."
    prio=8 ;;
  *)
    title="Claude Code"
    msg="[$proj] $event"
    prio=4 ;;
esac

# Best-effort; never fail the hook over a notification problem.
curl -fsS --max-time 10 -X POST "$GOTIFY_URL/message?token=$GOTIFY_TOKEN" \
  -F "title=$title" -F "message=$msg" -F "priority=$prio" >/dev/null 2>&1 || \
  echo "notify.sh: Gotify POST failed (non-fatal)." >&2

exit 0