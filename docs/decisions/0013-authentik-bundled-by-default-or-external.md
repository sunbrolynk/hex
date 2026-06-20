# 0013 — Authentik bundled by default, or external (bring-your-own)

- Status: **Accepted (amends 0010)**
- Date: project inception

## Context

ADR 0010 made the bundled Authentik stack the *only* path: HEx always rolls up its own
Authentik (server, worker, Postgres, Redis). That is the right on-ramp for a non-expert
owner, but it is wasteful for deployers who **already run Authentik** — forcing a second
Authentik on them duplicates a four-service stack they maintain elsewhere. Bring-your-own
is a standard, expected self-hosted option. 0010 still holds; this ADR only adds the
external branch and makes "bundled" the default rather than the sole choice.

This changes only **how Authentik is provided**, not the identity model. ADR 0001 stands:
Authentik is the identity source of truth and HEx never reimplements auth.

## Decision

1. **One env toggle selects the mode: `HEX_AUTHENTIK_MODE` (`bundled` | `external`,
   default `bundled`).**
2. **bundled (default, preferred, simple).** HEx's docker-compose rolls up the Authentik
   stack (server, worker, its own Postgres, Redis) exactly as ADR 0010 describes. The
   bundled-stack secrets in `.env.example` — `AUTHENTIK_SECRET_KEY`,
   `AUTHENTIK_PG_PASSWORD`, `AUTHENTIK_REDIS_PASSWORD`, and the `AUTHENTIK_BOOTSTRAP_*`
   values — are required **only** in this mode. The bundled Authentik services sit behind
   a compose profile named **`bundled-authentik`**, enabled by default for this mode (via
   `COMPOSE_PROFILES` in the generated `.env`).
3. **external / bring-your-own.** The deployer already runs Authentik and points HEx at
   it; HEx does **not** start its own Authentik services (the `bundled-authentik` profile
   stays off). Required in this mode: `AUTHENTIK_BASE_URL`, the OIDC client creds
   (`AUTHENTIK_OIDC_CLIENT_ID` / `AUTHENTIK_OIDC_CLIENT_SECRET`), and the scoped
   `AUTHENTIK_API_TOKEN`. The bundled-stack secrets are not required.
4. **First-launch gating applies in both modes.** A default web page gates the app on
   first launch until HEx can talk to a ready Authentik — bundled: complete the guided
   bootstrap; external: validate connectivity to `AUTHENTIK_BASE_URL`. This is the same
   "first run is a guided bootstrap, never a crash" behavior, with the external branch
   added; see `docs/BOOTSTRAP.md`.

## Consequences

- The shipped compose carries the Authentik services under the `bundled-authentik`
  profile. Bundled mode runs them; external mode leaves them off, so no second Authentik
  starts.
- `.env.example` gains `HEX_AUTHENTIK_MODE` and annotates which var groups apply per mode.
  It is a mode flag, not a secret — a real default (`bundled`) is correct and does not
  violate the no-placeholder-secrets rule (0005), which governs secrets only.
- The gating-page + connectivity logic is bootstrap-slice feature work; only the config
  toggle, the compose profile, and these docs land now.
- ADR 0010's invariants for bundled mode are unchanged: separate Postgres instances,
  locked; never embed Authentik in HEx's container.

## Rejected alternatives

- **External-only / always bring-your-own.** Rejected: brutal onboarding for non-experts —
  the very reason 0010 bundled Authentik in the first place.
- **Bundled-only / no BYO.** Rejected: wasteful for deployers who already run Authentik,
  forcing a redundant second stack.
