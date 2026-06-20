# Threat Model

HEx is structurally **the single most privileged box in the lab**: it holds credentials to
every downstream service *and* it can mint identities in the identity provider. Compromise
of HEx is compromise of the whole homelab. This document models the adversary so the
architecture can be designed against it, not patched after.

Design posture: **assume bad actors on all fronts.** Authenticate and authorize every
request independently. Trust no network position, no proxy header, no client claim.

## Assets (what an attacker wants)

- **A1 — Downstream service credentials.** The per-provider service-account tokens/keys.
  The crown jewels; they grant lateral movement across the lab.
- **A2 — Authentik service-account token.** Lets an attacker create/elevate identities.
- **A3 — User accounts and the owner account.** Especially the owner; owner = full control.
- **A3b — The break-glass credential.** The single local owner login. It is the one
  credential that bypasses Authentik, so it is the highest-value *single* target; its
  constraints (off-by-default, condition-gated, MFA, lockout, loud audit) exist to shrink
  this.
- **A4 — The provisioning ledger and audit log.** Tampering hides unauthorized access.
- **A5 — User PII** (emails, service linkage, request history).
- **A6 — The invite/signup surface** — a path to manufacture access.
- **A7 — The release artifact / build pipeline** — poison once, compromise every deployer.
- **A8 — The first-run setup window.** Before an owner is established, whoever reaches the
  setup wizard could try to claim ownership or read setup material (incl. Authentik's
  bootstrap token). Mitigated by the gated bootstrap surface (out-of-band setup token,
  loopback/LAN binding, completion-bound, browser never sees Authentik secrets) — see
  SECURITY_MODEL §13.5 and `docs/BOOTSTRAP.md`.

## Actors

- **External unauthenticated attacker** — reaches the public invite/signup endpoints and
  the login surface.
- **Authenticated low-privilege user** — a legitimate user trying to escalate, read other
  users' data, or self-grant services.
- **Malicious/compromised invitee** — someone who got an invite link (or guessed/replayed
  one).
- **Network-adjacent attacker** — can reach the HEx container directly, bypassing the
  reverse proxy.
- **Supply-chain attacker** — targets dependencies, CI, or the published image.
- **Compromised downstream service** — a provider HEx talks to returns hostile responses.
- **The non-expert deployer** — not malicious, but will misconfigure HEx insecurely if
  allowed to. Part of the threat model because HEx is OSS.
- **Hostile / modified client (incl. the OSS Android app).** The web and Android clients are
  untrusted and their source is public; assume an attacker runs a tampered build. This buys
  them nothing: no secrets live in any client, and the server authorizes every request
  against the validated identity (see "Clients hold nothing" mitigation and `docs/ANDROID.md`).
  A client that flips a local "I'm an admin" flag changes nothing server-side.

## STRIDE analysis and required mitigations

### Spoofing

- **Proxy-header spoofing (the headline risk).** If HEx trusts `X-Forwarded-User` /
  `Remote-User` / `X-authentik-*` headers and the container is reachable without
  transiting the proxy/outpost, any attacker sets those headers and becomes anyone.
  → **Mitigation:** validate the auth assertion itself (OIDC token against Authentik
  JWKS, or mTLS/shared-secret between proxy and app). Bind the app to the internal network
  only. Never trust a plain injected identity header. See SECURITY_MODEL.
- **Session/token theft.** → short-lived access tokens, secure/HttpOnly/SameSite cookies
  if cookies are used, token-binding where feasible, rotation, server-side revocation.
- **Invite-link replay.** → single-use (hard cap 1), short TTL, ≥128-bit entropy.
- **Break-glass abuse** (brute force, or use when not warranted). → disabled by default;
  accepted only under the defined condition (Authentik/OIDC unreachable) and/or a local-only
  path; MFA; Argon2id; aggressive rate-limit + lockout; every attempt (success or failure)
  is a high-severity audit event and, where configured, an alert. Prefer binding the path to
  non-internet-exposed network. See SECURITY_MODEL §13.

### Tampering

- **Ledger/audit tampering** to conceal unauthorized access. → append-only, tamper-evident
  audit log (hash-chained); audit storage isolated from app write paths; reconciliation
  detects drift independent of the ledger.
- **Grant/permission tampering** via the API. → all grants validated server-side against
  the provider's `grant_schema`; never trust a client-supplied grant blob.
- **Supply-chain tampering** of the image/deps. → signed artifacts + provenance + SBOM +
  pinned deps (SUPPLY_CHAIN).
- **User-authored dashboard content** (the post-v1 builder's code/CSS mode) — stored XSS,
  CSS injection and CSS-based exfiltration, and sandbox escape. → strict CSP; allowlist HTML
  sanitization; **no arbitrary/inline JS**; CSS/iframe sandboxing (iframe sandbox and/or
  Shadow DOM + sanitized CSS); server-side validation of saved dashboard definitions; strict
  per-user isolation so one user's dashboard cannot affect another user or the owner. Covered
  by abuse tests. See ADR 0014.

### Repudiation

- Every privileged action (provision, deprovision, approve/deny, owner config change,
  login, token use) is attributable in the append-only audit log with actor, action,
  target, result, and timestamp.

### Information disclosure

- **Cross-user data leakage** via `widget_data`/`status`/ledger endpoints. → strict
  server-side scoping to the requesting user; authorization tests that prove a user cannot
  read another user's data.
- **Secret leakage** in logs, errors, examples, or API responses. → secrets never logged,
  never returned by the API, never in shipped examples; structured logging with secret
  redaction.
- **Account enumeration** on invite/signup/login/password-reset. → uniform responses and
  timing; generic errors.
- **Verbose errors** leaking internals. → safe error envelopes; details to server logs
  only.
- **HEx itself as an exfiltration channel** (a malicious dependency, contribution, or
  future "feature" that phones home). → no-phone-home is an architectural invariant: a
  default build makes zero outbound connections except to owner-configured systems, the
  egress surface is enumerable and documented, and HEx never transmits user data /
  credentials / ledger / audit content off-instance. Tested for; reviewers reject PRs that
  add undisclosed outbound calls. See `docs/TRANSPARENCY.md`.

### Denial of service

- **Abuse of unauthenticated endpoints** (invite acceptance, signup). → rate limiting,
  per-IP and per-token throttles, invite-attempt caps.
- **Provider-call amplification.** → bounded concurrency, timeouts, circuit breakers on
  provider calls so a slow/hostile provider can't exhaust HEx.

### Elevation of privilege

- **User → owner escalation.** → the owner/user boundary is enforced server-side on every
  endpoint; role is derived from the validated identity, never from client input.
- **Self-granting services** outside the requestable set. → owner policy enforced
  server-side; requests for non-requestable services are rejected regardless of client UI.
- **Over-privileged service accounts.** → each provider account is least-privilege and
  scoped to exactly what it provisions; HEx never holds god-credentials (A1/A2 blast-radius
  reduction). `validate_config()` should detect over-broad scope where the API allows.
- **Client-claimed privilege (tampered/OSS Android client).** → any role or capability is a
  **server-side** attribute of the authenticated account, never a client claim; a tampered or
  rebuilt client cannot self-elevate. The app holds no secrets and is functionally identical
  for everyone, with no client-side gating to bypass (see `docs/ANDROID.md`, ADR 0012).

## Hostile-input boundaries (treat as compromised until proven otherwise)

- The **invite/signup surface** is an unauthenticated hostile surface. Design it as if it
  is actively under attack at all times.
- **Provider responses** are untrusted input. Parse defensively; never `eval`/trust
  shapes; a compromised or buggy provider must not be able to corrupt HEx state or leak
  another user's data.
- **The deployer's environment** may be misconfigured. HEx must refuse to run insecurely
  rather than assume the deployer got it right.
- **User-authored dashboard markup/CSS/code** (post-v1 builder) is hostile input. Treat it
  as actively malicious: CSP, allowlist sanitization, no arbitrary JS, CSS/iframe sandboxing,
  server-side validation, and per-user isolation (see Tampering above and ADR 0014).

## Mapping to a standard

HEx targets **OWASP ASVS 5.0** (the May 2025 release; ~350 requirements across 17
chapters, NIST SP 800-63 aligned). Per-component levels:

- **Identity, access-control, provisioning, secrets, audit, invite handling → Level 3.**
  These are the security-critical core.
- **Everything else (dashboard, general API surface) → Level 2.**

ASVS explicitly supports mixing levels per component; the identity/access core warrants
the higher bar while the dashboard does not. Track conformance per chapter in
SECURITY_MODEL as the build progresses.
