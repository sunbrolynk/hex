# Transparency & Openness

HEx is built to be **fully open and auditable**, in the spirit of the *arr stack and the
best of the self-hosted ecosystem. A tool that holds the keys to someone's whole lab has to
*earn* trust, and the only durable way to earn it is to let people read exactly what the
code does — including, especially, the security-relevant parts.

This is also the correct *security* posture, not a concession against it. See below.

## Posture

- **Source-available and open, like the *arr apps.** The codebase is public and readable.
  Anyone can verify there is no data theft, no hidden exfiltration, and no phone-home.
- **No telemetry, no phone-home, by default.** A default HEx build makes **zero** outbound
  network connections except to the systems the owner explicitly configures (Authentik and
  the enabled providers). It does not call any HEx-operated server. There is no analytics
  beacon, no usage reporting, no "anonymous stats" turned on quietly.
- **All data stays local.** Users, the provisioning ledger, the audit log, and all
  configuration live on the owner's instance and are never transmitted anywhere by HEx.
- **Every outbound connection is documented.** The docs enumerate exactly what HEx talks
  to and why. If you can't find a destination in that list, HEx shouldn't be reaching it —
  and because the code is open, you can confirm it isn't.

## Why open is *more* secure here, not less

HEx follows **Kerckhoffs's principle**: the security of the system rests on the secrecy of
**keys**, never on the secrecy of the **code or design**. Everything in `docs/` —
the architecture, the threat model, the exact security controls — is public on purpose.

- **No security through obscurity, anywhere.** If a control only works because an attacker
  hasn't read the source, it isn't a control. We assume the attacker has read everything.
- **More eyes find more holes.** An open security model invites the community to audit it
  and report weaknesses (exactly what `SECURITY.md` and `CONTRIBUTING.md` are for). That is
  a feature, not a risk.
- **Verifiability.** Signed, provenance-attested, SBOM-bearing releases (see
  `SUPPLY_CHAIN.md`) let a deployer prove the image they run is built from this public
  source, unmodified. Open code plus verifiable builds = you can trust what you run because
  you can check it.

## What HEx must never do (enforced as design constraints)

- **Never exfiltrate user data, credentials, or ledger/audit contents** off the owner's
  instance. This is an architectural invariant, tested for, and called out in the threat
  model (HEx itself is modeled as something that must not become an exfiltration channel).
- **Never add silent telemetry.** Any future opt-in diagnostics would be: off by default,
  explicitly enabled by the owner, with the **exact payload documented and visible**, never
  containing secrets or user PII, and to a destination the owner controls or explicitly
  approves.
- **Never phone home for licensing, "activation," or feature gating.** HEx does not change
  behavior based on contacting an HEx-operated server.
- **Never run a maintainer-operated service at all.** No project-run backend for licensing,
  telemetry, analytics, or anything else — it would defeat the purpose of a self-hosted tool.
  The only network destination is the user's own HEx instance. (ADR 0012.)
- **Never gate, nag, or use dark patterns.** Nothing is withheld or locked; every build is
  functionally identical for everyone. Attribution and project links are offered quietly, only
  in a tucked-away **About/Credits** section near the GitHub link (proper attribution to the
  libraries and upstream apps HEx builds on, plus repo/site/donation links). No nag prompts or
  "upgrade" banners, anywhere. (ADR 0012.)

## The narrow set of things that are *not* fully public — and why

Transparency is the default. There are exactly two deliberate, bounded exceptions, and
neither is "hidden code":

1. **Secrets and keys.** Obviously never in the repo (enforced by `.gitignore` + CI secret
   scanning, see `SECRETS.md`). Security rests on these being secret; that is Kerckhoffs,
   not obscurity.
2. **Pre-fix vulnerability details (coordinated disclosure timing only).** When a
   vulnerability is reported, the *weaponized details* are held until a fix ships and
   deployers have a reasonable window to update — then disclosed. The **code stays open the
   entire time**; we simply don't publish a ready-to-use exploit before the patch. This is
   responsible disclosure, the standard practice of every serious open-source security
   project, and the opposite of hiding the design. See `SECURITY.md`.

That's the whole list. Architecture, controls, data flows, and the security model are all
public.

## "Warn us if there's a hole"

That request is already wired into the project:

- **`SECURITY.md`** — a private, coordinated vulnerability-disclosure path so finders can
  report holes responsibly.
- **`CONTRIBUTING.md`** — contributor security gates and a security-review pass against the
  threat model on security-relevant changes.
- **Open code + published threat model + SBOM** — so the community can audit HEx the same
  way they audit the *arr apps, and see precisely how secure (or not) any given path is.

## If we ever close something up

The owner is open to closing a surface *only* where there is a concrete security reason,
and that reason must be **stated in the docs.** "Closing up" never means hiding code or the
security model — at most it means hardening defaults, reducing an exposed surface, or
narrowing what an endpoint reveals (e.g., enumeration-resistant error responses, which are
already specified). If a proposed change reduces transparency, it requires an explicit,
written justification in an ADR. Default is open.
