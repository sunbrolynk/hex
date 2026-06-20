# 0002 — Provider contract and four integration modes

- Status: **Accepted**
- Date: project inception

## Context

HEx integrates with heterogeneous services whose enrollment stories differ fundamentally.
A naive single-axis model ("how do we provision?") produces a specific, dangerous bug:
modeling Plex as "API-provisioned" leads offboarding code to assume an account deletion
that is impossible (the identity lives on plex.tv), so offboarding silently fails.

## Decision

Every service is a **provider** implementing one interface, declaring **two orthogonal
axes**:

- `integration_mode` ∈ { `sso_group`, `api_local`, `external_invite`, `manual` } — how HEx
  grants/revokes.
- `identity_owner` ∈ { `authentik`, `provider`, `external`, `none` } — who owns the user
  record, which governs whether deprovision is symmetric (delete) or asymmetric (revoke a
  share only).

`perms` is always a **structured, per-provider grant object** validated against the
provider's `grant_schema()` — never a boolean. A **provisioning ledger** records every
`(user, provider)` grant, state, external reference, and history, and is the backbone of
offboarding, status, audit, and recovery.

There are **four** integration modes and **no fifth**. Approval-gated access is a
workflow layer above all four modes, not a mode itself. LDAP-backed apps fold into
`sso_group`/`authentik`. Quota-rich provisioning is handled by the structured grant, not a
new mode. (There is one provider *contract* — the shared interface — and four *modes*.)

## Consequences

- The Plex-class offboarding bug is structurally prevented: `external_invite` +
  `identity_owner = external` forces revoke-the-share semantics.
- The contract must be **designed and frozen before feature code**; the lifecycle engine,
  dashboard, approval workflow, and security model all depend on it.
- Every provider ships with conformance tests (idempotency, fail-secure provisioning,
  correct deprovision semantics per `identity_owner`, no cross-user data leakage).
- Adding a service later is "write a provider against a proven contract," not a
  re-architecture.
