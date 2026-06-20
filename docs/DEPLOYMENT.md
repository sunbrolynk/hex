# Deployment — the bundled stack

HEx ships and orchestrates its identity plane. By **default** Authentik is bundled, so a
single command brings up the whole system. See ADR 0010.

## Two modes (`HEX_AUTHENTIK_MODE`)

`HEX_AUTHENTIK_MODE` (`bundled` | `external`, default `bundled`) selects how Authentik is
provided (ADR 0013). Bundled is the preferred, simple on-ramp; external is for deployers who
already run Authentik and don't want a second one.

- **bundled (default).** HEx's compose runs the Authentik services behind the
  **`bundled-authentik`** compose profile (enabled by default via `COMPOSE_PROFILES`). The
  bundled-stack secrets (`AUTHENTIK_SECRET_KEY`, `AUTHENTIK_PG_PASSWORD`,
  `AUTHENTIK_REDIS_PASSWORD`, `AUTHENTIK_BOOTSTRAP_*`) are required only here. Everything in
  "What ships" below applies.
- **external / bring-your-own.** The `bundled-authentik` profile stays off, so no Authentik
  services start; HEx points at the deployer's existing Authentik. Required vars:
  `AUTHENTIK_BASE_URL`, the OIDC client creds (`AUTHENTIK_OIDC_CLIENT_ID` /
  `AUTHENTIK_OIDC_CLIENT_SECRET`), and the scoped `AUTHENTIK_API_TOKEN`. The bundled-stack
  secrets are not needed.

The rest of this document describes **bundled mode**; its invariants (separate Postgres
instances, locked; Authentik never embedded in HEx's container) still hold there.

## What ships

Authentik is a four-service stack (confirmed from its docs): a **server**, a **worker**,
**PostgreSQL** (14–18), and **Redis**. HEx's deployment composes that stack together with
HEx and HEx's own database:

```
HEx deployment (docker compose)
├── hex                  # the HEx app (FastAPI + built frontend)
├── hex-db               # PostgreSQL for HEx's operational state (ledger, audit, config)
├── authentik-server     # Authentik web/API
├── authentik-worker     # Authentik background tasks (mounts docker socket for outposts)
├── authentik-db         # PostgreSQL for Authentik
└── authentik-redis      # Redis for Authentik
```

One `docker compose up -d` rolls **both services** (HEx and Authentik) and their datastores.
**HEx and Authentik run on fully separate PostgreSQL instances — locked, non-negotiable.**
Never share one Postgres instance or one logical database across the two apps: separate
instances keep their data, credentials, upgrade cycles, and blast radius independent.

> HEx does **not** embed Authentik inside its own container. Two apps in one container would
> break separation of concerns, independent updates, and the security boundary. HEx
> orchestrates the stack and owns the integration; each service stays its own image.

## Supported deployment methods (intended, in priority order)

These are the deployment targets HEx aims to support, listed in the order they're intended to
be completed. Some overlap (native-on-hardware is really "native per OS"); that's expected.

1. **Docker (compose) — first-class, the reference path.** This is where Authentik bundling
   is clean: the four Authentik services + datastores + HEx come up together from one compose
   file. Everything else below is measured against this.
2. **LXC** (e.g. system containers). Workable, but the bundled Authentik stack still wants
   container orchestration inside the LXC (nested Docker/compose) or a hand-rolled multi-
   service setup — more moving parts than (1).
3. **VM.** A VM image / cloud-init that brings up the stack (typically via Docker inside the
   VM). Straightforward once (1) exists.
4. **Native service on hardware (bare metal).** HEx itself as a native service is fine; the
   hard part is **Authentik** — it's a four-service stack oriented around containers, so
   running it natively/bare-metal is materially more work and must be documented per OS.
5. **Linux (native).** Native packaging/service unit (systemd) for HEx; Authentik native is
   the heavy lift (see 4).
6. **Windows (native).** Hardest target: Authentik has no first-class native Windows story,
   so realistically this means "Docker Desktop / WSL2 under the hood" rather than truly
   native services. Document honestly; don't pretend it's pure-native.
7. **macOS (native).** Same caveat as Windows — practically container-backed, not truly
   native, given Authentik's orientation.

**The honest through-line:** HEx is easy to run anywhere; **the bundled, required Authentik
stack is what makes non-Docker targets progressively harder.** Authentik **officially supports
only Docker Compose and Kubernetes (Helm)** — there is **no supported bare-metal/native
install** (community scripts exist but are unofficial and fragile, e.g. building Python from
source). So every non-container HEx target must either run Authentik in a container alongside
HEx, or accept an unsupported bare-metal Authentik — document which, honestly, per target.
Docker compose stays the recommended path, and every other target's docs must spell out how
its Authentik stack + two separate Postgres instances are stood up and kept healthy. Don't
ship a target whose Authentik story is hand-wavy.

The concrete artifacts for each target live under `deploy/` (compose first; others added in
the order above) and are built against the live stack — treat snippets here as shape, not
copy-paste.

## What HEx adds on top of a stock Authentik compose

- **Pinned, verified images.** Authentik server/worker pinned to a known-good tag (and,
  where available, verified); HEx's own image is signed with provenance + SBOM (see
  `docs/SUPPLY_CHAIN.md`). The bundled compose pins everything; nothing floats on `latest`.
- **Bootstrap seeding.** Authentik's automated-install env vars seed first start:
  `AUTHENTIK_BOOTSTRAP_PASSWORD_HASH` (pre-hashed admin password — avoids plaintext in the
  deploy), `AUTHENTIK_BOOTSTRAP_TOKEN` (a first-start API token HEx uses to configure
  Authentik), and `AUTHENTIK_BOOTSTRAP_EMAIL`. All carry generation instructions in
  `.env.example`; none ship with a usable default.
- **HEx blueprints.** HEx ships Authentik **blueprints** (declarative YAML Authentik imports
  at startup) under `deploy/authentik/blueprints/` that create HEx's OIDC application +
  provider, its scoped service account, and the groups HEx manages — so these exist
  automatically instead of being clicked together by hand. The blueprints are mounted
  read-only into the Authentik server/worker. Concretely, blueprint entries use Authentik's
  models — `authentik_providers_oauth2.oauth2provider` (one **confidential** provider for the
  web BFF, one **public** provider for Android), `authentik_core.application`,
  `authentik_core.group`, and an `authentik_core.user` service account plus its token — and
  reference built-in flows with `!Find`. Setting the bootstrap env vars also **skips
  Authentik's own out-of-box `initial-setup` flow**, so HEx drives setup end to end.
- **Internal networking + secret wiring.** Compose networks keep Authentik's datastores
  internal; only the proxy ingress and the necessary service ports are exposed. Secrets are
  generated per the secrets rules, never shipped as usable defaults.

## Ports / ingress

Authentik listens internally on 9000 (HTTP) / 9443 (HTTPS) by default; HEx on its own port.
Both sit behind the reverse proxy (with Authentik providing forward-auth/OIDC). Don't expose
the app ports directly — the proxy is the only ingress (see SECURITY_MODEL §2).

## Versioning & updates

- Authentik and HEx update independently (separate images). Pin Authentik to a tested tag
  and bump deliberately; Authentik's PostgreSQL major has upgrade steps — follow its guide.
- HEx's integration code targets a documented Authentik API/version baseline; when bumping
  Authentik, run HEx's integration tests against the new version before shipping the bump.

## First run

Bringing the stack up the first time does **not** require pre-wiring Authentik by hand. HEx
detects first run and walks the owner through a guided bootstrap that finishes the Authentik
setup and then HEx's own. That flow — and the security of the setup surface — is in
`docs/BOOTSTRAP.md`.

## Reference, not literal

A concrete `deploy/` compose + blueprints will be built with the maintainer against the live
stack and pinned versions; treat any compose snippets in these docs as the shape, not a
copy-paste artifact (same discipline as `docs/ci/`).
