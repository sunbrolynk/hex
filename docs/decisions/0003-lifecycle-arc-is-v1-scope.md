# 0003 — The full lifecycle arc is v1 scope (depth-first)

- Status: **Accepted** (dashboard scope amended by 0014)
- Date: project inception

## Context

The dashboard is commodity (Homepage, Homarr, Dashy). The media-onboarding wizard slice is
already well served by Wizarr. HEx's defensible value is the **whole user lifecycle arc** —
and especially offboarding — generalized past media servers and driven through Authentik.

## Decision

v1 ships the **entire lifecycle arc**: invite → accept/signup → provision → personalized
dashboard → request-more (approval workflow) → **offboard**. v1 is **depth-first, not
breadth-first**: prove the complete arc against a deliberately small provider set chosen so
that **all four integration modes are exercised end to end**:

- `sso_group` — a multi-user app behind Authentik SSO (e.g. Grafana, a wiki, or Mealie;
  *arr apps are single-user/owner-only, so not a valid user-provisioning example),
- `api_local` — Jellyfin,
- `external_invite` — Plex,
- `manual` — a service with no enrollment API.

v1 ships a curated-but-rich personalized dashboard (no user code/CSS yet); the full
configurable builder is a first-class post-v1 feature — see ADR 0014.

## Consequences

- The provider contract is validated against every integration mode before it hardens.
  Skipping a mode would mean discovering its true shape only after the interface calcified.
- Breadth (more providers) becomes cheap afterward: writing plugins against a proven spine.
- Offboarding — the differentiator and the hard state problem — is in scope from the start,
  which forces the ledger and reconciliation to be real, not deferred.

## Rejected alternative

"Dashboard-first, lifecycle later." Rejected: it risks shipping a Homepage clone and
stalling before the differentiating work, and it lets the provider contract harden without
ever being tested against offboarding or the external-invite mode.
