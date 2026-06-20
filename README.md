# HEx — The Homelab Experience

> The website that *is* your homelab. An access-orchestration and experience layer that
> onboards, governs, and offboards users across your self-hosted services — driven by
> Authentik, with a personalized dashboard as its face.

**Status:** pre-alpha / design. Not yet released.

---

## What HEx is

HEx turns inviting someone to a homelab into real, governed accounts and permissions
across every service — and, just as importantly, can cleanly remove them everywhere when
they leave. A new user follows an invite link into a guided wizard, gets provisioned into
their default services, lands on a personalized dashboard, can self-serve requests for more
access (gated by owner approval), and can be offboarded across the whole lab in one action.

The dashboard is the surface. The **lifecycle orchestration** is the product:

```
INVITE → ACCEPT/SIGNUP → PROVISION → DASHBOARD → REQUEST MORE → OFFBOARD
```

## What HEx is *not*, and how it relates to existing tools

The self-hosted ecosystem already solves pieces of this, and HEx deliberately does not
rebuild them:

- **Dashboards** (Homepage, Homarr, Dashy, Heimdall) — mature and plentiful. HEx's
  dashboard is intentionally minimal; it is not the value.
- **Media onboarding wizards** (Wizarr) — already excellent at invite → provision for media
  servers (Plex, Jellyfin, Emby, Audiobookshelf, and more). HEx generalizes the *whole*
  lifecycle past media servers and through an identity provider.
- **Identity** (Authentik) — HEx does **not** reimplement auth. Authentik is the source of
  truth; HEx orchestrates it.

The unclaimed ground HEx occupies is the **cohesive, generalized lifecycle arc** — onboard
→ request → personalized experience → **offboard** — across arbitrary self-hosted services,
each modeled as a pluggable provider, with security and supply-chain integrity treated as
core requirements.

## Core design commitments

- **Authentik is the identity source of truth.** HEx does **not** reimplement auth.
  Authentik is **bundled and required** — one command rolls HEx and Authentik together, and
  first run is a guided setup, not a crash. (ADR 0001 + 0010, `docs/DEPLOYMENT.md`,
  `docs/BOOTSTRAP.md`)
- **Every service is a provider** with two orthogonal axes — *how* it provisions and *who*
  owns the identity — which is what makes correct offboarding possible. (ADR 0002,
  `docs/PROVIDER_CONTRACT.md`)
- **The full lifecycle arc, including offboarding, is v1.** (ADR 0003)
- **Security and supply chain are core mission, from commit one.** OWASP ASVS 5.0 (L3 core,
  L2 elsewhere); signed, provenance-attested, SBOM-bearing releases. (ADR 0004,
  `docs/THREAT_MODEL.md`, `docs/SECURITY_MODEL.md`, `docs/SUPPLY_CHAIN.md`)
- **No usable secret ships, ever; the app refuses to boot insecure.** (ADR 0005,
  `docs/SECRETS.md`)
- **Open and no phone-home.** The code and full security model are public; HEx makes no
  outbound connections except to the systems you configure — no telemetry, no analytics,
  no exfiltration of your data. Auditable like the *arr stack. (ADR 0006,
  `docs/TRANSPARENCY.md`)
- **Strict, regression-first testing from commit one**, backend and frontend. (ADR 0007,
  `docs/TESTING.md`)
- **One minimal, tightly-bounded break-glass owner login** for when Authentik is
  unreachable — disabled by default, condition-gated, MFA, loudly audited. Normal login is
  pure Authentik OIDC. (ADR 0008)
- **Free, open, and never gated.** Nothing is withheld or locked; every build is functionally
  identical for everyone. Available via sideload and an official Google Play build. No nags, no
  dark patterns, no analytics, no project-run service. (ADR 0012)

The Android app is a separate, public, OSS repo and a client of this API; see
`docs/ANDROID.md`.

## Tech stack (assumed; see CLAUDE.md)

FastAPI · PostgreSQL · React 19 · Authentik (OIDC + API) · Argon2id · Docker/GHCR.

## Documentation

| Doc | What it covers |
|---|---|
| `CLAUDE.md` | Operating manual + non-negotiables (read first) |
| `docs/ARCHITECTURE.md` | System shape, Authentik-as-SoT, components, trust boundaries |
| `docs/PROVIDER_CONTRACT.md` | **The spine** — four modes, two axes, grants, ledger |
| `docs/LIFECYCLE.md` | The arc, approval workflow, reconciliation, offboarding |
| `docs/DEPLOYMENT.md` | The bundled stack (HEx + Authentik); one compose rolls both |
| `docs/BOOTSTRAP.md` | First-run guided setup and its security |
| `docs/THREAT_MODEL.md` | STRIDE threat model |
| `docs/SECURITY_MODEL.md` | Concrete crypto, token validation, header-trust, authz, audit |
| `docs/SECRETS.md` | Secret generation, envelope encryption, refuse-to-boot |
| `docs/SUPPLY_CHAIN.md` | SLSA, cosign, SBOM, pinning, scanning |
| `docs/TRANSPARENCY.md` | Open-source posture, no phone-home, what's open vs. closed and why |
| `docs/TESTING.md` | Strict, regression-first testing strategy (front + back) |
| `docs/WORKFLOW.md` | Delivery cadence + Claude Code gating (vertical slices, checkpoints) |
| `docs/BREAK_GLASS.md` | Emergency-access design + operational runbook |
| `CONVENTIONS.md` | Code style: docstrings, comments, naming, small-file discipline |
| `docs/FILE_ARCHITECTURE.md` | Directory layout + proposed HEx tree |
| `docs/ANDROID.md` | Foundation for the separate Android client repo |
| `.claude/` | Committed Claude Code permission rules + hook template |
| `docs/decisions/` | Locked architectural decisions (ADRs) |
| `SECURITY.md` | Vulnerability disclosure |
| `CONTRIBUTING.md` | Dev workflow + quality/security gates |

## Verifying releases (planned)

Released images will be keyless-signed with cosign and carry SLSA provenance and an SBOM,
all verifiable from the public Rekor transparency log. A `cosign verify` snippet will live
here so you can confirm the image you run came from this pipeline, unmodified, before
deploying. See `docs/SUPPLY_CHAIN.md`.

## License

**AGPL-3.0.** Strong copyleft that also covers running a modified version as a network
service: anyone who hosts a modified HEx must release their changes under the same license.
This keeps HEx fully open source while preventing closed/proprietary forks. The copyright
holder retains the option to dual-license. The Android client (separate repo) may carry the
same license or a permissive one (e.g. Apache-2.0).
