# CI reference skeletons

These files are **reference patterns, not runnable workflows.** They reference repo
specifics (org/repo names, image paths, workflow filenames, branch protections) that do
not exist yet, and they have not been verified against a live repo.

**Do not copy them into `.github/workflows/` and assume they run.** Build the real
workflows together with the owner against the live repository, verifying each step. These
skeletons exist to capture the *patterns* that matter:

- GitHub Actions pinned to **full commit SHAs**, not tags.
- **Least-privilege `permissions`** — default `{}`, grant per-job only what's needed
  (`id-token: write` only on the signing job, `packages: write` only on push).
- Ordering: **build → SBOM (Syft) → keyless sign (cosign) → SLSA provenance → attest**.
- **Scan gates**: `pip-audit`/`osv-scanner` + Grype + gitleaks must pass.
- **Frontend tested as rigorously as backend**: Vitest/RTL/MSW units, Playwright lifecycle
  E2E, and visual-regression diffs that must be reviewed (not auto-accepted).
- **Mutation testing** on security-critical modules (scheduled + on critical-module changes).
- Releases build only from tags on protected branches; no secret-bearing job runs
  untrusted PR code.

See `docs/TESTING.md` for the full testing strategy and `docs/SUPPLY_CHAIN.md` for the
signing/provenance rationale and the verification snippet deployers will use.

Files:

- `ci.yml.reference` — PR/push checks: backend lint/type/test+coverage, frontend
  lint/type/unit/E2E/visual, dependency & secret scans, CodeQL, mutation (commented).
- `release.yml.reference` — tag-triggered build, SBOM, keyless sign, provenance, publish.
