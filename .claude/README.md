# `.claude/` — committed Claude Code gating

This directory configures the guardrails described in `docs/WORKFLOW.md` so they apply the
same way every session, instead of depending on remembering to set a mode.

## `settings.json` (project, committed)

Permission rules with **deny → ask → allow** precedence (deny always wins; an allow rule
cannot override a deny). Summary of intent:

- **allow** — low-risk, repeatable, reversible: read/edit/write files, run tests, lint,
  typecheck, build, read-only git.
- **ask** — privileged or irreversible: any commit/push/merge/rebase, PR/release ops,
  container ops, schema migrations (`alembic`), and dependency installs. These prompt for
  explicit owner approval.
- **deny** — dangerous or secret-touching: reading/editing real secret files
  (`.env`, `.env.local`, …, `secrets/**`), force-push, `rm -rf`, arbitrary network fetch
  (`curl`/`wget`), `sudo`. These are hard-blocked.

### Note on `.env.example`

The deny rules target the **real** secret files by exact name (`.env`, `.env.local`,
`.env.production`, `.env.development`) so that **`.env.example` stays readable** — it
contains no secrets (only generation commands) and Claude Code needs to see it. Don't add a
broad `Read(./.env*)` deny; it would also block the example.

### Local overrides

Personal, uncommitted tweaks go in `.claude/settings.local.json` (gitignored). Use it to
*tighten* further on your machine; avoid loosening the committed deny rules.

## PostToolUse auto-check hook (enable once the toolchain exists)

Fast feedback is what stops a minute-5 error becoming an hour-3 surprise. Once the backend
and frontend toolchains exist, add a **PostToolUse** hook that runs lint + the fast test
subset after every `Edit`/`Write`. A starting template lives at
`.claude/hooks/post-edit-check.sh`. To wire it, add a `hooks` block to `settings.json`
(verify with `/hooks`), for example:

```json
"hooks": {
  "PostToolUse": [
    { "matcher": "Edit|Write",
      "hooks": [ { "type": "command", "command": ".claude/hooks/post-edit-check.sh" } ] }
  ]
}
```

It is **not** wired by default so it doesn't fail on an empty repo. Enable it as soon as
there's something to lint and test.

## Plan vs build

- **Plan mode** (Shift+Tab, or `/permissions` → plan): read-only, structurally cannot
  mutate. Use for design, review, and agreeing the approach before edits.
- **Default mode**: building, with the rules above in force.
- Avoid **bypassPermissions** (`--dangerously-skip-permissions`) outside a throwaway
  sandbox — it approves everything that reaches the mode check (deny rules and PreToolUse
  hooks still apply, but ask/allow gating is gone).

Use `/permissions` in-session to see which rules are active and why a tool did or didn't
prompt.
