# Security Model (implementation-level)

This is the concrete, build-it-this-way companion to THREAT_MODEL. Targets **OWASP ASVS
5.0**, Level 3 on the identity/access/secrets/audit core and Level 2 elsewhere. Where exact
parameters are given, they are current as of the dated research behind these docs — treat
the *floor* as a floor and tune up for an identity service.

---

## 1. Authentication: HEx is a relying party, not an IdP

- HEx authenticates its own users via **Authentik over OIDC**. Validate ID/access tokens
  against **Authentik's JWKS** (signature, `iss`, `aud`, `exp`, `nbf`, nonce where
  applicable). Do not accept unsigned or `alg=none` tokens. Cache JWKS with rotation.
- HEx derives the user's role/identity **only** from the validated token + HEx's own
  authorization records — **never** from a client-supplied field.
- Any HEx-local credential (e.g. a break-glass owner login, if one exists at all) is
  hashed with Argon2id (see §3). Prefer *no* local password path; lean on Authentik.

## 2. The forward-auth header trap (read this twice)

If HEx sits behind a reverse proxy / Authentik outpost that injects identity headers
(`X-authentik-username`, `X-Forwarded-User`, `Remote-User`, …), **those headers are only
trustworthy if the request provably transited the proxy.** If the HEx container is
reachable directly on the network, an attacker sends the same headers and impersonates
anyone. This is the most likely catastrophic misconfiguration.

Required mitigations (defense in depth — do several, not one):

1. **Validate the assertion yourself.** Prefer validating an OIDC token against Authentik
   JWKS over trusting any proxy-injected header. If you must consume forward-auth headers,
   pair them with a verifiable secret.
2. **Authenticated channel between proxy and app.** mTLS, or a shared secret header that
   the app checks on every request and that an external attacker cannot know. Reject any
   request lacking it.
3. **Network isolation.** Bind HEx only to the internal/proxy network; never expose the
   app port directly. The proxy is the only ingress.
4. **Independent authz regardless.** Even behind the proxy, every request is authorized by
   HEx on its own. The proxy is not the authorization decision.

## 3. Password / credential hashing (when HEx hashes anything)

- Algorithm: **Argon2id** (RFC 9106), via `argon2-cffi`.
- OWASP floor: **m = 19456 KiB (19 MiB), t = 2, p = 1.** Alternative floor: m = 47104
  (46 MiB), t = 1, p = 1. These are *minimums*; since HEx is an identity-adjacent service,
  tune higher (e.g. 64–128 MiB, t = 3) subject to your hardware's latency budget, and
  document the chosen parameters.
- Unique per-credential salt (argon2-cffi handles this). Consider a **pepper** stored
  separately from the database (not alongside the hash) for defense if the DB leaks.
- Re-hash on login when parameters are upgraded.
- Never use fast hashes (SHA-256/MD5) for credentials.

## 4. Tokens and sessions

- **Web app uses the backend-for-frontend (BFF) model:** the HEx backend is a *confidential*
  OIDC client, does the Authorization Code exchange server-side, and the browser receives only
  a `Secure` `HttpOnly` `SameSite` session cookie — **no OIDC/access tokens are exposed to the
  browser.** This is the concrete form of "clients hold nothing."
- **Android uses a *public* client + PKCE** (AppAuth); it holds tokens in hardware-backed
  encrypted storage (DataStore + Tink + Keystore), never in plaintext. See `docs/ANDROID.md`.
- Short-lived access tokens; refresh with rotation and server-side revocation.
- Cookies are `Secure`, `HttpOnly`, `SameSite=Lax`/`Strict` as appropriate; CSRF protection
  for any cookie-authenticated state-changing route.
- Treat self-contained tokens per ASVS 5.0's dedicated chapter: validate every claim,
  bound lifetimes, no sensitive data in the payload.
- Server-side revocation for logout and offboarding — a revoked user's tokens stop working
  immediately, not at expiry.

## 5. Authorization

- **Server-side on every request.** No endpoint trusts client-supplied role/identity.
- **Owner/user boundary is absolute.** Owner-only routes (provider config, approvals,
  global settings) check the role from the validated identity every time.
- **Object-level authz.** A user can only read/act on their own ledger entries, requests,
  and widget data. Write authorization tests that prove user A cannot touch user B's
  objects, and that a user cannot self-grant a non-requestable service.
- **Requestable-set enforcement.** What a user may request is owner policy, enforced
  server-side; the client UI is a convenience, not the gate.

## 6. The invite link is a capability

- **Single-use: hard cap of 1 acceptance.** After one successful acceptance the token is
  permanently dead (atomic check-and-burn to avoid race-based double acceptance).
- **Entropy ≥ 128 bits**, generated with a CSPRNG (`secrets.token_urlsafe`), never a
  predictable/sequential id.
- **Short TTL** and **owner-revocable** before acceptance.
- **Rate-limited** acceptance endpoint (per IP and global), with invite-attempt caps.
- **Enumeration-resistant:** invalid, expired, and already-used tokens return an
  indistinguishable generic response with uniform timing.
- The invite encodes its grant set server-side; the client cannot alter which services or
  tiers the invite confers.

## 7. Secrets handling

Full detail in SECRETS.md. The load-bearing rules:

- **No plaintext secrets at rest.** Provider credentials are envelope-encrypted; the
  data-encryption key is not stored next to the ciphertext (KMS/transit, or a key sourced
  from a secrets backend — e.g. a KMS, HashiCorp Vault, or a self-hosted
  Vaultwarden/Bitwarden instance).
- **Refuse to boot insecure.** Missing or weak required secrets → hard fail at startup. No
  default admin, no "changeme" that works. **Exception, not loophole:** a genuine *first
  run* enters a secured **bootstrap mode** (guided setup; see `docs/BOOTSTRAP.md`), which is
  not the same as running the operational app with weak/missing secrets. The setup surface
  is itself gated (see §13.5). Once setup completes, full boot validation applies.
- **Generation instructions, not placeholders.** Every secret field in `.env.example`
  ships with the exact command to generate a strong value and no usable default.
- Secrets never logged, never returned by the API, redacted in structured logs.
- Per-provider least-privilege service accounts; rotate-able without redeploying.

## 8. Fail-secure provisioning

- Uncertain provider result → `FAILED`, no access granted. Never optimistic success.
- Deprovision is idempotent and aggressive; partial failures are isolated, retried, and
  surfaced, never swallowed.
- Provider calls are bounded: timeouts, capped concurrency, circuit breakers — a hostile
  or slow provider cannot stall or DoS HEx.

## 9. Audit log

- **Append-only and tamper-evident** (e.g. hash-chained entries so any edit/deletion is
  detectable). Stored such that the normal app write path cannot rewrite history.
- Records every privileged action: provision, deprovision, approve/deny, owner config
  change, login, token issuance/revocation — with actor, action, target, result, timestamp.
- Reconciliation findings (drift, unmanaged access) are audited as security events.
- No secrets or full PII dumped into audit entries — reference by id.

## 10. Input handling and API hardening

- All input validated with Pydantic v2 models; reject unknown fields on security-relevant
  payloads.
- Parameterized queries only (SQLAlchemy) — no string-built SQL.
- **Provider responses are untrusted input** — parse defensively; a compromised provider
  cannot corrupt HEx state or cross user boundaries.
- Safe error envelopes; internal detail to server logs only.
- Security headers on responses (CSP, HSTS, `X-Content-Type-Options`, frame-ancestors).
  ASVS 5.0 has a dedicated web-frontend-security chapter — follow it for the React app.

## 11. Crypto hygiene

- TLS everywhere (terminated at the proxy; internal hop authenticated per §2).
- CSPRNG (`secrets`) for all tokens/ids/salts; never `random`.
- ASVS 5.0 folds in post-quantum *considerations* — not required now, but prefer
  algorithm-agile interfaces so primitives can be swapped without redesign.

## 12. Multi-tenant-of-one caveat

Even though a homelab has one owner, model the owner/user separation rigorously. The whole
point of HEx is that untrusted-ish users (friends, family) get scoped access. Treat every
non-owner as a potential adversary in the authorization model.

## 13. Break-glass owner access (availability exception)

Normal login is pure Authentik OIDC (ADR 0001). Break-glass is the **one** local credential
that exists, solely so the owner is not locked out when Authentik/OIDC is unreachable and
needs to get in to diagnose and repair. It is the single highest-value local target, so it
is built to be safe *by constraint*:

- **Disabled by default.** It does not exist until the owner explicitly provisions it
  (config-gated; see `.env.example`). A fresh install has no local login.
- **Single owner account.** Not a general local-user system. Never issued to normal users.
- **Condition-gated.** Accepted **only** when the break-glass condition holds — primarily a
  failing health check against Authentik/OIDC — and/or via an explicitly **local-only**
  path. If HEx can reach a healthy Authentik, the break-glass path is closed. It is not a
  parallel everyday login.
- **Network-constrained where feasible.** Prefer binding the path to the LAN /
  non-internet-exposed surface so it is unreachable from the public internet.
- **Strongly authenticated.** Argon2id (tuned above the OWASP floor, per §3) for the secret;
  **TOTP MFA strongly recommended/enforced** when enabled (WebAuthn/FIDO2 is the stronger,
  phishing-resistant option). **The second factor must be offline-verifiable** — validated
  locally by HEx, never via Authentik, email, SMS, push, or anything internet-dependent.
  The recovery path must not depend on the thing that might be broken.
- **Brute-force resistant.** Aggressive rate limiting and lockout on repeated failure.
- **Loudly audited.** Every attempt — success or failure — is a **high-severity,
  append-only audit event**, and an alert where the owner has configured alerting.
  Break-glass use is never quiet.
- **Optionally scope-limited** to the diagnostic/repair surface needed to recover the
  system, rather than full normal operation.
- **Revocable/rotatable** without redeploy; disabling it removes the path entirely.

Required tests (per TESTING): disabled-by-default; rejected when the condition isn't met;
lockout enforced; audit event emitted on every use; MFA enforced when configured.

Operational guidance — credential storage (retrievable when the stack is down),
when/how to use it, rotation-after-use, and the periodic test cadence — is in
`docs/BREAK_GLASS.md`.

## 13.5 First-run bootstrap surface

The first-run setup wizard is a high-value attack window: whoever reaches it first could try
to claim ownership or read setup material. It is treated like the invite and break-glass
surfaces (full flow in `docs/BOOTSTRAP.md`):

- **Completion-bound + single-use.** Bootstrap mode exists only until an owner is
  established, then closes permanently.
- **Out-of-band setup token.** A one-time setup token printed to the **container logs** on
  first start is required to begin setup, so only someone with host/log access can complete
  first run.
- **Bind narrowly.** Prefer loopback/LAN exposure for the setup surface until setup
  completes; never the public internet by default.
- **Never expose Authentik's bootstrap token or any Authentik secret to the browser.** They
  stay server-side and are rotated to a scoped service-account token at the end of bootstrap.
- **Audited + fail-secure.** First run, ownership claim, and the hardening/rotation steps are
  high-severity audit events; if Authentik isn't healthy or the integration can't be
  verified, HEx stays in bootstrap mode rather than falling through into a half-open app.

## 14. Transparency / no security through obscurity

The security model is public on purpose (`docs/TRANSPARENCY.md`). Assume the attacker has
read every line of this document and the source. No control may depend on code being
unreadable; security depends only on secret **keys** (Kerckhoffs). HEx also makes no
outbound connections except to owner-configured systems and never exfiltrates user data —
this is an architectural invariant, tested for, and enforced in review.

---

## ASVS 5.0 conformance tracking

Maintain a checklist per relevant chapter (authentication, session management,
access control, validation/sanitization, cryptography, self-contained tokens,
secure communication, web frontend security, configuration). Mark each requirement
Not-started / In-progress / Met, with the target level (L3 core, L2 elsewhere). Update it
as modules land; a requirement is "Met" only when a test proves it.
