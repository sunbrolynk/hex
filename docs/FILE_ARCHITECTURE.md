# File Architecture

HEx's directory conventions. The companion `CONVENTIONS.md` covers code style; this covers
*where files live*. The layout favors many small, single-responsibility modules over a few
large ones (see the file-size rules in `CONVENTIONS.md`).

## Backend — root is `src/`

```
src/
├── api/
│   ├── {resource}_routes/        # one folder per route group
│   │   ├── __init__.py
│   │   └── router.py             # endpoints for that resource only
│   ├── __init__.py
│   ├── dependencies.py           # FastAPI dependencies
│   ├── main.py                   # app assembly / router registration
│   └── schemas.py                # central Pydantic schemas
├── database/
│   ├── database.py               # engine/session
│   ├── models.py                 # SQLAlchemy models
│   ├── {domain}_manager.py       # data-access "manager" classes
│   └── __init__.py
├── providers/                    # pluggable providers: base + one file per app
│   ├── base.py                   # the provider interface (one contract)
│   └── {app}.py                  # one provider per integrated app
├── {feature}/                    # cohesive feature packages (auth client, secrets, …)
├── services/
│   ├── handlers/                 # one file per background/orchestration task
│   │   └── {task}_handler.py
│   └── {concern}_service.py      # flat, one service file per concern
├── utils/
│   ├── {subsystem}/              # subpackage when a concern has parts (e.g. logging/)
│   └── {concern}.py              # flat, one util module per concern
├── __init__.py
├── __version__.py
└── config.py
```

Key points:

- **Route groups are `{resource}_routes/` with `__init__.py` + `router.py`.** Schemas are
  **central** in `api/schemas.py`, not co-located per route. Keep routers thin — push logic
  into services so the router stays small.
- **No top-level `models/` or `core/` package.** Models live in `database/models.py`;
  config is `src/config.py` at the src root.
- **Data access uses "manager" classes** (`database/{domain}_manager.py`).
- **Services are flat, one concern each**, with a `handlers/` subfolder for task
  orchestration (one handler per task). Split a growing service into a small service plus
  focused helpers rather than letting it balloon.
- **Pluggable systems = `base.py` interface + one file per implementation.** This is the
  shape for HEx's providers (see below). Note the vocabulary: there is one provider
  *contract* (the `base.py` interface); each provider declares one of four *integration
  modes*; the apps are the providers. See `docs/PROVIDER_CONTRACT.md`.

## Frontend — `frontend/src/`

```
frontend/src/
├── components/
│   ├── {kind}/      # grouped by kind: cards, modals, toasts, tables, ui, layout, icons
│   └── {feature}/   # and by feature where it makes sense
├── pages/
│   └── {area}/      # grouped by area: onboarding, dashboard, requests, settings, system, about
├── hooks/           # use{Feature}Data.ts + use{Feature}Actions.ts (split data vs actions)
├── services/        # thin per-resource API wrappers (small — one resource each)
├── stores/          # global state (e.g. Layout, Theme)
├── contexts/        # cross-cutting React contexts (Auth, …)
├── lib/             # api.ts, websocket.ts, utils.ts
├── types/ , utils/ , assets/
├── App.tsx , main.tsx
```

Notable: **hooks split into `…Data` and `…Actions`** per feature; **frontend `services/`
are deliberately thin** (one small file per resource); pages grouped by area folder. Keep
page components from becoming god files — extract sections into components and the data/
action logic into hooks.

The `pages/about/` area is a **required** surface (ADR 0012): one quiet About/Credits page,
reached from near the GitHub link, listing the libraries and upstream apps that make HEx
possible (attribution, ideally generated from the lockfiles so it can't drift), plus the
project repo/site/GitHub and donation links. It is never surfaced prominently and never
nags. The Android app implements the equivalent single About/Credits screen.

## Tests mirror source 1:1

```
tests/
├── api/{resource}_routes/test_router.py     # mirrors src/api/{resource}_routes/
├── providers/test_{app}.py                  # + contract-conformance tests per provider
├── services/handlers/test_{task}_handler.py
├── services/test_{concern}_service.py
├── database/{domain}_manager/test_*.py
├── factories/{model}_factory.py             # one factory per model ({Model}Factory)
├── utils/…  , conftest.py (at multiple levels)
```

Test layout shadows the source tree; factories live under `tests/factories/`.

## Proposed HEx tree (confirm route-group names before scaffolding)

The provider system uses the `base.py` + one-file-per-app pattern; that is the home for the
provider contract.

```
src/
├── api/
│   ├── auth_routes/              # OIDC login (relying party)
│   ├── breakglass_routes/        # local emergency access (disabled by default)
│   ├── invite_routes/            # owner-created invites + acceptance/signup surface
│   ├── lifecycle_routes/         # provision / offboard actions
│   ├── request_routes/           # user access-requests + owner approvals
│   ├── provider_routes/          # owner config of providers + grant schemas
│   ├── dashboard_routes/         # per-user dashboard payloads
│   ├── audit_routes/             # read access to the audit log (owner)
│   ├── system_routes/            # health, version, status
│   ├── dependencies.py , main.py , schemas.py , __init__.py
├── providers/                    # the provider contract + one file per app
│   ├── base.py                   # the interface: the four modes, two axes, methods
│   ├── jellyfin.py               # api_local / provider
│   ├── plex.py                   # external_invite / external
│   ├── seerr.py                  # api_local / provider (Overseerr-compatible API)
│   ├── forward_auth.py           # sso_group / authentik (generic forward-auth app)
│   └── manual.py                 # manual / instructional
├── database/
│   ├── database.py , models.py
│   ├── ledger_manager.py         # the provisioning ledger (backbone of offboarding)
│   ├── audit_manager.py          # append-only, tamper-evident audit log
│   └── __init__.py
├── authentik/                    # Authentik API client + token validation (identity SoT)
│   ├── client.py , oidc.py
├── bootstrap/                    # first-run guided setup: state, Authentik wiring, hardening
├── secrets/                      # secrets broker (envelope encryption, boot validation)
├── services/
│   ├── handlers/
│   │   ├── provision_handler.py
│   │   ├── offboard_handler.py
│   │   └── reconcile_handler.py
│   ├── invite_service.py , request_service.py , breakglass_service.py , …
├── utils/
│   ├── logging/
│   └── {concern}.py
├── __init__.py , __version__.py , config.py
```

Frontend mirrors the `frontend/src/` shape above with HEx's areas. Tests mirror this tree,
with `tests/providers/` carrying the **contract-conformance tests** required for every
provider (see `docs/PROVIDER_CONTRACT.md` and `docs/TESTING.md`).

A top-level **`deploy/`** holds the bundled stack and per-target deployment artifacts. The
reference target is **docker-compose** (rolls HEx + Authentik server/worker + two separate
Postgres instances + Redis); additional targets (LXC, VM, native per-OS) are added under
`deploy/` in the priority order in `docs/DEPLOYMENT.md`. `deploy/authentik/blueprints/` holds
the declarative YAML Authentik imports on first start to create HEx's OIDC app, service
account, and groups (see `docs/DEPLOYMENT.md`, `docs/BOOTSTRAP.md`).

The security-critical areas (`providers/`, `secrets/`, `authentik/`, `bootstrap/`, auth,
invite, breakglass, audit) follow the stricter small-file target from `CONVENTIONS.md`.
