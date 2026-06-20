# First-Run Bootstrap

The first time the stack comes up, HEx must **not** crash on everything that isn't
configured yet. Instead it detects first run, enters a secured **bootstrap mode**, finishes
wiring Authentik for the owner, hardens, and then moves into HEx owner setup. See ADR 0010.

## State machine

```
  FIRST RUN (unconfigured)
        │
        ▼
  BOOTSTRAP MODE  ── secured setup surface only; the full app is NOT running ──┐
        │                                                                       │
        │  1. Wait for Authentik to be healthy (it self-seeds from bootstrap    │
        │     env vars + the HEx blueprints on its first start).                │
        │  2. Using the Authentik bootstrap token, verify/finish HEx's          │
        │     integration: OIDC app + provider, scoped service account, groups  │
        │     (created by blueprint; confirm + fill any gaps via API).          │
        │  3. Show the owner the minimal Authentik details to confirm/supply    │
        │     (public URL/domain, confirm admin password set, prompt MFA).      │
        │  4. HARDEN: rotate off the bootstrap token to HEx's own scoped        │
        │     service-account token; recommend disabling the bootstrap admin    │
        │     and enrolling MFA.                                                 │
        ▼                                                                       │
  HEX OWNER SETUP  ── create the owner identity (via Authentik enrollment),     │
        │             optionally configure first providers ──────────────────── ┘
        ▼
  NORMAL OPERATION  ── full app; normal boot-time security validation applies.
```

Bootstrap mode is a **deliberate, minimal, secured** state — not an insecure running app and
not a crash. It exposes only the setup flow; the dashboard, invites, provisioning, and the
rest stay closed until setup completes.

## Why this design

- **Authentik is required and bundled** (ADR 0010), so HEx can drive its first-time
  configuration rather than asking the owner to hand-wire OIDC. HEx ships **blueprints** so
  most of Authentik's HEx-specific objects exist automatically on Authentik's first start;
  bootstrap mode just confirms and fills gaps. The blueprints create both OIDC
  registrations — a **confidential** provider/app for the web BFF and a **public**
  provider/app (PKCE) for Android — plus the scoped service account and HEx's groups
  (`authentik_providers_oauth2.oauth2provider`, `authentik_core.application`,
  `authentik_core.group`, `authentik_core.user` + token). Setting the bootstrap env vars also
  **skips Authentik's own `initial-setup` out-of-box flow**, so there is no competing setup
  wizard.
- **The bootstrap token is the bridge.** Authentik's `AUTHENTIK_BOOTSTRAP_TOKEN` is read only
  on first start and gives API access; HEx uses it to finish wiring, then **rotates to its
  own least-privilege service-account token** and stops using the bootstrap token.
- **It ends in a working system**, not a checklist — the whole point of guiding the owner.

## Security of the setup surface (this is a high-value attack window)

The first-run setup wizard is sensitive: whoever reaches it first could try to claim
ownership or read setup material. Treat it like the invite and break-glass surfaces.

- **Single-use, completion-bound.** Bootstrap mode exists only until setup completes; once an
  owner is established it is permanently closed. Claiming ownership is a one-time, guarded
  action.
- **Require a setup token the operator must retrieve out-of-band.** Print a one-time setup
  token to the **container logs** on first start and require it to begin setup, so only
  someone with host/log access can complete first run. (Same capability-token thinking as
  invites.)
- **Bind narrowly.** Prefer exposing the setup surface on **loopback/LAN only**, not the
  public internet, until setup completes.
- **Never expose Authentik's bootstrap token (or any Authentik secret) to the browser.** It
  lives server-side in HEx during bootstrap and is rotated out at the end.
- **Audit it.** First-run, ownership claim, and the hardening/rotation steps are
  high-severity append-only audit events (see SECURITY_MODEL §9).
- **Fail secure.** If Authentik isn't healthy or the integration can't be verified, stay in
  bootstrap mode and surface the problem — never fall through into a half-open app.

## Relationship to "refuse to boot insecure"

These are not in conflict (see SECRETS / SECURITY_MODEL):

- **Unconfigured first run** → secured **bootstrap mode** (guided setup). Not a crash.
- **Misconfigured / weak-secret *operational* state** → **refuse to boot**. Still a hard
  fail. Bootstrap mode is not a way to run the app insecurely; it's a way to *finish setup*
  securely before the app runs at all.

## Where this sits relative to the user lifecycle

System bootstrap and owner setup come **before** the user lifecycle arc
(`docs/LIFECYCLE.md`). Order: bundled stack up → first-run bootstrap → HEx owner setup →
*then* the owner can invite users and the invite→provision→…→offboard arc begins.

## Hardening hand-off (recommended to the owner at the end of bootstrap)

Mirror the identity-provider hardening practice: disable/retire the bootstrap admin in favor
of a proper superuser, delete the bootstrap token, and enroll MFA (ideally a phishing-
resistant method) on the owner identity. HEx surfaces these as the final bootstrap steps;
some it can do automatically, others it prompts for.
