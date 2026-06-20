# Authentik blueprints

Declarative YAML that the bundled Authentik imports on startup to create HEx's
Authentik objects automatically (see `docs/DEPLOYMENT.md`, `docs/BOOTSTRAP.md`).
This directory is mounted **read-only** into `authentik-server` and `authentik-worker`
at `/blueprints/custom`.

## Status (Slice 0)

Intentionally empty of real blueprints. The full set — the **confidential** OIDC
provider/app for the web BFF, the **public** provider/app (PKCE) for Android, the scoped
service account + token, and HEx's managed groups — is authored in the **bootstrap slice**
against the live Authentik blueprint schema. Per CLAUDE.md we do **not** guess Authentik
model fields, flows (`!Find`), or the API contract; those are verified against the pinned
Authentik version before being written here.

Bundled-mode bring-up (Slice 0 checkpoint) only needs Authentik to start and its UI to be
reachable — it does not require these blueprints to exist yet.
