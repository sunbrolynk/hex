# 0001 — Authentik is the identity source of truth

- Status: **Accepted**
- Date: project inception

## Context

HEx onboards and offboards users across many self-hosted services and needs an identity
system: authentication, MFA, enrollment flows, group/role management, and an API to drive
all of it. Authentik already provides this, is API-first, and supports SCIM 2.0 in both
directions. Authentik is assumed to be the deployment's identity provider, fronting the
browser-facing services HEx orchestrates.

## Decision

**Authentik is the identity source of truth. HEx never reimplements authentication and
never becomes an identity provider.** HEx authenticates its own users via Authentik (OIDC)
and provisions identity by calling Authentik's REST API through a dedicated, least-
privilege service-account token. Where downstream apps support SCIM, Authentik's own SCIM
provider performs the downstream sync and HEx merely manages the group.

This is the deliberate inverse of a "HEx owns identity" design.

## Consequences

- HEx is a relying party; it validates tokens against Authentik's JWKS and derives roles
  from validated identity + its own authorization records, never from client input.
- The security-critical identity surface (password storage, MFA, enrollment) stays in a
  hardened, purpose-built system rather than being re-created (and likely weakened) in HEx.
- Authentik is a **hard dependency for v1** (see 0001a below); the app abstracts the IdP
  only after there is a second real implementation to justify the abstraction.
- HEx's privileged surface shrinks wherever Authentik-SCIM can push to a downstream app
  instead of HEx holding that app's credentials directly.
- **Authentik is bundled and bootstrapped, not assumed.** Because it is required, HEx ships
  and orchestrates it and guides its first-time setup rather than expecting the deployer to
  stand it up and hand-wire it. See ADR 0010, `docs/DEPLOYMENT.md`, `docs/BOOTSTRAP.md`.

### 0001a — Authentik is a hard dependency for v1

Do not build a multi-IdP abstraction speculatively. Build against Authentik directly;
introduce an auth-backend abstraction only when a concrete second backend exists. (YAGNI.)
