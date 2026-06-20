# Delivery Cadence & Claude Code Gating

The failure this prevents: an autonomous agent runs for hours, then a problem made in
minute 5 surfaces at hour 3 and a pile of work has to be unwound. The fix is **frequent,
runnable, human-reviewed checkpoints** plus **mechanical guardrails** so the agent can't go
far off the rails between checkpoints. This doc defines both the *cadence* (how we work) and
the *enforcement* (how Claude Code is configured to make it stick).

## Principles

1. **Vertical slices, not horizontal layers.** Build thin end-to-end slices that actually
   run, rather than all-the-models, then all-the-routes, then all-the-UI. Every slice ends
   in something the maintainer can **start and see**. A slice that compiles but can't be run or
   viewed is not done.
2. **Plan before edits.** Use Claude Code **plan mode** (read-only; Shift+Tab or
   `/permissions` → plan) to agree the approach before any files change. The model can read
   and reason but cannot edit, write, or run mutating commands in plan mode — ideal for
   getting the plan right first.
3. **Checkpoint cadence.** Stop at defined checkpoints for maintainer review. Do **not** proceed
   past a checkpoint until the maintainer has reviewed the diff, the slice has been **run live**,
   and (for anything with UI) it's been **visually verified**. A red or unverified
   checkpoint blocks the next slice.
4. **Fail fast.** Lint and the fast test subset run automatically after edits (PostToolUse
   hook), so an error introduced now surfaces within a tool call or two — not hours later.
   The full suite still runs in CI as the merge gate (see TESTING).
5. **Bounded autonomy.** Low-risk, repeatable actions are pre-approved; privileged or
   irreversible actions require an explicit prompt; dangerous actions are denied outright.

## Checkpoint definition ("done" for a slice)

A slice may be handed back for review only when all of these hold:

- It **runs** — the dev server starts / the endpoint responds / the command executes.
- It is **visually verifiable** where UI is involved — the maintainer can load the page/flow and
  see it behave. Provide the exact command/URL to do so.
- **Lint clean, types clean, relevant tests green** (full suite reserved for CI).
- The diff is **reviewable** — scoped to the slice, complete files, no unrelated churn.
- It does not violate any non-negotiable (CLAUDE.md). If it would, stop and raise it.

Claude Code presents the checkpoint, states exactly how to run/see it, and **waits**. The
maintainer is the executor and the final approver on every checkpoint and every commit.

## Suggested cadence

- **Per slice:** plan → build the slice → auto-checks → hand back with run/verify steps.
- **Roughly hourly or per meaningful unit**, whichever comes first, there is a live-run
  checkpoint — never a multi-hour stretch with no runnable artifact.
- **Security-relevant changes** (auth, authz, provisioning, secrets, invite, break-glass)
  get a read-only reviewer pass against THREAT_MODEL/SECURITY_MODEL before the maintainer commits.

## Mechanical enforcement (Claude Code configuration)

These are real Claude Code controls, committed in `.claude/settings.json` so the gating is
consistent and not dependent on remembering to set a mode. See `.claude/README.md` for the
shipped config and how to extend it.

- **Permission rules** (`permissions.allow` / `ask` / `deny`). Evaluation is **deny → ask →
  allow, and deny always wins** — a deny rule cannot be overridden by any allow rule. We:
  - **allow** low-risk repeatable commands (read/edit, run tests, lint, typecheck, git
    status/diff),
  - **ask** on privileged/irreversible effects (git commit/push/merge, PR ops, container
    ops, schema migrations, dependency installs),
  - **deny** dangerous or secret-touching operations (reading `.env`/secrets, force-push,
    `rm -rf`, arbitrary network fetches).
- **Permission modes.** Use **plan** for design/review sessions (structurally cannot
  mutate), **default** for building. Avoid **bypassPermissions** (`--dangerously-skip-permissions`)
  outside a throwaway sandbox — it approves everything that reaches the mode check.
- **Hooks** (deterministic, run every time, outside the model's discretion):
  - **PreToolUse** as guardrails — block writes to secret files, migrations, or other
    protected paths (a PreToolUse hook exiting non-zero blocks the call, even when a rule
    would allow it).
  - **PostToolUse** for fast feedback — auto-run lint + the fast test subset after every
    `Edit`/`Write`, so regressions surface immediately. (Template in `.claude/README.md`;
    enable once the toolchain exists so it doesn't fail on an empty repo.)
- **Subagents / reviewer pass.** A read-only reviewer agent can check a slice against the
  non-negotiables and threat model before the maintainer commits — the maintainer remains the human
  override on every merge.

### Environment note

This repo is developed in **VS Code locally** (a standard local IDE setup).
OS-level **sandboxing** (the `/sandbox` feature) is **macOS-only** (Seatbelt) — available
and worth enabling when developing on macOS. On Windows/Linux the safety boundary is
**permission rules + hooks** (optionally inside a dev container), since there is no OS
sandbox. Either way, the committed deny rules and PreToolUse guardrails are the primary
protection — lean on them, and keep anything you can't afford the agent to touch out of the
workspace.

## Why this is in the repo

Committing the cadence and the `.claude/` config means the gating travels with the project
and applies the same way every session, instead of depending on the maintainer remembering to
flip a mode. For a tool with HEx's privilege level, "the agent physically can't read `.env`
or force-push, and it stops for a live check every slice" is worth far more than trusting it
to behave.
