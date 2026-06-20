<div align="center">

# HEx Roadmap

**Where HEx is going, and where it is right now.**

</div>

This roadmap is **directional, not a dated promise.** HEx is built in small, reviewable
vertical slices — each one something you could actually run and see — so the order below can
shift as we learn. It exists so you can follow the journey and know exactly what "done" means.

**Legend:** ✅ done · 🚧 in progress · ⬜ planned

> ### 📍 You are here
> **Phase 0 (Foundation) is wrapping up** — the bundled stack comes up, the app serves, the
> quality gates are green. Next up is **Phase 1: identity, secrets, and the guided first run.**

---

## Phase 0 · Foundation 🚧 *(almost done)*

The skeleton everything else is built on.

- ✅ Project charter, architecture, threat model, and locked design decisions (ADRs)
- ✅ Bundled stack — HEx + Authentik (server, worker, its own database, cache) from **one command**
- ✅ **Bundled *or* bring-your-own Authentik** — a single toggle; power users point HEx at their
  existing instance and no second Authentik starts
- ✅ Single-origin serving — the app, its API, and API docs on one port
- ✅ Frontend shell + quiet About/Credits surface
- ✅ Backend skeleton with strict, regression-first quality gates (lint, types ×2, tests, coverage)
- ✅ CI pipeline with commit-SHA-pinned actions and dependency/secret scanning
- 🚧 First tagged checkpoint + branch protection
- ⬜ Signed / provenance / SBOM release pipeline (scaffolded; wired before first release)

## Phase 1 · Identity, secrets & first run ⬜

Making HEx safe to start and able to log you in.

- ⬜ Secrets broker — envelope encryption, **refuse to boot insecure** (no usable defaults, ever)
- ⬜ Guided first-run bootstrap — a secured setup that *never crashes* on a fresh install
- ⬜ Normal login = **Authentik OIDC** (backend-for-frontend; no tokens in the browser)
- ⬜ External-Authentik path — connectivity gating + OIDC wiring for existing instances
- ⬜ Break-glass owner login — disabled by default, condition-gated, MFA, loudly audited

## Phase 2 · The provider contract ⬜

Freezing the spine before the features ride on it.

- ⬜ The provider interface — four integration modes, two identity axes, structured grants
- ⬜ The provisioning **ledger** (the backbone of offboarding) + tamper-evident audit log
- ⬜ Contract-conformance test harness every provider must pass

## Phase 3 · The lifecycle arc ⬜

The whole reason HEx exists.

- ⬜ **Invite** — capability links: single-use, expiring, rate-limited, unguessable
- ⬜ **Accept / signup** — guided wizard via Authentik enrollment
- ⬜ **Provision** — fail-secure, idempotent, precise partial-failure handling
- ⬜ **Dashboard** — personalized per user, strictly scoped
- ⬜ **Request more** — self-service requests gated by owner approval
- ⬜ **Offboard** — remove a user *everywhere* in one action, with drift reconciliation

## Phase 4 · All four provider modes, end to end ⬜

Proving the contract against reality — the v1 bar.

- ⬜ Group/SSO app behind Authentik *(sso_group)*
- ⬜ Jellyfin *(API-managed local accounts)*
- ⬜ Plex *(external invite / share — you don't own the account)*
- ⬜ A manual, no-API service *(owner-authored steps)*

## Phase 5 · Hardening & first release ⬜

- ⬜ OWASP ASVS 5.0 conformance pass (Level 3 on the identity/access core)
- ⬜ Mutation testing on security-critical modules
- ⬜ Signed, provenance-attested, SBOM-bearing releases — verifiable from a public log
- ⬜ Deployer documentation + quickstart *(arrives when HEx is actually runnable by users)*

---

## 🎯 v1.0

> The **complete lifecycle arc** — invite → accept → provision → dashboard → request → **offboard**
> — proven across **all four** provider modes, on a stack you can cryptographically verify.

## Beyond v1

- ⬜ **Breadth** — more providers against the proven contract (Seerr, Mealie, Audiobookshelf, …)
- ⬜ **Android app** — a separate, open client (auth + dashboard first)
- ⬜ Dashboard polish, theming, and richer per-service widgets
- ⬜ More deployment targets (LXC, VM, native per-OS)

---

<div align="center">
<sub>Following along? ⭐ Star and 👀 watch the repo — every slice lands in the open.</sub>
</div>
