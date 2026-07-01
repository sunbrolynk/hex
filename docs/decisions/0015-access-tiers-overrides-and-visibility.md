# 0015 — Access model: categories, tiers, per-service overrides, and three-tier visibility

- Status: **Accepted** (design-first; the two acceptance questions below are resolved inline)
- Date: 2026-06-30 (accepted 2026-07-01)
- Relates to: ADR 0002 (provider contract / four modes), 0001 (Authentik as SoT), 0014 (rich
  dashboard). Enables the invite-grant selection, dashboard visibility, and the request-more flow —
  which all share this one model.

## Context

Three surfaces need the same permission model: what an **invite grants**, what a user **sees on the
dashboard**, and what a user can **request**. If each invents its own shape they will fight. The
maintainer's requirements:

- **Selectable lists everywhere, never free text** — a user cannot be expected to know or spell a
  service's name to request it; the owner picks grants from what exists.
- **Access "levels," Authentik-styled** — since Authentik is the source of truth (ADR 0001), a level
  maps to Authentik's own mechanics for SSO-fronted services, and the owner can seed levels from
  their **existing Authentik groups**.
- **Per-service overrides that bypass the level** — both *additive* ("also give this user X") and
  *subtractive* ("everyone in this tier gets these, but not this user").
- **Zero attack surface** through the request and grant mechanisms.

The Authentik mechanics below were **verified live** against 2026.5.3 during a spike (see the
`[[access-visibility-model]]` note), not assumed.

## Decision

Four **orthogonal** concepts (do not conflate them):

### 1. Categories — organizational labels
Owner-curated labels grouping services (media, gaming, docs, home & family, music, photos, tv,
movies, productivity, …): a pick-from-suggested **plus create-your-own** list; a service can belong
to several. Purely for **organizing/displaying** and for **bulk selection**. Provider-agnostic; carry
no permission by themselves. **Resolved (Q2): HEx ships a default suggested category set** (Media,
Gaming, Docs, Home & Family, Music, Photos, Productivity, …) that is **fully owner-editable**
(rename / add / remove) — owners start organized, not on a blank slate.

### 2. Tiers — permission bundles
Owner-defined named bundles (e.g. "Family", "Guest") that map a set of services → **each service's
grant**, expressed in that service's own terms. A user is assigned a tier (per invite). A tier may be
composed **from a category**, from an **independent tier-grouping seeded by the owner's Authentik
groups**, or **per-service**.

**Resolved (Q1): a tier is a HEx bundle that *expands*, not a single Authentik group.** It expands to
per-service grants — for `sso_group` that means membership in the relevant service/level groups, for
`api_local`/`external_invite` the app-appropriate grant. So one tier can span many services and modes
(which a single Authentik group cannot). Owners may still *seed* a tier's SSO memberships from
existing Authentik groups, but the tier itself is a HEx concept layered over Authentik.

A "level" is not universal — it **resolves per `integration_mode`**:

| Mode | What a "level/grant" is |
|---|---|
| `sso_group` | Authentik **group membership** (nested: a service parent group with level child groups) |
| `api_local` (e.g. Jellyfin) | a bundle of the app's own API permissions (libraries, policy flags) — Jellyfin has **no** native tiers/SSO |
| `external_invite` (e.g. Plex) | which resources you **share** (libraries) |
| `manual` | owner-authored instructions |

HEx stores the structured `Grant` (the frozen contract, ADR 0002); the provider applies it. HEx never
invents permissions — it drives Authentik / the app API with a least-privilege service account (#3).

### 3. Overrides — per-(user, service), on top of a tier
- **Additive**: grant a specific service/level the tier wouldn't include.
- **Subtractive**: deny a specific service the tier *does* include.
Owner-authored only (`require_owner`), audited (#7), never self-grantable.

### 4. Visibility — three states per (user/invite, service)
- **Granted** — access by default → the invite's `default_grants`.
- **Visible / requestable** — not granted, but the user **may know it exists and request it** → the
  invite's `requestable`; drives the selectable request list.
- **Hidden** — the owner does **not** want them to know it exists → the default for everything else;
  **never leaked** in any response a user can reach (not requestable, not enumerable).

Visibility is its own axis, distinct from grants — a service can be granted, visible-but-not-granted,
or hidden.

### Authentik mechanics for `sso_group` (verified live)
- A service is an Authentik **application** gated by a `PolicyBinding(group → app)`; only members
  pass. The app's `policy_engine_mode` composes bindings.
- **Tiers via group nesting**: level groups are **children** of a service parent group; the app binds
  the **parent**, so a member of any level child transitively passes (`all_groups()` resolves the
  hierarchy). Granting a level = add the user to that level group.
- **Subtractive deny**: set the app's `policy_engine_mode = all` and add a **negated per-user**
  `PolicyBinding` — it denies even a group member. (Under `any` mode a deny is ignored, so `all` +
  single-parent-grant + negated-user-denies is the pattern.)
- **Seed from existing groups**: `GET /core/groups` lists the owner's groups + hierarchy to map onto
  service tiers.
HEx creates/manages this via the Authentik API (or shipped blueprints), preserving SoT.

### The invite is the composition point
An invite assigns a **tier (+ overrides)** → resolved to structured `default_grants`; a
**visible/requestable set** → `requestable`; everything else is **hidden**. Every selection is
validated against the provider registry at the boundary (unknown provider/tier → `422`, never
stored). The **dashboard** renders granted tiles (from the ledger) and may surface the visible set as
"request these"; the **request flow** shows only the visible set.

### Security model (the "no attack surface" requirement)
By construction, not by hope:
1. **No free-text identifiers** — the server hands out every selectable list; the client never names
   a service by a string it typed.
2. **Invite-scoped visibility** — a user's visible/request set is derived server-side from their
   **session identity**, never client-supplied (no IDOR); **hidden services never appear** in any
   user-reachable response.
3. **Re-validate at every hop** — a requested `(service, tier)` is checked against *that user's*
   permitted set at **submit** and again at **owner approval**; tampering to request a higher tier or
   an unlisted/hidden service is rejected.
4. **Owner-only authoring** — tiers, categories, overrides, and grants are owner-set
   (`require_owner`), each a privileged audited action (#7); a user can never self-grant or escalate.
5. **Registry + contract validation** — every provider id / tier / grant resolves against the
   registry and the provider's schema.
6. **Capability/enumeration resistance** on invite + request tokens (per non-negotiable #5); the
   6-2d signed-nonce binding stands.

## Consequences
- New **HEx-side** entities layer over the frozen provider contract: categories, tiers, overrides,
  and per-invite visibility (granted/visible/hidden). The `Grant` object stays the contract's, so
  Phase-4 providers plug in unchanged.
- The **invite schema evolves**: `default_grants` stays the structured `provider → grant` map (6-3
  provisioning untouched); `requestable` becomes a richer, registry-validated set; a hidden default.
- The **dashboard** (6-4) reads visibility + the ledger; the **request flow** (6-5) is built directly
  on this model.
- For `sso_group`, HEx manages a **group hierarchy per service** and per-user deny bindings via the
  Authentik API — the provisioner SA needs the corresponding group/policy-binding permissions
  (tracked when that provider lands).

## Rejected alternatives
- **Free-text service names** — typo/injection-prone; users can't be expected to know names.
- **`any`-mode multi-group grants** — cannot express a per-user deny (verified); nesting + `all`
  mode + negated user bindings is required.
- **Binding on a guessable/opaque id** — already rejected in 6-2d (sequential id → capability
  downgrade); selections validate against the registry, secrets stay separate.
- **Owner-authored raw grant blobs everywhere** — reintroduces a hostile-input surface; owner selects
  from provider-offered options, curated-first (mirrors ADR 0014).

## Deferred / verify at Phase 4
- Per-provider grant specifics for `api_local` (Jellyfin libraries/flags) and `external_invite`
  (Plex share API + the plex.tv account-link onboarding) — verified against live APIs when those
  providers are built.
- **Config-driven provider templates** ("adding a service is mostly config") — its own future ADR
  (see `[[provider-catalog-and-roadmap]]`).
- Concrete storage (HEx tables for categories/tiers/overrides/visibility) — the first implementation
  slice now that this model is accepted.

## Resolved acceptance decisions (2026-07-01)
1. **Tier ↔ Authentik group** — a tier is a **HEx bundle that expands** to per-service grants (SSO
   memberships included), not a single Authentik group; one tier spans many services/modes. Owners
   may seed a tier's SSO memberships from existing Authentik groups.
2. **Category source** — HEx ships a **default suggested category list**, fully owner-editable.
