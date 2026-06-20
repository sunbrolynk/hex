# 0014 — The per-user dashboard is a rich, configurable, lifecycle-governed feature

- Status: **Accepted** (amends 0003)
- Date: project inception

## Context

ADR 0003 framed the v1 dashboard as "intentionally minimal" to keep focus on the lifecycle
arc. That framing undersells the product. The dashboard is the *surface* every user touches
daily; a flat, commodity tile page leaves HEx's main user-facing experience weaker than the
standalone tools (Homarr, Homepage, Dashy) it sits beside.

The distinction from those tools was never "ours is smaller." It is that HEx's dashboard is
**governed by the lifecycle**: a user sees and configures only what they have been granted
(read from the ledger), and the whole thing is offboardable in one action. A rich dashboard
and "not another dashboard" therefore do not conflict — governance, not minimalism, is the
line.

## Decision

The per-user dashboard is a **first-class, richly configurable feature**, delivered in
phases. It does **not** change ADR 0001 (Authentik as source of truth), ADR 0002 (the
provider contract / four integration modes), or the lifecycle-is-the-differentiator thesis —
it amends only the dashboard's scope and ambition.

**v1** — a clean, personalized, configurable dashboard:

- curated widgets,
- basic drag/drop layout and organization,
- theming.

**No user-authored code or CSS in v1.** v1 is architected toward the full builder so the
post-v1 work is an extension, not a rewrite. Everything stays strictly per-user-scoped and
ledger-driven.

**Post-v1** — the full dashboard builder, two tracks:

- a **GUI builder for non-technical users**: extensive widget/layout/display/theming
  configuration, entirely in-GUI;
- a **power-user mode to author custom code/CSS**, behind the hardened builder security
  model below.

### Builder security model (stated now; lands post-v1)

User-authored markup/CSS/code is a hostile-input surface and is treated like any other
untrusted input. Required mitigations:

- strict **Content-Security-Policy**;
- **HTML sanitization** (allowlist-based);
- **no arbitrary or inline JavaScript**;
- **CSS sandboxing/scoping** (iframe sandbox and/or Shadow DOM + sanitized CSS) to prevent
  CSS injection and CSS-based data exfiltration;
- **server-side validation** of saved dashboard definitions;
- **strict per-user isolation** — one user's dashboard can never affect another user or the
  owner.

These paths are covered by abuse/failure tests, not just happy-path tests. See THREAT_MODEL
(hostile-input boundaries) and SECURITY_MODEL.

## Consequences

- The v1 dashboard data model and rendering must be designed for the eventual builder
  (declarative, server-validated dashboard definitions) so power-user code/CSS slots in later
  without a rewrite.
- The builder is a security-critical surface from the moment user-authored content is
  allowed; its mitigations are not optional and are merge-blocking.
- HEx's user-facing experience is no longer the weakest part of the product, while the
  lifecycle remains the differentiator.

## Rejected alternatives

- **Keep the dashboard minimal/commodity (ADR 0003 as written).** Rejected: it undersells
  the product and leaves the daily-touched surface thinner than standalone dashboards for no
  good reason — the differentiator is governance, not minimalism.
- **Ship the full code/CSS builder in v1.** Rejected: too much scope before the lifecycle is
  proven, and it opens a serious hostile-input surface (stored XSS, CSS injection/exfil,
  sandbox escape) prematurely. Curated-but-rich first; the builder once the spine is solid.
