# Android Client — Foundation

The HEx Android app is a **separate, public, OSS repository** and a **client of the HEx
API** — nothing more. This doc is the foundation it will be seeded from; it captures the
security model, the recommended stack, distribution, and where in the
web dev cycle to start. (When the repo is spun up, it gets its own `CLAUDE.md`/docs derived
from this.)

## The one truth that governs everything

**The client is untrusted. Open-sourcing it changes nothing about real security — if the
architecture is right.** A determined user can already decompile any Android app; publishing
the source just removes the (worthless) speed bump of obfuscation. So the worry "people will
hack the official app because the code is visible" is answered not by hiding code but by
making sure **there is nothing in the client worth hacking**:

- **No secrets in the client. Ever.** No API keys, no client secrets, no signing material,
  no privileged tokens. (Same BFF rule as the web app — see ARCHITECTURE.)
- **The server is the only trust boundary.** All authorization and all sensitive operations
  are enforced server-side against the authenticated identity. A tampered client talking to
  the HEx API still hits a server that authorizes every request independently.
- **Assume the attacker has the source and a modified build.** Design so that buys them
  nothing they couldn't already do as an authenticated user.

This is the same Kerckhoffs principle the rest of HEx follows (`docs/TRANSPARENCY.md`):
security rests on server-side enforcement and secret keys, never on unreadable client code.

## Distribution

The app is open source and **functionally identical for everyone, however it is installed.**
There is no tiering and nothing gated — so there is nothing in the
client to "unlock" or bypass.

- **Sideload (GitHub).** Anyone can build/install the app from source. This is a first-class,
  fully supported path, not a second-class one.
- **Official Google Play build.** The same app, distributed through Play for convenience and
  auto-updates.
- **Beta (Play closed testing).** Interested users **email to register**; the maintainer adds
  their Google account to a **closed testing** track. This track also satisfies Google's
  production-access gate for new personal developer accounts (created after Nov 13, 2023):
  a **minimum of 12 opted-in testers** (Google reduced this from 20 on Dec 11, 2024)
  actively engaging for **14 consecutive days**. 12 is a floor, **not a cap** — invite as
  many interested testers as you like (closed tracks scale well beyond that; the *internal*
  track caps at 100, closed tracks can be larger via email lists / Google Groups).
  Organization accounts are exempt from the requirement.

No client-side gating logic of any kind. No in-app checks, no DRM, no
project-operated backend (see ADR 0012 and `docs/TRANSPARENCY.md`). The app talks only to the
user's own HEx instance.

## Play Integrity — available signal, never a gate

The **Play Integrity API** (Google's replacement for the deprecated SafetyNet) lets a backend
verify, via a signed token, that a request comes from a genuine, untampered app binary on a
genuine device, with the strict pattern **client is the messenger, the server is the judge**
(the client fetches an integrity token with a server-issued nonce; the server verifies it;
never decide on-device).

For HEx it is, at most, an optional **server-side anti-abuse signal** — and it is **never a
gate**:

- A **sideloaded / self-built app legitimately will not pass app-integrity** (it isn't the
  Play-signed binary). Since sideload is a fully supported path, Integrity must **never
  block** the app or degrade its function.
- It is verified server-side or not at all — never used to make on-device decisions.
- For the **self-hosted HEx backend** it is of limited use (it's the owner's own server), so
  don't build the app to require it against the HEx API.

## Recommended stack (researched, current)

Native is recommended for an Android-first, security-forward app (tightest access to the
platform security APIs and the cleanest integrity story).

- **Language/UI:** **Kotlin + Jetpack Compose.** (Flutter is the alternative and reuses prior
  Flutter experience, but native maximizes access to Android security primitives.)
- **Auth:** HEx is the identity plane (via Authentik OIDC). The app is a **public OAuth2
  client** — it holds **no client secret** — using **Authorization Code flow + PKCE** via
  **AppAuth-Android** (the OpenID Foundation SDK, which follows RFC 8252 *OAuth 2.0 for Native
  Apps*: Custom Tabs for the auth request, never a WebView, PKCE for public clients). Note:
  Android's **Credential Manager is the wrong tool here** — it's for passkeys/passwords and
  federated Google sign-in, not generic OIDC against a self-hosted IdP. The redirect uses an
  app link / custom scheme; PKCE binds the code to this app to resist interception. (The web
  app uses a different model — a backend-for-frontend confidential client; see ARCHITECTURE.)
- **Token storage (current best practice; EncryptedSharedPreferences is deprecated):**
  **Jetpack DataStore for persistence + Google Tink for AEAD encryption + Android Keystore
  for hardware-backed key protection.** DataStore alone is not encrypted — encrypt values
  with Tink, protect keys in the Keystore. Clear tokens on logout.
- **Transport:** TLS 1.2+ only, no cleartext (Android Network Security Config). **Certificate
  pinning caveat:** HEx is self-hosted — the app connects to the *user's own* HEx instance at
  a user-supplied URL with the owner's own cert, so you cannot pin to a cert you don't
  control. Rely on TLS + OIDC token validation + (optionally) letting the user trust their
  own CA, rather than classic domain pinning.
- **App lock:** optional biometric / device-credential lock (AndroidX Biometric) before the
  app reveals data.
- **Obfuscation:** R8/ProGuard for size/hygiene only — **it is not a security control** for
  an OSS app and must never be relied on as one. (No secret is ever "protected" by it because
  there are no secrets in the client.)
- **Local data:** store the minimum; encrypt at rest (above); nothing sensitive in logs.

## Opening the user's other installed apps (Plex, ABS, Jellyfin, …)

When a user taps a link to an integrated app, the HEx app should hand off to **that app if
it's installed** (e.g. open Plex in the Plex app), and only fall back to a browser otherwise.
Researched, current (Android docs, 2026):

- **Primary pattern — let Android route, prefer non-browser.** Fire an `ACTION_VIEW` intent
  for the URL with **`FLAG_ACTIVITY_REQUIRE_NON_BROWSER`**. If only a browser could handle it,
  Android throws `ActivityNotFoundException`; catch it and open the URL in a **Custom Tab**
  (in-app browser). This needs no package queries and is the cleanest "app if possible, else
  browser" behavior. Whether the target app opens depends on *its* registered deep/app links.
- **Package visibility (Android 11+/API 30).** To detect or directly launch *specific* known
  apps, declare a **minimal `<queries>`** block in the manifest listing exactly those app
  packages (or the intent signatures) HEx integrates — Android otherwise hides other installed
  apps for privacy. Declare only what's needed.
- **Never use `QUERY_ALL_PACKAGES`.** It's a Google Play policy-restricted permission and
  unnecessary here; the minimal `<queries>` approach is the correct, privacy-respecting one.
- **Confirm package names / URL schemes per app** before relying on them, and treat the
  integrated-app list as **data, not assumptions** — there are many third-party clients, so
  the *official* package must be verified in Play. Commonly (verify before relying):
  Plex `com.plexapp.android`, Jellyfin `org.jellyfin.mobile`, Audiobookshelf
  `com.audiobookshelf.app`. Some integrated services are **web-only** (e.g. Seerr and the
  *arr apps have no first-party Android app) — for those, there is no app to open and the
  handoff is always a Custom Tab; only services with a real first-party app get the app /
  Play-Store path.
- **If the target app isn't installed, offer to install it.** When detection (via the
  declared `<queries>`) shows the app is absent, route the user to that app's **Play Store
  page** instead of a generic web page: launch `market://details?id=<package>` (the Play
  Store app), falling back to `https://play.google.com/store/apps/details?id=<package>` if the
  Play Store app isn't present. So the chain is: **installed app → its Play Store page →
  web/Custom Tab.**
- **HEx's own links** (e.g. an invite or a deep link back into the HEx app) use **verified
  Android App Links** (`autoVerify="true"` + a hosted `assetlinks.json`) so they open the HEx
  app directly without the chooser prompt — but note the self-hosted caveat: App Link
  verification is tied to a domain, and each user's HEx lives at their own domain, so HEx's
  own deep-linking has to account for user-supplied hosts (custom scheme + in-app routing as
  the portable fallback).

## What the app actually is, architecturally

A thin BFF client of the HEx API: it authenticates the user via OIDC, renders their
dashboard, lets them submit/track access requests, and manages their profile — all by calling
the same HEx API the web frontend uses. It holds no provider credentials and makes no direct
calls to providers (identical rule to the web client; see ARCHITECTURE "Clients hold
nothing").

It also includes one **required, quiet About/Credits screen** (ADR 0012), reached from near
the GitHub link: the libraries and upstream apps that make HEx possible (attribution), plus
the repo/site/GitHub and donation links. Tucked away, never pushed.

## Where in the web dev cycle to start

The Android app chases the HEx API, so it must not start against a moving target.

1. **During web v1:** keep the API client-agnostic (it already is — BFF), and **document and
   freeze the user-facing API contract** (OpenAPI) for the endpoints mobile needs: OIDC
   login, dashboard payload, access-request submit/status, profile/settings, notifications.
2. **After web v1 works end-to-end and that contract is frozen:** spin the separate public
   Android repo, seed it from this doc, and build **auth + read-only dashboard first** as a
   vertical slice (same checkpoint discipline as `docs/WORKFLOW.md`), then access-requests,
   then polish.
3. **Late, pre-release:** Play setup — store listing, the closed beta track, and Play
   Integrity wiring only if a server-side anti-abuse signal is ever warranted.

**Sequence: web first → freeze the API contract → Android as a fast-follow.** Don't
parallelize early; a moving contract would thrash the mobile build.

## Non-negotiables for the Android repo (carried from HEx)

- No secrets in the client; the server enforces all authorization.
- Same security/transparency posture: open, no phone-home beyond the user's configured HEx
  instance, and **no maintainer-operated service of any kind** (it would defeat a self-hosted
  tool — ADR 0012).
- Same rigor: strict testing, signed releases, supply-chain hygiene (adapted to Android —
  Play App Signing, reproducible builds where feasible).
- **No gating, no dark patterns (ADR 0012).** Nothing is gated; the app is fully OSS and
  identical for everyone, however installed. **Never** add nag prompts, banners, analytics, or
  any project-operated backend. Attribution and links live only in a quiet **About/Credits**
  screen reached near the GitHub link: the libraries and upstream apps that make HEx possible,
  the repo/site/GitHub links, and donation links — tucked away, never pushed.
