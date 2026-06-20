# Contributing to HEx

Thanks for your interest. HEx is a security-sensitive tool — it orchestrates access to an
entire homelab — so the contribution bar leans toward correctness and assurance over speed.

## Before you start

Read, in order: `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/PROVIDER_CONTRACT.md`,
`docs/THREAT_MODEL.md`, `docs/SECURITY_MODEL.md`. The provider contract and the security
model are load-bearing; most design questions are answered there. For code style and
directory layout, follow `CONVENTIONS.md` and `docs/FILE_ARCHITECTURE.md`:
terse-but-professional uniform docstrings, comment the *why*, and small,
single-responsibility files.

## Development workflow

- **Discuss design before large changes.** Open an issue describing the approach; for
  anything touching auth, authz, provisioning, secrets, or the audit log, expect a design
  conversation first.
- **Small, focused PRs.** One concern per PR. Complete files, clear commits.
- **Branch from the default branch**, keep up to date, resolve conflicts cleanly.

## Quality gates (required, enforced in CI — see `docs/TESTING.md`)

Testing is strict and regression-first, on **both** backend and frontend. Full strategy in
`docs/TESTING.md`.

- **Tests: 100% passing**, backend and frontend. A red test blocks merge.
- **Full suite runs on every change** as the gate — no affected-only runs as the gate.
- **Coverage:** 80% global, **95% on security-critical modules** (auth, authz,
  provisioning, secrets, audit, invite handling, break-glass). **Coverage ratchets — never
  silently decreases.**
- **No-skip policy.** No skipped/`xfail`ed/commented-out tests to make CI green; flaky tests
  are fixed or quarantined with a tracking issue. Tests are deterministic and seeded.
- **Abuse/failure tests required** for security-critical paths — prove the fail-secure
  behavior, not just the happy path.
- **Frontend tested as rigorously as backend:** Vitest + React Testing Library + MSW for
  units/components, Playwright for lifecycle E2E, accessibility checks, and
  **visual-regression baselines reviewed like code**.
- **Mutation testing** on security-critical modules — a surviving mutant is a defect.
- **Zero linter warnings** (ruff + frontend lint). Formatting consistent.
- **Type-checked.** Pydantic v2 models for all external input; reject unknown fields on
  security-relevant payloads.

## Security & transparency gates (required)

- No secrets in the repo. Secret scanning (gitleaks) runs in CI and as a pre-commit hook;
  a hit fails the build. Example config uses empty fields + generation commands only —
  never a usable value.
- **No phone-home / no telemetry.** PRs that add outbound network calls to anything other
  than owner-configured systems, or that add analytics/telemetry, are rejected. Any future
  opt-in diagnostics must follow `docs/TRANSPARENCY.md` (off by default, documented payload,
  no secrets/PII). HEx must never exfiltrate user data, credentials, or ledger/audit content.
- **No security through obscurity.** Don't rely on a control being unreadable; assume the
  attacker has read the source.
- Dependencies pinned (hash-locked); GitHub Actions pinned to commit SHAs. Dependency and
  image vulnerability scans (`pip-audit`/`osv-scanner`/Grype) must pass.
- Security-relevant PRs get a review pass against the threat model and SECURITY_MODEL
  before merge. The maintainer is the final human override on every merge.
- Never weaken a non-negotiable (CLAUDE.md) to make something pass. If a non-negotiable is
  in your way, that is a design discussion, not a workaround.

## Contributing a new provider

Providers are the main extension point. A provider PR must:

1. Declare both axes correctly — `integration_mode` **and** `identity_owner`. Getting
   `identity_owner` wrong (e.g. marking an external-IdP service as `provider`) is the
   classic offboarding bug; reviewers will check this specifically.
2. Implement the full interface with **idempotent, fail-secure** `provision` and
   **idempotent, aggressive** `deprovision` (revoke-the-share, not delete-the-account, for
   `identity_owner = external`).
3. Define and validate a **structured grant schema** — never a boolean.
4. Scope `widget_data`/`status` strictly to the requesting user.
5. Ship **contract-conformance tests** (idempotency, fail-secure, correct deprovision
   semantics, no cross-user leakage).
6. Document the **minimum service-account scope** the provider needs downstream.
7. Not require HEx to hold an admin/god credential for the service.

## Reporting security issues

Do **not** open a public issue. See `SECURITY.md` for private disclosure.

## Code of conduct

Be civil and constructive. Assume good faith. This is a community project; help others get
their setups working.

## Licensing of contributions

HEx is licensed under **AGPL-3.0**. By contributing, you agree your contributions are
licensed under the same terms (inbound = outbound). Keep this in mind for any third-party
code or assets you include — they must be license-compatible.
