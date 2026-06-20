# Security Policy

HEx is an access-orchestration layer that, by design, holds credentials to downstream
services and can provision identities. We take its security posture seriously and treat
both the running application and the release pipeline as part of the attack surface.

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Please report privately via GitHub's **private vulnerability reporting** (Security →
Report a vulnerability) on this repository, or by the contact listed there. Include:

- a description of the issue and its impact,
- steps to reproduce or a proof of concept,
- affected version/commit,
- any suggested remediation.

We aim to acknowledge reports promptly, keep you updated on remediation, and credit
reporters who wish to be credited once a fix is released. Please give us a reasonable
window to remediate before any public disclosure.

## Scope

In scope: the HEx backend, frontend, provider integrations, the invite/signup surface, the
secrets and audit subsystems, and the release/build pipeline.

Out of scope: vulnerabilities in third-party services HEx integrates with (report those
upstream), and issues that require a pre-existing full compromise of the host.

## Security posture (summary)

- **Identity:** Authentik is the source of truth; HEx is a relying party and never
  reimplements authentication. The sole local credential is a minimal, disabled-by-default,
  condition-gated **break-glass** owner login for when Authentik is unreachable — MFA,
  Argon2id, rate-limited, and loudly audited on every use. (`docs/decisions/0001`, `0008`)
- **Open by design, no phone-home.** The codebase and full security model are public
  (Kerckhoffs: security rests on secret keys, never secret code — **no security through
  obscurity**). HEx makes no outbound connections except to owner-configured systems, ships
  no telemetry/analytics, and never exfiltrates user data, credentials, or ledger/audit
  content. (`docs/TRANSPARENCY.md`)
- **Standard:** targets OWASP ASVS 5.0 — Level 3 on the identity/access/secrets/audit
  core, Level 2 elsewhere.
- **Secrets:** no plaintext at rest; envelope-encrypted; the app refuses to boot with
  missing/weak/default secrets; no usable secret ships in any example. (`docs/SECRETS.md`)
- **Least privilege:** per-provider service accounts scoped to exactly what they provision;
  HEx holds no god-credentials.
- **Trust boundaries:** proxy-injected identity headers are never trusted on their own;
  every request is independently authorized server-side; clients hold no downstream
  secrets. (`docs/SECURITY_MODEL.md`, `docs/THREAT_MODEL.md`)
- **Auditability:** append-only, tamper-evident log of all privileged actions.
- **Supply chain:** releases are keyless-signed (cosign), carry SLSA provenance and an
  SBOM, and are built from pinned dependencies and SHA-pinned actions; CI scans for vulns
  and leaked secrets. (`docs/SUPPLY_CHAIN.md`)

## For deployers

HEx is secure-by-default and will refuse to start in an insecure configuration. Run it
behind your reverse proxy with Authentik in front, generate all secrets as instructed in
`.env.example` (never reuse the examples — they are empty by design), and verify release
artifacts with cosign before deploying.
