# CLAUDE.md — HEx operating manual

> This file is auto-loaded by Claude Code. It is the contract for how you work in
> this repository. Read it fully before doing anything. When in doubt, the rule is:
> **stop and ask, do not assume.**

## What HEx is (one paragraph)

HEx ("The Homelab Experience") is a self-hosted **access-orchestration and experience
layer** for a homelab. It is the front door that turns an owner's invitation into real,
governed accounts and permissions across heterogeneous self-hosted services, gives each
user a personalized dashboard, lets users self-serve requests for more access (gated by
owner approval), and — critically — can cleanly **offboard** a user across every service
at once. The dashboard is the *surface*; the orchestration + lifecycle is the *product*.

HEx is **not** a dashboard-with-login. A dozen mature tools already do dashboards
(Homepage, Homarr, Dashy). Do not rebuild that. The defensible core is the lifecycle arc
and the provider model below.

## Non-negotiables (these are not refactor-later items)

These are architectural load-bearing walls. If a task would violate one, **stop and
flag it** rather than proceeding.

1. **Authentik is the identity source of truth. HEx never reimplements auth.** HEx
   drives Authentik's API; it does not become an IdP. **Authentik is bundled and required:**
   HEx ships and orchestrates the Authentik stack (one `docker compose up` rolls both), and
   **first run is a guided bootstrap, never a crash** — HEx enters a secured setup mode,
   wires Authentik via bootstrap token + shipped blueprints, hardens, then proceeds to owner
   setup. The one local-auth exception is the **break-glass** login (non-negotiable 12).
   Normal login is pure OIDC. See ADRs 0001 + 0010, `docs/DEPLOYMENT.md`, `docs/BOOTSTRAP.md`.
2. **Never trust proxy-injected identity headers.** Validate OIDC tokens against
   Authentik's JWKS, or enforce mTLS/shared-secret between proxy and app. Assume the
   app container is directly reachable by an attacker who can set any header.
3. **HEx never holds god-credentials.** Every downstream integration uses a
   least-privilege, per-provider service account scoped to exactly what it provisions.
4. **Secrets are never stored in plaintext, and the app refuses to boot insecure.**
   No default credentials, no placeholder secrets that "work." Missing/weak secret →
   hard fail at startup. See `docs/SECRETS.md`.
5. **Invite links are capabilities:** single-use (hard cap of 1 acceptance), short TTL,
   ≥128 bits of entropy, rate-limited, enumeration-resistant.
6. **Fail secure on provisioning.** If the outcome of a provider call is uncertain, do
   NOT grant. Deprovision is the opposite: aggressive and idempotent.
7. **Every privileged action is written to an append-only, tamper-evident audit log.**
8. **Authorization is enforced server-side on every request.** The owner/user boundary
   is absolute. Never trust a role claim from the client. A user can never see another
   user's ledger, tokens, or escalate to owner.
9. **Clients hold nothing.** Backend-for-frontend (BFF). The web and future Android
   clients talk only to the HEx API with a user-scoped token. Downstream secrets never
   leave the server.
10. **Supply chain is part of the product, from commit one.** Signed artifacts, SBOM,
    provenance, pinned dependencies and actions, scanning in CI. See `docs/SUPPLY_CHAIN.md`.
11. **Open and no phone-home.** The codebase and full security model are public
    (Kerckhoffs: security rests on secret *keys*, never secret code). HEx makes **zero**
    outbound connections except to owner-configured systems — no telemetry, no analytics,
    no licensing callbacks. HEx **never exfiltrates** user data, credentials, or
    ledger/audit content. No security through obscurity. See `docs/TRANSPARENCY.md`.
12. **Break-glass is the one local credential and is tightly bounded.** Disabled by
    default, single owner account, condition-gated (only when Authentik/OIDC is
    unreachable and/or local-only path), MFA, Argon2id, rate-limited + lockout, every use
    is a high-severity audit event. It is never a routine bypass of Authentik-as-SoT.
    The recovery path must not depend on the thing that's broken (offline-verifiable MFA).
    See `docs/decisions/0008`, `docs/BREAK_GLASS.md`, and SECURITY_MODEL §13.
13. **No gating, no dark patterns, no maintainer service.** Nothing is withheld or locked;
    every build is functionally identical for everyone, however installed. Never add gating
    checks, "upgrade" prompts, nag dialogs, banners, analytics, or any
    project-operated backend. Attribution and project links live only in a single tucked-away
    **About/Credits** section near the GitHub link (dependency/upstream attribution +
    repo/site/GitHub + donation links). If a change would add any of the above, **stop and
    flag it.** See `docs/decisions/0012`.

## Read these before designing or coding (in order)

1. `docs/ARCHITECTURE.md` — system shape, Authentik-as-SoT, the orchestration boundary.
2. `docs/PROVIDER_CONTRACT.md` — **the spine.** The four integration modes, the two
   orthogonal axes (`integration_mode` × `identity_owner`), the structured grant object,
   the method interface, and the provisioning ledger. Everything plugs into this.
3. `docs/LIFECYCLE.md` — invite → provision → dashboard → request → offboard, and the
   ledger/reconciliation that makes offboarding actually work.
4. `docs/DEPLOYMENT.md` — the bundled stack (HEx + Authentik server/worker + datastores);
   one compose rolls both.
5. `docs/BOOTSTRAP.md` — first-run guided setup: bootstrap mode → wire Authentik → harden →
   owner setup. Never crash on first run.
6. `docs/THREAT_MODEL.md` — who attacks HEx and how. HEx is the most privileged box in
   the lab; design accordingly.
7. `docs/SECURITY_MODEL.md` — concrete crypto, token validation, header-trust, authz.
8. `docs/SECRETS.md` — secret generation, storage, the "generation instructions not
   placeholders" rule.
9. `docs/SUPPLY_CHAIN.md` — SLSA, cosign keyless signing, SBOM, pinning, scanning.
10. `docs/TRANSPARENCY.md` — open-source posture, no phone-home, what's open vs. the narrow
   closed set (secrets + coordinated vuln disclosure) and why.
11. `docs/TESTING.md` — the strict, regression-first testing strategy (front + back).
12. `docs/WORKFLOW.md` — delivery cadence + Claude Code gating: vertical slices, runnable
   checkpoints, and the committed `.claude/` permission rules and hooks.
13. `docs/BREAK_GLASS.md` — emergency-access design + operational runbook.
14. `CONVENTIONS.md` — code style: terse-but-professional docstrings, comment discipline,
   naming, small single-responsibility files.
15. `docs/FILE_ARCHITECTURE.md` — the directory layout and the proposed HEx tree
   (providers use a `base.py` + one-file-per-implementation pattern).
16. `docs/ANDROID.md` — foundation for the separate Android client repo (untrusted-client
   model, untrusted-client security model, stack, and when to start).
17. `docs/decisions/` — the locked architectural decisions (ADRs). These are settled;
   do not relitigate without explicit say-so.

**The single most important rule for v1: design and freeze the provider contract before
writing feature code.** The security model rides on it.

## Assumed stack (confirm before scaffolding)

- Backend: **FastAPI** (Python 3.12+), async, Pydantic v2.
- DB: **PostgreSQL 15+**, SQLAlchemy async + Alembic migrations.
- Frontend: **React 19**.
- Testing: backend **pytest** (async); frontend **Vitest + React Testing Library + MSW**
  and **Playwright** for lifecycle E2E; visual-regression baselines; mutation testing on
  security-critical modules. Strict and regression-first — see `docs/TESTING.md`.
- Password hashing (for any HEx-local credential): **argon2-cffi**, Argon2id, OWASP
  floor `m=19456, t=2, p=1` (tune *up* — this is an identity service; see SECURITY_MODEL).
- Auth: **Authentik** via OIDC for HEx's own login; Authentik REST API + a scoped
  service-account token for provisioning.
- Packaging: Docker image published to GHCR.

These are the project's assumed stack and are not yet committed in code. If any differ from
the intended direction, raise it before scaffolding.

## How you work here (maintainer conventions)

- **Confirm before coding.** Propose the plan; wait for the go-ahead.
- **One file at a time**, with review between files. Output **complete files**, not diffs.
- **Read a file before proposing edits to it.** Never edit blind.
- **The maintainer is the executor.** You do not commit, push, or merge. You produce; the
  maintainer reviews and commits.
- **No preambles, no restating the question.** Lead with the answer, then context.
- **Push back concretely.** If something is wrong, say so with reasoning, not hedging.
- **Batch questions** under named buckets; don't dribble them out one at a time.
- **Never edit files directly on a production server.**
- **Work in runnable vertical slices, stop at checkpoints.** Build thin end-to-end slices
  that the maintainer can start and *see*; "compiles" is not "done." Plan first (plan mode),
  then at each checkpoint hand back a diff plus the exact command/URL to run and visually
  verify it, and **wait** — do not build the next slice on an unreviewed, unrun one. The
  committed `.claude/` rules enforce the guardrails; see `docs/WORKFLOW.md`.
- **Match the house style and layout.** Follow the directory conventions in
  `docs/FILE_ARCHITECTURE.md` and the code style in `CONVENTIONS.md`: terse docstrings
  (three words if three suffice), never restate a name or file path, comment the *why* not
  the *what*, one responsibility per file kept small, and one uniform docstring style across
  the whole repo. Providers follow the `base.py` + one-file-per-implementation pattern.

## Quality gates (hard, not aspirational — see `docs/TESTING.md`)

Testing is strict and **regression-first from commit one**, on **both** backend and
frontend. The full intent lives in `docs/TESTING.md`; the gates:

- Test pass rate is **100%**, backend and frontend. A red test blocks everything.
- **Full suite runs on every change** as the merge gate — no affected-only runs as the gate.
- Coverage gate: **80% global, 95% on security-critical modules** (auth, authz,
  provisioning, secrets, audit, invite handling, break-glass). **Coverage ratchets — it
  may go up, never silently down.**
- **No-skip policy.** Tests are never skipped/`xfail`ed/commented to make CI green; flaky
  tests are fixed or quarantined with a tracking issue. Tests are deterministic and seeded.
- **Zero linter warnings** (ruff, plus frontend lint). Run the full suite before any push.
- Security-critical paths require **abuse/failure tests**, not just happy path —
  fail-secure behavior must be proven by a test (authz boundaries, capability tokens,
  header-trust rejection, boot refusal, break-glass).
- **Frontend tested as rigorously as backend:** Vitest/RTL/MSW units, Playwright lifecycle
  E2E, accessibility checks, and **visual-regression baselines reviewed like code**.
- **Mutation testing** on security-critical modules — a surviving mutant there is a defect.
- Every new provider ships with a contract-conformance test (see PROVIDER_CONTRACT).

## Recommended commit-gate pattern (optional but encouraged)

Given the privilege level of this app, a **read-only reviewer pass before any change is
proposed for commit** is worth the overhead: a second pass whose only job is to check the
diff against the non-negotiables above and the threat model, with the maintainer as the
final
human override on every merge. Treat security-relevant changes as merge-blocking until
that review is clean.

## When you are unsure about an external system

Provider integrations depend on third-party APIs (Authentik, Plex, Jellyfin, Seerr,
Mealie, etc.) whose behavior changes. **Do not guess an endpoint, scope, or auth flow.**
State the uncertainty, and either ask the maintainer or propose a spike to verify against the
live API before building on the assumption.
