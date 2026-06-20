# 0011 — Android client: separate OSS repo, untrusted client, server-enforced

- Status: **Accepted**
- Date: project inception (foundation; build deferred — see timing)

## Context

HEx will have a native Android app, distributed as a **separate public OSS repo**, installable
by sideload and via an official Google Play build. The maintainer is new to Android and is
concerned that publishing the client source lets users "hack" the official app. The real
question is the security model for an open, untrusted client.

## Decision

1. **The client is untrusted; the server is the only trust boundary.** No secrets in the
   client (no keys, no client secret, no privileged tokens). All authorization is enforced
   server-side against the authenticated identity. Open-sourcing the client changes nothing
   about real security (Kerckhoffs). Obfuscation is hygiene, never a control.
2. **Separate, public, OSS repo**, seeded from `docs/ANDROID.md`, carrying HEx's posture
   (open, no phone-home beyond the user's HEx instance, strict testing, signed releases).
3. **Stack:** native **Kotlin + Jetpack Compose**; **OAuth2 Authorization Code + PKCE** as a
   public client (no client secret) against Authentik/HEx; token storage via **DataStore +
   Tink + Android Keystore** (EncryptedSharedPreferences is deprecated); TLS-only.
4. **No gating; the app is identical for everyone.** No client-side gating logic of any kind,
   no DRM, no project-operated backend. Sideload and the official Play build are functionally
   identical. (See ADR 0012 and `docs/TRANSPARENCY.md`.)
5. **Play Integrity is a signal, not a gate.** Verified server-side, never on-device, and
   never a hard block — sideloaded/OSS builds legitimately won't pass app-integrity, which is
   a fully supported path. At most an optional server-side anti-abuse signal.
6. **App-to-app handoff.** Tapping a link to an integrated app opens that app if installed,
   else routes to its Play Store page, else a Custom Tab — via minimal manifest `<queries>`
   and `FLAG_ACTIVITY_REQUIRE_NON_BROWSER` (never `QUERY_ALL_PACKAGES`). See `docs/ANDROID.md`.
7. **Timing:** build **after** web v1 works and the user-facing API contract is frozen. The
   app is a BFF client and must not chase a moving API. Sequence: web → freeze API → Android
   fast-follow; auth + read-only dashboard slice first.

## Consequences

- "People will hack the visible code" is largely a non-threat: there is nothing valuable in
  the client (no secrets, server enforces everything), and sideload is a supported path.
- A documented, frozen API contract (OpenAPI) becomes a web-v1 deliverable so the Android
  build has a stable target.
- The Android repo will get its own `CLAUDE.md`/docs derived from `docs/ANDROID.md` when it
  is created.

## Rejected alternatives

- **Client-side gating / feature-locks in the app.** Rejected: trivially patched in an OSS
  client; false security.
- **Rely on obfuscation or hidden secrets.** Rejected: not a control; risks leaking material.
- **Hard-block non-Play (sideloaded) installs via Play Integrity.** Rejected: it would break
  the intended free/OSS sideload path.
- **Start Android in parallel with early web work.** Rejected: a moving API contract would
  thrash the mobile build.
