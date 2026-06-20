# Testing Strategy

Testing is a **merge gate, not an aspiration**, and it is strict from commit one — on both
the backend and the frontend. HEx hands out access to an entire homelab; a regression in
auth, provisioning, or offboarding is a security incident, not a bug. The strategy below is
designed to catch regressions the moment they appear and to prove the *abuse* cases, not
just the happy path.

## Principles

- **Full suite on every change.** No partial/affected-only runs as a gate. Every change
  runs the complete backend and frontend suites in CI; any failure blocks merge.
- **Regression is the enemy.** The point of the suite is to make it impossible to silently
  break something that used to work. Coverage and behavior **ratchet** — they may go up,
  never quietly down.
- **No-skip policy.** Tests are not skipped, `xfail`ed, or commented out to make CI green.
  A flaky test is fixed or quarantined with a tracking issue, never ignored.
- **Determinism.** Tests are seeded, isolated, parallel-safe, and free of real network/time
  dependencies (clocks and external calls are controlled).
- **Abuse-case coverage is mandatory** for security-critical paths — prove fail-secure
  behavior with a test, don't assume it.

## The test pyramid (front + back)

```
            ▲  E2E lifecycle flows (Playwright): invite→provision→dashboard→request→offboard
           ███ Security/abuse tests: authz boundaries, capability tokens, header-trust, boot-refusal
          █████ Contract/conformance tests: every provider against the provider contract
         ███████ Integration tests: API + DB + provider clients (mocked downstreams)
        █████████ Unit/component tests: backend units + React components
```

## Backend testing

- **Framework:** pytest (+ async). 100% pass required.
- **Coverage gate:** 80% global, **95% on security-critical modules** (auth, authz,
  provisioning, secrets, audit, invite handling, break-glass). Coverage cannot decrease.
- **Conventions (owner standing rules):** mock at the **router's import path**; assert API
  errors via `response.json()["error"]`; run the **full suite before any push is proposed**;
  zero ruff warnings.
- **Required abuse/failure tests** include, at minimum:
  - authorization boundary: user A cannot read or act on user B's ledger/requests/widgets;
    a user cannot self-grant a non-requestable service; a user cannot reach owner-only
    routes.
  - invite capability: single-use (hard cap 1; concurrent double-accept loses the race
    safely), expiry, ≥128-bit entropy, enumeration-resistant + uniform-timing responses.
  - **header-trust:** a request carrying spoofed identity headers but lacking a valid OIDC
    token / proxy shared-secret is rejected.
  - **fail-secure provisioning:** an uncertain/timed-out provider call yields `FAILED` and
    grants nothing; deprovision is idempotent and uses revoke-not-delete for
    `identity_owner = external`.
  - **boot refusal:** missing/weak/denylisted secrets abort startup (see SECRETS).
  - **break-glass:** disabled-by-default; rejected when its activation condition isn't met;
    rate-limit/lockout enforced; every use emits a high-severity audit event; MFA enforced
    if configured. (See SECURITY_MODEL.)

## Frontend testing

- **Unit/component:** Vitest + React Testing Library. Components tested for behavior and
  accessibility, not implementation detail.
- **API mocking:** MSW (Mock Service Worker) so component/integration tests exercise real
  request/response handling without a live backend.
- **E2E:** Playwright drives the **full lifecycle arc** in a browser against a test
  backend: invite acceptance → signup wizard (all four provider modes represented) →
  dashboard → request-more/approval → offboard. These are the flows whose regression would
  hurt most, so they are covered end to end.
- **Accessibility checks** in component and E2E layers (axe or equivalent).
- **Coverage gate** for the frontend mirrors the backend intent: a global floor plus a
  higher bar on security-relevant UI (auth flows, invite/signup, owner config). Coverage
  ratchets, never silently drops.

## Visual / UI regression

- **Snapshot + visual regression** (Playwright screenshots, or a component story baseline)
  so unintended UI changes are caught and must be explicitly approved. Baselines are
  reviewed like code; an unreviewed visual diff blocks merge.

## Provider contract conformance

Every provider ships conformance tests proving idempotency, fail-secure provisioning,
correct `deprovision` semantics for its `identity_owner`, and no cross-user data leakage.
A provider without passing conformance tests does not ship. (See `PROVIDER_CONTRACT.md`.)

## Mutation testing on security-critical code

To ensure the tests *actually* catch bugs (not just execute lines), run **mutation testing**
on the security-critical modules — e.g. `mutmut`/`cosmic-ray` (Python) and Stryker
(JS/TS). A surviving mutant in auth/authz/provisioning/secrets/invite handling is a missing
test and is treated as a defect. This is the antidote to high-coverage-but-weak tests.

## Load / abuse smoke on the unauthenticated surface

The invite-acceptance and signup endpoints get a lightweight load/abuse smoke test in CI to
validate that rate limiting, lockout, and enumeration resistance hold under repeated and
concurrent requests.

## CI enforcement (summary)

A PR merges only when **all** of these are green: backend lint + type + full suite +
coverage gate, frontend lint + type + full suite + coverage gate, visual-regression review,
provider conformance, dependency + secret + image scans (see SUPPLY_CHAIN). Mutation testing
on security-critical modules runs at least on a schedule and on changes to those modules.
The owner is the final human override on every merge.
