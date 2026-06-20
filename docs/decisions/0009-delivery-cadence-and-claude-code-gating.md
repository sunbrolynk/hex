# 0009 — Delivery cadence and Claude Code gating

- Status: **Accepted**
- Date: project inception

## Context

HEx will be built largely with an agentic coding tool (Claude Code). Long autonomous runs
risk the classic failure: an error made early surfaces hours later, after a lot of work has
been built on top of it. The maintainer wants frequent, runnable, human-reviewed checkpoints —
including live and visual verification that the app actually works — plus mechanical
guardrails so the agent can't go far off the rails between checkpoints.

## Decision

Adopt a **checkpoint-driven, vertical-slice cadence** with **committed Claude Code
guardrails** (full detail in `docs/WORKFLOW.md` and `.claude/`):

- **Vertical slices over horizontal layers.** Every slice ends in something the maintainer can
  start and see; "compiles" is not "done."
- **Plan before edits** using plan mode (read-only).
- **Checkpoints block progress:** no proceeding past a checkpoint until the maintainer has
  reviewed the diff, run the slice live, and visually verified any UI. The maintainer is the
  executor and approver on every checkpoint and commit.
- **Fast feedback** via a PostToolUse hook (lint + fast tests after edits) so regressions
  surface immediately; the full suite remains the CI merge gate.
- **Bounded autonomy** via committed `.claude/settings.json` permission rules
  (deny > ask > allow): allow low-risk repeatable commands, ask on privileged/irreversible
  effects, deny dangerous or secret-touching operations. PreToolUse hooks as hard
  guardrails; plan mode for review; bypass mode avoided outside throwaway sandboxes.

## Consequences

- The gating travels with the repo and applies identically every session, rather than
  depending on the maintainer remembering to set a mode.
- The agent physically cannot read `.env`/secrets or force-push, and stops for a live check
  each slice — much stronger than trusting it to behave.
- OS-level sandboxing is macOS-only; on Windows/Linux the boundary is permission rules +
  hooks (optionally inside a dev container). Documented in WORKFLOW.
- Some raw speed is traded for the guarantee that errors are caught within a slice, not
  hours later. For this project that trade is correct.
