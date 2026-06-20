# The Provider Contract

This is the spine of HEx. Every app HEx integrates with is a **provider** that implements
one interface — *the* provider contract. The lifecycle engine, the dashboard, the
access-request workflow, and the security model all plug into this interface. **Design and
freeze it before any feature code.**

## Vocabulary (use these terms precisely)

- **Provider** — the integration module for one app (the Jellyfin provider, the Plex
  provider). One file per app, all implementing the same interface.
- **The provider contract** — the single shared interface every provider implements
  (the methods + the two declared axes below). There is exactly one contract.
- **Integration mode** — one of **four** values a provider declares for *how* it
  provisions: `sso_group`, `api_local`, `external_invite`, `manual`. These are **modes**,
  not "contracts": there is one provider contract (the interface) and four modes.

The contract is built on a single insight that prevents a whole class of bugs:

> **How HEx provisions an app and what HEx is allowed to do when offboarding are two
> different questions.** Conflating them produces silent offboarding failures.

So every provider declares **two orthogonal axes**, not one.

---

## Axis 1 — `integration_mode`: how HEx grants/revokes access

| Mode | Meaning | HEx's action to grant | Example services |
|---|---|---|---|
| `sso_group` | App authenticates against Authentik (OIDC / forward-auth / LDAP) and authorizes by group/claim. | Add user to an Authentik group (via Authentik API, or let Authentik SCIM-push downstream). | *arr apps behind forward-auth, Grafana (OIDC), Mealie (OIDC), most modern apps |
| `api_local` | App owns its own user table and exposes a user-management API. | Call the app's API to create the user / set permissions. | Jellyfin, Seerr (Overseerr-compatible API) |
| `external_invite` | Identity lives on an external IdP HEx does not control; access = a share/membership the user claims with their own account. | Send an invite/share via API; user claims it externally. | **Plex** (plex.tv), Discord server invites |
| `manual` | No API and no SSO. HEx cannot automate it. | Render owner-authored step-by-step instructions in the wizard. | Niche apps, hardware portals, anything without an enrollment API |

## Axis 2 — `identity_owner`: who owns the user record (governs offboarding)

| Owner | Who holds the identity | Deprovision semantics | Status semantics |
|---|---|---|---|
| `authentik` | Authentik directory | Remove from group / deactivate in Authentik. Symmetric and complete. | "Is the user in the granting group?" |
| `provider` | The app's own DB | Delete/disable the user via the app API. Symmetric and complete. | "Does the local user exist / is it enabled?" |
| `external` | An IdP HEx does not control (plex.tv, Discord) | **Asymmetric: revoke the share/membership only. HEx CANNOT delete their account.** | "Is the external identity still linked/shared?" |
| `none` | No per-user downstream record (e.g. a wiki behind forward-auth with no user model) | Near-no-op: revoke the group; nothing to delete downstream. | Degenerate; usually just the group check. |

### Why two axes and not one

If Plex were modeled as `api_local` (because "it has an API"), the offboarding code would
assume a `delete_user` that does not exist — you do not own the plex.tv account, you only
revoke the library share. Offboarding would **silently fail** and leave access in place.
That is exactly the kind of bug that is unacceptable in a security tool. `external_invite`
+ `identity_owner = external` makes the asymmetry explicit and forces correct code.

### Realistic combinations

- `sso_group` + `authentik` — the clean path. Prefer pushing services into this bucket;
  it minimizes bespoke code and centralizes lifecycle in the IdP.
- `sso_group` + `none` — forward-auth app with no user model.
- `api_local` + `provider` — Jellyfin, Seerr.
- `external_invite` + `external` — Plex, Discord.
- `manual` + `provider` — owner provisions by hand following instructions; HEx tracks
  state but performs no automation.

> **There is deliberately no fifth mode.** Candidates that look like new modes collapse:
> LDAP-backed apps are `sso_group`/`authentik` (the directory is the user store);
> approval-gated access is a **workflow layer above all four modes**, not a mode itself;
> quota-rich provisioning is handled by the structured grant object, not a new mode.
> If you believe you have found a genuine fifth mode, that is a design escalation —
> raise it, do not invent a mode silently.

---

## The structured grant object

`perms` is **never a boolean.** "Has access" is insufficient; real services have tiers,
quotas, and scoped permissions. A grant is a structured, **per-provider** object whose
schema the provider defines and validates.

Examples (illustrative — verify against live APIs before implementing):

- Seerr: `{ "request_limit": 10, "auto_approve": false, "movie_quota_days": 7, "tv_quota_days": 7 }`
- Jellyfin: `{ "libraries": ["movies","tv"], "max_active_sessions": 2, "allow_downloads": true }`
- Plex: `{ "libraries": ["Movies","TV"], "allow_sync": true, "allow_channels": false }`
- An `sso_group` app: `{ "group": "media-users" }`

Each provider exposes `grant_schema()` so the owner UI can render the right controls and
the API can validate input server-side. **Never accept an unvalidated grant blob.**

---

## The provider interface

A provider implements this interface (names illustrative; finalize in code review).
All network-touching methods are async and must be defensively coded against timeouts,
partial failures, and hostile/malformed responses.

```
class Provider:
    # --- static declaration ---
    id: str                       # stable slug, e.g. "jellyfin"
    name: str                     # display name
    category: str                 # "media", "requests", "docs", ...
    integration_mode: IntegrationMode
    identity_owner: IdentityOwner
    capabilities: set[Capability] # which optional methods are meaningful

    def grant_schema(self) -> JSONSchema:
        """Schema for the structured grant object. Drives UI + server validation."""

    async def validate_config(self) -> ConfigStatus:
        """Verify credentials, connectivity, and least-privilege scope AT BOOT.
        A provider that cannot validate is disabled, not silently broken."""

    async def provision(self, user: User, grant: Grant) -> ProvisionResult:
        """Idempotent. Returns a state, an external_ref if applicable, and—for
        manual/external modes—the instructions or claim URL to show the user.
        On ANY uncertainty, return FAILED. Do not optimistically report success."""

    async def deprovision(self, user: User, entry: LedgerEntry) -> DeprovisionResult:
        """Idempotent and aggressive. For identity_owner=external this REVOKES THE
        SHARE, it does not delete the account. Re-running on an already-revoked grant
        must succeed, not error."""

    async def status(self, user: User, entry: LedgerEntry) -> DownstreamStatus:
        """Current real downstream state, for reconciliation/drift detection."""

    # --- optional, gated by capabilities ---
    async def widget_data(self, user: User) -> WidgetPayload | None:
        """Per-user dashboard data (e.g. Seerr request statuses). Must be scoped to
        THIS user only; never return another user's data."""

    def available_grants(self) -> list[GrantTemplate]:
        """What tiers/options the owner can offer for this provider."""
```

### `ProvisionResult` states

- `GRANTED` — access is live now.
- `PENDING_MANUAL` — user must complete owner-authored steps; carries the instructions.
- `PENDING_EXTERNAL_CLAIM` — invite/share sent; awaiting the user's external claim
  (e.g. Plex invite accepted). Carries the claim URL/reference.
- `FAILED` — could not provision. **This is the safe default for any uncertainty.**
- `PARTIAL` — multi-step grant where some steps succeeded; must record exactly what did,
  so deprovision/retry is precise.

---

## The provisioning ledger

The ledger is the backbone of offboarding, status, audit, and recovery. Without it,
"remove this user everywhere" is unanswerable.

For every `(user_id, provider_id)` HEx records:

- the **grant** that was applied (structured object),
- the current **state** (`GRANTED` / `PENDING_*` / `REVOKED` / `FAILED` / `PARTIAL`),
- the **external_ref** (downstream user id, share id, invite id) needed to act later,
- **timestamps** and a **state-transition history** (append-leaning event log),
- **last_reconciled_at** and last observed downstream status.

Design notes:

- Model it as an **append-leaning event log** (provisioning events) with a current-state
  projection, not a single mutable row you overwrite. This gives you a tamper-evident
  history and a clean audit story.
- The ledger plus Authentik is your **disaster-recovery source of truth**: if HEx's
  operational DB is lost or tampered, you can reconstruct who-has-what-where from the
  ledger and the IdP.
- The ledger feeds the **audit log** (see SECURITY_MODEL): every provision/deprovision
  is a privileged action and must be auditable independent of application state.

## Reconciliation loop

Periodically (and on demand) call `status()` for active ledger entries to detect **drift**:

- access that was revoked downstream out-of-band (someone removed the Jellyfin user
  manually) → ledger updated, owner optionally alerted,
- expired/declined external invites → state corrected,
- grants that exist downstream but not in the ledger → flagged as **unmanaged access**,
  which is a security signal, not noise.

Reconciliation is a security control, not a nicety: it is how HEx notices that reality and
its records have diverged.

## Contract-conformance tests

Every provider ships with a conformance test proving:

- `validate_config` fails closed on bad/expired credentials,
- `provision` is idempotent and returns `FAILED` (never optimistic success) when the
  downstream call is uncertain,
- `deprovision` is idempotent and, for `identity_owner=external`, revokes-the-share
  rather than attempting an impossible account delete,
- `widget_data`/`status` never leak another user's data.

A provider without passing conformance tests does not ship.
