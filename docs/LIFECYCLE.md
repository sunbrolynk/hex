# The User Lifecycle Arc

> Precedence: the **system bootstrap** and **owner setup** (`docs/BOOTSTRAP.md`) happen
> first, on first run. Only after an owner exists does the user lifecycle arc below begin.

The lifecycle arc is HEx's v1 spine and its differentiator. Wizarr-class tools nail the
media-onboarding slice; nobody cohesively does the whole arc — and especially not the
**offboarding** end — across arbitrary services. Build the arc depth-first across all four
provider integration modes, not breadth-first across many services.

```
  INVITE ──▶ ACCEPT/SIGNUP ──▶ PROVISION ──▶ DASHBOARD ──▶ REQUEST MORE ──▶ OFFBOARD
   (owner)     (capability)      (per the      (per-user)    (approval        (revoke
                                  contract)                   workflow)        everywhere)
```

## 1. Invite

The owner creates an invite that encodes: which default services/grants the new user gets,
which services they are *allowed to request* later, and an expiry. The invite link is a
**capability** (see SECURITY_MODEL):

- single-use — **hard cap of 1 acceptance**, then the token is dead,
- short TTL,
- ≥128 bits of entropy, unguessable,
- rate-limited and enumeration-resistant on the acceptance endpoint,
- revocable by the owner before acceptance.

## 2. Accept / signup wizard

The prospective user follows the link into a guided wizard. Because HEx delegates identity
to Authentik, "create your account" means **driving an Authentik enrollment flow**, not
HEx minting credentials. The wizard then walks the user through the default service set,
where each service's onboarding UX is determined by its `integration_mode`:

- `sso_group` → access is automatic once the Authentik group is assigned; nothing for the
  user to do but maybe a first SSO login.
- `api_local` → HEx creates the downstream account via API; wizard confirms it.
- `external_invite` → wizard shows the claim step (e.g. accept the Plex invite with your
  own Plex account) and tracks `PENDING_EXTERNAL_CLAIM` until claimed.
- `manual` → wizard renders the owner-authored instructions.

## 3. Provision

The lifecycle engine calls `provision(user, grant)` per selected provider, writes a ledger
entry per `(user, provider)`, and emits an audit event per privileged action. Rules:

- **Fail secure.** Any uncertain provider result is `FAILED`; the user does not get access
  on a maybe. Surface the failure to the owner for retry.
- **Record `PARTIAL` precisely.** Multi-step grants must record exactly what succeeded so
  retry and deprovision are exact.
- **Idempotent.** Re-running provisioning must not double-grant.

## 4. Dashboard

The user lands on a rich, personalized, configurable dashboard. Each provider may expose
`widget_data(user)` (e.g. Seerr request statuses) — strictly scoped to that user. Tiles
deep-link to the service's subdomain/subfolder as the owner has configured. The dashboard
reads the ledger to know what the user actually has, so a user configures only what they have
been granted. v1 ships curated widgets + drag/drop layout + theming (no user code/CSS yet);
the full GUI builder plus a power-user code/CSS mode is post-v1 — see ADR 0014.

### Seamless access (no second login) — a dashboard goal

**Goal: clicking a tile in HEx should drop the user straight into the service, already
signed in — no re-authentication where the integration mode allows it.** This is a first-class
UX goal of the dashboard, not an afterthought; how fully it is achievable is a pure function of
the provider's `integration_mode`:

- `sso_group` (OIDC / forward-auth behind Authentik) — **fully seamless, and largely free.**
  Because HEx and the service share Authentik as the IdP, a user who already has an Authentik
  session is logged in silently on click (OIDC SSO) or transparently allowed (forward-auth /
  proxy). Push as many services into this bucket as possible precisely for this reason.
- `api_local` (Jellyfin, Seerr) — **best-effort.** The app owns its own accounts, so true silent
  SSO is only possible if the app itself supports SSO/OIDC; otherwise the tile is a clean
  deep-link and the app may still prompt. Do not fake the app's login.
- `external_invite` (Plex) — **not possible by design.** The user authenticates with their own
  external account (plex.tv); HEx cannot and must not complete that login for them.
- `manual` — no automation; the tile is just a link.

> **Security boundary (non-negotiable #2):** "no second login" must always be achieved *through
> Authentik* (real SSO), never by HEx forging or injecting identity into the downstream app. HEx
> must never inject identity headers or synthesize credentials to bypass a real auth check — that
> would violate the never-trust-injected-identity rule. Seamless = a genuine Authentik SSO session
> carried through, not an auth bypass.

## 5. Request more access (the approval workflow layer)

A user can request a service the owner marked **requestable**. This is **not** a fifth
provider contract — it is a workflow layer that sits above all four:

```
  user requests ──▶ PENDING approval ──▶ owner approves/denies
                                              │
                                approve ──────┘──▶ dispatch to the provider's
                                                    integration_mode → provision()
```

Requests are themselves audited. Denials and approvals both produce audit events. The
owner controls, per service and per user/group, what is visible, what is auto-granted, and
what is requestable.

## 6. Offboard (the part nobody builds)

"Remove this user everywhere" is the hardest and most valuable operation, and it is a
pure function of the ledger. For each active ledger entry, the engine calls
`deprovision(user, entry)`:

- `identity_owner = authentik` → remove from group / deactivate in Authentik.
- `identity_owner = provider` → delete/disable the downstream account via API.
- `identity_owner = external` → **revoke the share/membership only. The external account
  is not yours to delete.** The ledger and audit log must reflect "share revoked," not
  "account deleted."
- `identity_owner = none` → revoke the group; nothing downstream to delete.

Offboarding rules:

- **Aggressive and idempotent.** Re-running offboarding on an already-revoked grant
  succeeds. Better to over-revoke than to leave a door open.
- **Partial-failure handling.** If one provider's revoke fails, the others still proceed;
  the failed one is flagged, retried, and surfaced — a single stuck provider must never
  block revoking access everywhere else.
- **Time-limited access** (invites/grants with an expiry) runs through the same path
  automatically when the clock runs out.
- Every revoke is audited.

## The ledger and reconciliation underpin steps 3–6

See PROVIDER_CONTRACT for the ledger shape. Two lifecycle-critical behaviors:

- **Reconciliation** periodically calls `status()` on active entries to detect drift:
  access removed downstream out-of-band, expired external invites, or — a security signal
  — downstream access that exists with no managing ledger entry (**unmanaged access**).
- **Recovery:** ledger + Authentik together let HEx reconstruct who-has-what-where if its
  operational DB is lost or tampered.

## v1 provider set (depth-first, one per integration mode)

Pick a minimal set that forces every mode to be real before the contract calcifies:

- `sso_group` — a multi-user app behind Authentik SSO (e.g. Grafana, a wiki, or Mealie).
- `api_local` — Jellyfin.
- `external_invite` — Plex.
- `manual` — any service with no enrollment API (owner-authored steps).

If you skip a mode in v1, you will discover its true shape only after the interface has
hardened around the modes you did build — which is exactly when it is most expensive to
change. All four, end to end, or it is not a v1.
