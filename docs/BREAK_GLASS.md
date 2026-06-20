# Break-Glass: Design & Operational Runbook

This is the operational companion to ADR 0008 and SECURITY_MODEL §13. It covers *how to
build it safely* and *how to operate it* — where to store the credential, when and how to
use it, and how to keep it from quietly rotting into a useless (or dangerous) artifact.

The whole concept of an emergency-access / "break-glass" account is well-established
practice; the canonical reference is the identity-provider world (Microsoft's emergency
access account guidance is the most detailed public treatment), adapted here to a
single-owner self-hosted context.

## The one principle that governs everything

> **The recovery path must not depend on the thing that might be broken.**

HEx's break-glass exists because Authentik (or the internet) can be down. So every part of
the break-glass path must be verifiable **locally, offline, by HEx itself** — no step may
route through Authentik, the internet, email, or any external service. This single rule
drives most of the design decisions below.

## Design requirements (build it this way)

- **Independent of the IdP.** The break-glass credential lives in HEx, not Authentik. That
  independence is the entire point — it must work precisely when Authentik does not.
- **Offline-verifiable second factor.** The MFA factor must be checkable without any
  external dependency: **TOTP** (HEx stores the seed and validates locally) or, stronger,
  **WebAuthn/FIDO2** (phishing-resistant, also local). Never email/SMS/push, which depend on
  services that may be down. Keep MFA on — do not "exclude break-glass from MFA"; just make
  the MFA self-contained. Phishing-resistant methods like FIDO2 or certificate-based auth are the preferred second factor for emergency accounts.
- **Not tied to a person, not synced from the directory.** Emergency access accounts are standalone, with no employee attached, so access does not depend on a specific person being available — and they are not synced from the primary directory. For HEx this means: a dedicated owner-recovery identity, defined locally, never mirrored from Authentik.
- **A second recovery path (redundancy).** Industry practice is two break-glass accounts so that if one is inaccessible a backup still grants access. For a solo homelab, mirror the spirit: have at least one independent backstop beyond the single break-glass login — e.g. a second break-glass credential with independent MFA, **and/or** a documented host-level recovery (direct console/DB access on the box) as the ultimate fallback.
- **Condition-gated + network-constrained.** Accepted only when Authentik/OIDC is
  unreachable and/or via a LAN-only path (see SECURITY_MODEL §13). Prefer not exposing the
  break-glass path to the public internet at all.
- **Strong, unique secret.** Argon2id-hashed (tuned above the OWASP floor). In team
  settings the password is often split into segments held by different people so no single person holds the whole credential; for a solo owner, substitute secure **offline** storage (below).
- **Least privilege / scope-limited.** Reduce what the break-glass session can do to what
  recovery actually needs. Minimizing the account's surface (no mailbox, no extra data paths) reduces phishing and exfiltration exposure — the HEx analogue is scoping the session to diagnostic/repair, not full normal operation.
- **Unpredictable identifier.** Avoid predictable names like "breakglass" or "emergencyadmin"; use a neutral identifier known only to the owner.
- **Loud by design.** Every use is a high-severity, append-only audit event and (where
  configured) an alert. A break-glass sign-in should be treated as a high-severity event; without alerting and a response runbook you may not notice a compromise until it is too late.

## Operational runbook (where to look, what to do)

### Where to store the credential

The break-glass secret and its TOTP seed (or FIDO2 key) must be retrievable **when the
stack is down** — including when your password manager might be down. Practical options,
ideally combined:

- **Offline/physical:** printed and sealed in a physical safe (the TOTP seed as text or
  QR, the passphrase separately). This survives a total homelab outage.
- **Independent of the lab:** if using a password manager, use one that does **not** depend
  on the homelab being up (the "your password manager is also down" failure mode is real —
  don't make
  your only copy live inside the thing you're recovering).
- **Cross-stored factors:** store the passphrase and the second-factor seed in separate
  places so one leak isn't full compromise.

### When and how to use it

1. **Confirm it's warranted.** Verify Authentik/OIDC is actually down (not HEx itself, not
   a network blip you can fix faster another way). Break-glass is for "normal admin access
   can't be used," used only for genuine emergency scenarios, and restricted to only the times it is absolutely necessary.
2. **Access via the constrained path** (LAN / local-only), authenticate with the secret +
   offline MFA.
3. **Do the minimum.** Diagnose and repair; don't use the break-glass session as a general
   admin console.
4. **Rotate after use.** Treat every use as potential exposure: rotate the passphrase (and
   re-issue the TOTP seed if appropriate) once normal access is restored.
5. **Review the audit/alert trail** to confirm the only break-glass use was yours.

### Keep it from rotting (the part everyone skips)

- **Test on a cadence** (e.g. quarterly): actually exercise the break-glass path in a safe
  way and confirm the credential, the offline MFA, the condition-gate, and the alerting all
  still work. If you don't test it, you don't have an emergency control — you have an assumption.
- **Guard against drift.** Emergency access can drift out of compliance as credentials expire, policies change, or accounts get disabled by inactive-user cleanup. Exempt the break-glass account from any "disable inactive users" logic HEx might add, and re-verify after changes to the auth/health-check code.
- **Keep the runbook current** and make sure the steps above are written down where you can
  find them during an outage — the emergency process should be documented, current, and known to whoever might need to perform it.

## Standards mapping

This aligns with general emergency-access and privileged-access practice: NIST SP 800-53
account-management and least-privilege controls (AC-2, AC-6), contingency planning (CP),
and audit (AU); and the identity-provider emergency-access guidance referenced above. HEx
implements the self-hosted equivalent of each control.

## References

- Microsoft Learn — Manage emergency access admin accounts (the canonical public runbook):
  https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access
- NIST SP 800-53 (AC-2, AC-6, CP, AU control families).
