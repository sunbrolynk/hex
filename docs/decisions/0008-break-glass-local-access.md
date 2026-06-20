# 0008 — Minimal local break-glass owner access

- Status: **Accepted** (resolves the open fork noted in 0001 / the design Q&A)
- Date: project inception

## Context

ADR 0001 makes Authentik the identity source of truth and prefers a pure-OIDC login with no
local password path. But that creates an **availability** problem: if Authentik (or the
internet, or OIDC) is down, the owner could be locked out of HEx exactly when they need to
get in to diagnose and repair. The owner wants a minimal local break-glass path for that
case — explicitly scoped so it cannot become a routine bypass of Authentik-as-SoT.

This is a deliberate, bounded exception driven by the **A in CIA (availability)**.

## Decision

HEx provides **one** minimal, owner-only, local **break-glass** credential, designed so it
is safe precisely because it is constrained:

- **Disabled by default.** It does not exist until the owner explicitly provisions it.
- **Single owner account only.** Not a general local-user system; not for normal users.
- **Condition-gated.** It is only accepted under defined break-glass conditions — primarily
  when the primary IdP (Authentik/OIDC) is **unreachable/unhealthy** — and/or via an
  explicitly local-only path. It is **not** a parallel everyday login. If Authentik is the
  thing that's broken, this still works; if HEx can reach a healthy Authentik, the
  break-glass path is closed.
- **Network-constrained where feasible.** Prefer binding the break-glass path to the local
  network / non-internet-exposed surface, so it is not reachable from the public internet.
- **Strongly authenticated.** Argon2id (tuned above the OWASP floor) for the secret, and
  **MFA/step-up (TOTP) strongly recommended/enforced** when enabled. The second factor must
  be **offline-verifiable** (validated locally by HEx), since the recovery path cannot
  depend on Authentik/internet/email being up.
- **Aggressively rate-limited with lockout.** Brute-force resistant; lockout on repeated
  failure.
- **Loudly audited.** Every break-glass authentication (success or failure) is a
  **high-severity, append-only audit event** and, where the owner configures alerting, an
  alert. Break-glass use is never quiet.
- **Optionally scope-limited** to the diagnostic/repair surface needed to recover the
  system, rather than full normal operation.

The **normal** login path remains pure Authentik OIDC (ADR 0001 unchanged). Break-glass is
the explicitly-marked emergency exit, not a second front door.

## Consequences

- Break-glass is the single highest-value local credential and therefore the highest-value
  single target; the constraints above (off-by-default, condition-gated, network-bound,
  MFA, lockout, loud audit) exist specifically to shrink that risk. It is modeled as a
  named asset and attack path in the threat model, and is covered by mandatory abuse tests
  (disabled-by-default, condition-gate enforced, lockout, audit-on-use, MFA).
- `.env.example` ships the break-glass config **disabled**, with generation instructions
  for its secret and a clear note that enabling it opens an emergency path.
- SECURITY_MODEL documents the concrete mechanics; SECRETS covers its credential handling;
  **`docs/BREAK_GLASS.md` is the design + operational runbook** (storage, use, rotation,
  test cadence, standards mapping).

## Rejected alternatives

- **No local path at all (pure OIDC).** Rejected: unacceptable availability risk — owner
  lockout when the IdP is down, with no recovery path.
- **A normal always-on local admin login.** Rejected: it would be a permanent bypass of
  Authentik-as-SoT and a standing high-value target, defeating ADR 0001.
