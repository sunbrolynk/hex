# Architecture

## Thesis

HEx is an **orchestration and experience layer**, not an identity provider and not a
dashboard. It sits *above* the homelab's identity system and *beside* its services,
coordinating the user lifecycle and presenting a personalized experience. The hard,
defensible value is the lifecycle arc and the provider model — not the UI.

## The one decision everything hangs off: Authentik is the identity source of truth

HEx does **not** own authentication. Authentik already provides OIDC, SAML, LDAP,
forward-auth, enrollment flows, MFA, and the entire security-critical identity surface,
and it is fully API-first with SCIM 2.0 in both directions. Reimplementing any of that in
HEx would make HEx a liability rather than a feature.

Therefore:

- **HEx authenticates its own users via Authentik (OIDC).** HEx validates tokens against
  Authentik's JWKS. HEx is a relying party, not an authority.
- **HEx provisions identity by driving Authentik's REST API** using a dedicated,
  least-privilege service-account token — create user, create/assign group, trigger an
  enrollment flow. It does not run the IdP.
- Where a downstream app supports SCIM, **Authentik's own SCIM provider can push** the
  user to that app, so HEx manages the group and Authentik handles the sync. Prefer this
  over HEx talking to the app directly whenever it is available — it shrinks HEx's
  privileged surface.

This is the deliberate inverse of a "HEx is the source of truth" design. See
`docs/decisions/0001`.

## Component layout

> The concrete directory tree lives in `docs/FILE_ARCHITECTURE.md`; this section is the
> logical component view.

```
                         ┌──────────────────────────────┐
   user's browser /      │   Reverse proxy              │
   future Android app ──▶│   + Authentik forward-auth/   │
                         │     OIDC outpost              │
                         └───────────────┬──────────────┘
                                         │ (validated identity)
                                         ▼
                         ┌──────────────────────────────┐
                         │   HEx backend (FastAPI, BFF)  │
                         │  ┌────────────────────────┐   │
                         │  │ Lifecycle engine       │   │
                         │  │ Access-request workflow│   │
                         │  │ Provider registry      │   │
                         │  │ Provisioning ledger    │   │
                         │  │ Audit log (append-only)│   │
                         │  │ Secrets broker         │   │
                         │  └────────────────────────┘   │
                         └───┬───────────┬───────────┬───┘
                             │           │           │
              Authentik API  │   per-provider svc    │  reconciliation
              (identity SoT) │   accounts (scoped)   │  loop
                             ▼           ▼           ▼
                       ┌─────────┐ ┌─────────┐ ┌─────────┐
                       │Authentik│ │Jellyfin │ │  Plex   │  ...providers
                       └─────────┘ │ Seerr   │ │(invite) │
                                   │ Mealie  │ └─────────┘
                                   └─────────┘
```

### Backend (FastAPI, backend-for-frontend)

The only component that holds downstream credentials or talks to providers. Everything a
client needs is mediated here. Responsibilities:

- **Lifecycle engine** — drives invite → provision → request → offboard against the
  provider contract; writes the ledger; emits audit events.
- **Provider registry** — loads enabled providers, runs `validate_config()` at boot,
  exposes their grant schemas to the owner UI.
- **Access-request workflow** — the approval layer that sits *above* all four integration
  modes and dispatches to the right one once the owner approves.
- **Provisioning ledger** — see PROVIDER_CONTRACT. The backbone of offboarding/status.
- **Audit log** — append-only, tamper-evident record of privileged actions.
- **Secrets broker** — the only thing that can decrypt provider credentials; see SECRETS.

### Frontend (React 19)

Presentation only. Holds **no** downstream secrets and makes **no** direct calls to
providers. Talks only to the HEx API with a user-scoped token. The future Android app is
a second client of the same API and follows the same rule — untrusted client, server
enforces everything, no secrets in the client. It ships as a separate public OSS repo; see
`docs/ANDROID.md`.

### Identity plane (Authentik) — bundled, not assumed

Source of truth for *who the user is*. HEx reads/writes identity here through a scoped
service account and validates user sessions here via OIDC. **Authentik is bundled with HEx
and required** — HEx ships and orchestrates the Authentik stack (server, worker, Postgres,
Redis) so one command rolls both, and guides its first-time setup rather than expecting the
deployer to stand it up by hand (see ADR 0010, `docs/DEPLOYMENT.md`, `docs/BOOTSTRAP.md`).

**OIDC client model (two distinct registrations):**

- **Web app — backend-for-frontend (BFF), a *confidential* client.** The HEx backend performs
  the Authorization Code exchange server-side (holding the client secret), and the browser
  only ever receives a secure, httpOnly session cookie — **no tokens in the browser.** This is
  the current best practice for browser-based apps and is the concrete form of "clients hold
  nothing."
- **Android app — a *public* client + PKCE** (no secret; AppAuth-Android). The app holds its
  tokens in hardware-backed encrypted storage. See `docs/ANDROID.md`.

HEx ships Authentik blueprints that pre-create **both** of these (a confidential provider/app
for the web BFF and a public provider/app for Android) plus the HEx service account and the
groups HEx manages — so first run is turnkey (see `docs/BOOTSTRAP.md`).

**Break-glass exception (availability).** Because losing Authentik would otherwise lock the
owner out of HEx exactly when they need to repair things, HEx provides one minimal,
disabled-by-default, condition-gated local **break-glass** owner login. It is accepted only
under break-glass conditions (primarily: Authentik/OIDC unreachable) and/or via a
local-only path, is MFA-protected and Argon2id-hashed, rate-limited with lockout, and every
use is a high-severity audit event. It is the emergency exit, never a routine second front
door — normal login stays pure OIDC. See `docs/decisions/0008` and SECURITY_MODEL §13.

### Data plane (PostgreSQL)

HEx's operational state: users-as-HEx-knows-them, the ledger, audit log, invites,
access-requests, owner configuration, encrypted provider credentials. Note that identity
authority still lives in Authentik; the HEx DB is operational state, not the identity
store of record.

## Trust boundaries (enumerated — the threat model expands on these)

1. **Public ↔ HEx (unauthenticated):** invite-acceptance and signup endpoints. Hostile
   by default. Capability-token gated, rate-limited, enumeration-resistant.
2. **Client ↔ HEx (authenticated):** every request independently authorized server-side.
   Never trust client-supplied role/identity claims.
3. **Proxy ↔ HEx:** HEx must not blindly trust proxy-injected headers. Validate the auth
   assertion itself. See SECURITY_MODEL "the forward-auth header trap."
4. **HEx ↔ providers:** each via a scoped service account, secrets decrypted only in the
   secrets broker, calls fail-secure.
5. **HEx ↔ Authentik:** scoped service-account token; the most sensitive integration.

## Why the dashboard is intentionally minimal in v1

The dashboard is commodity and can be made beautiful later. Building it first risks
shipping a Homepage clone and stalling before the differentiating work. v1 proves the
**whole lifecycle arc** against a small provider set chosen to exercise **all four
integration modes** (see LIFECYCLE and `docs/decisions/0003`). Once the contract survives
all four modes end to end, breadth is just writing more providers against a proven spine.

## Deployment shape

- **A bundled stack, not a lone image.** HEx ships a docker-compose that rolls HEx + its
  database + the Authentik stack (server, worker, Postgres, Redis) together; one
  `docker compose up` starts both services. HEx does not embed Authentik in its own image —
  it orchestrates the stack. See `docs/DEPLOYMENT.md`.
- HEx's image is published to GHCR, signed, with provenance + SBOM; Authentik images are
  pinned to a tested tag.
- Runs behind a reverse proxy with Authentik in front.
- **First run is a guided bootstrap, not a crash.** On first start HEx enters a secured
  bootstrap mode, finishes wiring Authentik (via bootstrap token + shipped blueprints),
  hardens, then moves into HEx owner setup and normal operation. See `docs/BOOTSTRAP.md`.
- **Secure by default / refuses to boot insecure:** no default admin, mandatory secret
  generation on first run, no real-looking secrets in any shipped example. (Bootstrap mode
  is a *secured* setup state, distinct from the misconfigured/refuse-to-boot state.)

## Transparency as an architectural constraint (no phone-home)

HEx is open and auditable by design (`docs/TRANSPARENCY.md`). This is an architectural
invariant, not just policy:

- A default build makes **zero** outbound connections except to owner-configured systems
  (Authentik and enabled providers). No HEx-operated server is contacted — no telemetry,
  analytics, or licensing callbacks.
- HEx **never** transmits user data, credentials, or ledger/audit content off the owner's
  instance. The egress surface is enumerable and documented; anything outside that list is
  a bug (and, because the code is public, an auditable one).
- The security model itself is public — security depends on secret **keys**, never on
  unreadable code (Kerckhoffs). Verifiable signed/provenance/SBOM releases let deployers
  confirm the running image matches this public source.
