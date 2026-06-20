# 0004 — Security and supply chain are core mission

- Status: **Accepted**
- Date: project inception

## Context

HEx is structurally the most privileged box in the lab: it holds credentials to every
downstream service and can mint identities in Authentik. It is also OSS, deployed by people
who are not security experts, with an unauthenticated invite/signup surface. The blast
radius of a compromise — of the running app *or* of the release pipeline — is the whole
homelab, for every deployer.

## Decision

Security and supply-chain integrity are **architectural requirements from commit one**, not
post-launch hardening. Specifically:

- Target **OWASP ASVS 5.0**: Level 3 on the identity/access/secrets/audit/invite core,
  Level 2 elsewhere.
- The load-bearing security decisions in SECURITY_MODEL are **not bolt-on-able later** and
  must be designed in: never trust proxy-injected headers; per-provider least-privilege
  service accounts (no god-credentials); no plaintext secrets + refuse-to-boot-insecure;
  invite links as single-use capabilities; fail-secure provisioning; append-only
  tamper-evident audit log; server-side authz with an absolute owner/user boundary; BFF so
  clients hold nothing.
- **Supply chain is part of the product:** signed artifacts (cosign keyless), SBOM,
  SLSA provenance, pinned dependencies and SHA-pinned actions, CI scanning, secure-by-
  default runtime. A deployer must be able to cryptographically verify the image came from
  the pipeline unmodified.

## Consequences

- Security-critical modules carry a higher coverage gate (95%) and require abuse/failure-
  case tests, not just happy-path.
- A read-only security-review pass against the threat model gates security-relevant
  changes; the owner is the human override on every merge.
- The threat model and security model are living documents; ASVS conformance is tracked
  per chapter as modules land.
- Some velocity is traded for assurance. For a tool that hands out access to an entire
  lab, that trade is correct.
