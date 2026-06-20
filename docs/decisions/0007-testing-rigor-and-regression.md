# 0007 — Testing rigor and regression monitoring from the outset

- Status: **Accepted**
- Date: project inception

## Context

A regression in HEx's auth, provisioning, or offboarding is a security incident, not a
cosmetic bug. The owner wants extremely strict testing across the board — backend **and**
frontend — with regression monitoring in place from the very first commit, not retrofitted.

## Decision

Adopt a strict, regression-first testing strategy (full detail in `docs/TESTING.md`):

- **Full suite on every change** as a merge gate; any failure blocks merge. No
  affected-only runs as the gate.
- **Coverage ratchets:** 80% global / 95% security-critical, and coverage may never
  silently decrease. Behavior baselines (including visual/UI snapshots) ratchet too.
- **No-skip policy.** Flaky tests are fixed or quarantined with a tracking issue, never
  ignored to pass CI. Tests are deterministic, seeded, isolated, parallel-safe.
- **Abuse/failure tests are mandatory** for security-critical paths (authz boundaries,
  invite capabilities, header-trust rejection, fail-secure provisioning, boot refusal,
  break-glass).
- **Frontend is tested as rigorously as the backend:** Vitest + React Testing Library +
  MSW for units/components, Playwright for full lifecycle E2E, accessibility checks, and
  visual-regression baselines reviewed like code.
- **Mutation testing** on security-critical modules ensures tests actually catch bugs; a
  surviving mutant there is a defect.
- **Provider conformance tests** are required for every provider.

## Consequences

- CI has parallel backend and frontend pipelines, both blocking, plus visual-regression
  review, conformance, mutation (at least scheduled + on critical-module changes), and the
  supply-chain scans.
- Some upfront velocity is traded for the guarantee that nothing silently regresses. For an
  access-control tool that trade is correct.
- The quality gates in `CLAUDE.md` and `CONTRIBUTING.md` reflect this, and the reference CI
  skeletons include frontend jobs.
