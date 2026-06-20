# 0010 — Authentik is bundled and required; first run is a guided bootstrap

- Status: **Accepted** (supersedes the "assumed to exist" framing in 0001) — **amended by
  0013**: bundled is now the **default**, not the only path; an external/bring-your-own
  Authentik mode also exists. See `docs/decisions/0013`.
- Date: project inception

## Context

ADR 0001 makes Authentik the identity source of truth but framed it as something the
deployer "already runs." In practice, requiring a non-technical-ish owner to stand up
Authentik separately — a four-service stack (server, worker, PostgreSQL, Redis) — and then
hand-wire OIDC, a service account, and groups before HEx works at all is a brutal first
experience and a frequent failure point. Authentik is not optional to HEx; it *is* HEx's
identity plane. So HEx should ship and orchestrate it, and the first run should guide the
owner through setup rather than crash on everything that isn't configured yet.

## Decision

1. **Authentik is bundled and required.** HEx ships a deployment (docker-compose) that
   stands up the whole stack together — HEx + Authentik server + Authentik worker +
   their datastores (PostgreSQL, Redis) — so **one `docker compose up` rolls both
   services**. HEx does **not** embed Authentik inside its own container (that would break
   separation, updatability, and security); it orchestrates the stack and owns the
   integration. **HEx and Authentik get fully separate PostgreSQL instances — locked, never
   a shared database or instance.** See `docs/DEPLOYMENT.md`.
2. **First run is a guided bootstrap, not a crash.** On first start HEx detects it is
   unconfigured and enters a **secured bootstrap mode** instead of hard-failing on missing
   wiring. It uses Authentik's automated-install path — bootstrap env vars
   (`AUTHENTIK_BOOTSTRAP_PASSWORD_HASH`, `AUTHENTIK_BOOTSTRAP_TOKEN`) plus **blueprints**
   HEx ships (declarative YAML Authentik imports at startup) — to auto-create HEx's OIDC
   application, scoped service account, and groups. It then shows the owner the minimal
   Authentik details to confirm/supply, verifies Authentik is healthy and the integration
   is provisioned, **hardens** (rotates off the bootstrap token to a scoped service-account
   token; recommends disabling the bootstrap admin and enrolling MFA), and only then exits
   bootstrap mode and proceeds to **HEx owner setup**. See `docs/BOOTSTRAP.md`.
3. **"Refuse to boot insecure" still holds for the operational app.** Bootstrap mode is a
   deliberate, minimal, *secured* setup state — not an insecure running app. Once setup
   completes, the normal boot-time secret/security validation applies and HEx refuses to
   run if it is later broken. The first-run setup surface is itself treated as a high-value
   attack surface and gated accordingly (see BOOTSTRAP / SECURITY_MODEL).

## Consequences

- The shipped artifact is a **stack**, not a lone image: HEx, Authentik (server+worker),
  and datastores, wired and ready. `.env.example` carries the Authentik bootstrap/secret
  values with generation instructions.
- HEx owns Authentik **blueprints** in `deploy/` so its own OIDC app + service account +
  groups are created declaratively, minimizing manual Authentik clicking.
- A new runtime state exists: **first-run bootstrap**, distinct from normal operation and
  from the misconfigured/refuse-to-boot state. The state machine and its security are in
  `docs/BOOTSTRAP.md`.
- 0001 still stands (Authentik is the identity SoT; normal login is pure OIDC; break-glass
  is the only local credential). This ADR only changes *how Authentik gets there*: bundled
  and bootstrapped, not assumed.

## Rejected alternatives

- **Assume the deployer runs Authentik separately.** Rejected: brutal onboarding, and a
  core dependency being "bring your own" is a frequent failure point.
- **Embed Authentik inside the HEx container.** Rejected: two apps in one container breaks
  separation of concerns, independent updates, and the security boundary.
- **Crash on missing config and make the owner pre-wire everything.** Rejected: the whole
  point is a guided first run that ends in a working system.
