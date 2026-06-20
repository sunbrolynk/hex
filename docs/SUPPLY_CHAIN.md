# Supply-Chain Security

For an OSS tool that becomes the most privileged box in someone else's lab, the build and
release pipeline is part of the attack surface: poison it once, compromise every deployer.
Supply-chain hardening is a first-class design concern here, not a release-day afterthought.

Standards referenced (current as of the research behind these docs): **SLSA** build track
(v1.0 → v1.2, the latter adding a Source track), **Sigstore/cosign** keyless signing via
GitHub Actions OIDC → Fulcio → Rekor, **SBOM** in CycloneDX/SPDX via Syft, and **OpenSSF
Scorecard**.

## Targets

- **SLSA Build L3-equivalent** for release artifacts: signed provenance, built on hosted
  infrastructure with isolation, no signing secrets on developer machines. Realistic for a
  solo dev via GitHub Actions + `slsa-github-generator`.
- **Every released container image is signed** (keyless) and carries **provenance** and an
  **SBOM**, all verifiable from the public Rekor transparency log.
- **All dependencies and all GitHub Actions are pinned**; updates are reviewed, not
  automatic-merged.
- **CI fails on** known-vulnerable dependencies, leaked secrets, and (optionally) Scorecard
  regressions.
- **Secure by default for the deployer** — the runtime refuses to start insecure (see
  SECRETS).

## 1. Signing + provenance + SBOM (keyless, no long-lived keys)

Use **cosign keyless** signing. The GitHub Actions OIDC token proves "this workflow in
this repo built this," Fulcio issues a short-lived certificate, Rekor logs the signature
immutably. No private key to store or leak.

Per release:

- `cosign sign` the image by digest using the Actions OIDC identity (`id-token: write`).
- Generate an SBOM with **Syft** in both CycloneDX and SPDX JSON, and attach it as a
  signed attestation (`cosign attest --type cyclonedx` / `spdxjson`).
- Generate **SLSA provenance** (`slsa-github-generator`, predicate `slsa.dev/provenance/v1`)
  and attach it as an attestation.
- Publish a `cosign verify` / `cosign verify-attestation` snippet in the README so
  deployers can verify image, provenance, and SBOM against your expected OIDC identity
  before deploying.

Pin the cosign identity in verification docs to
`https://github.com/<org>/<repo>/.github/workflows/<release>.yml@refs/tags/...` and issuer
`https://token.actions.githubusercontent.com`.

## 2. Dependency hygiene

- **Pin everything.** Python deps locked with hashes (e.g. `uv`/`pip-tools` producing a
  hash-pinned lockfile); JS deps via a committed lockfile. Reproducible installs.
- **Pin GitHub Actions to full commit SHAs**, not tags — a tag can be repointed at
  malicious code; a SHA cannot. (`actions/checkout@<sha>`, not `@v4`.)
- **Renovate** (or Dependabot) opens PRs for updates, including SHA-pinned action bumps
  with the human-readable version in a comment. **Review and merge manually** — never
  auto-merge into a security-critical project.
- **Vulnerability scanning in CI:** `pip-audit` / `osv-scanner` for Python, the JS
  ecosystem equivalent, and **Grype** against the built image. Known-high/critical vulns
  fail the build (with a documented, time-boxed exception path).
- **Secret scanning:** `gitleaks` in CI and as a local pre-commit hook; a hit fails the
  build.
- **Minimal base image** (distroless or slim), non-root runtime user, dropped
  capabilities, read-only root filesystem where possible.

## 3. Pipeline hardening

- **Least-privilege `GITHUB_TOKEN`:** default to `permissions: {}` and grant per-job only
  what is needed (`id-token: write` only on the signing job, `packages: write` only on
  push, etc.).
- **Protected release workflow:** releases build only from tags on protected branches;
  no release path runs untrusted PR code with secrets.
- **Separate build from sign** so the signing step has the narrowest possible inputs.
- **OpenSSF Scorecard** runs on a schedule and surfaces repo-hygiene regressions
  (branch protection, token permissions, pinned deps, dangerous workflow patterns).
- **CodeQL** (or equivalent SAST) on PRs.

## 4. Repo hygiene that is also supply-chain

- Branch protection on the default and release branches; required reviews; required status
  checks (tests, lint, scans) green before merge.
- Signed commits/tags where practical.
- A `SECURITY.md` with a private vulnerability-disclosure path (shipped).
- A documented **threat model** (shipped) so contributors share the security model.

## 5. Reference workflow sketches

Skeletons live in `docs/ci/` as **reference, not runnable** (they reference repo specifics
that do not exist yet). Build the real workflows with the owner against the live repo;
do not copy a workflow that hasn't been verified to run. The skeletons capture: SHA-pinned
actions, least-privilege permissions, build → SBOM → sign → provenance ordering, and the
scan gates.

## Why this is in the repo from commit one

Retrofitting signing, pinning, and provenance after the fact is painful and tends to be
skipped. Establishing the pattern before there is a release means every release inherits
it. For a tool with HEx's privilege level, a deployer being able to **cryptographically
verify** that the image they run came from your pipeline — unmodified — is a core feature,
not polish.
