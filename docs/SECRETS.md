# Secrets Management

HEx holds the keys to the lab. Secret handling is not a feature, it is a precondition for
the app being allowed to run at all.

## Principles

1. **No plaintext secrets at rest.** Provider credentials and any HEx-held secrets are
   **envelope-encrypted**: data encrypted with a data-encryption key (DEK), the DEK
   protected by a key-encryption key (KEK) that is **not stored next to the ciphertext**.
   Acceptable KEK sources: a KMS/transit engine, or a key injected from a secrets backend
   at runtime. Acceptable KEK sources include a KMS/transit engine, HashiCorp Vault, or a
   self-hosted secrets manager such as Vaultwarden/Bitwarden — any of which keeps the key
   off the box that holds the ciphertext.
2. **Refuse to boot insecure.** On startup HEx validates that every required secret is
   present and strong. Missing, empty, or known-weak/default value → **hard fail with a
   clear message**, never a silent fallback. No default admin account. No "changeme" that
   works.
3. **Generation instructions, not placeholders.** Example config never ships a usable or
   real-looking secret. Every secret field carries the **exact command to generate a
   strong value** and is left empty. This both prevents copy-paste-the-default and teaches
   the deployer to do it right. See the pattern below and `.env.example`.
4. **Secrets never leave the server boundary.** Not logged, not returned by the API, not
   embedded in client bundles, redacted in structured logs.
5. **Least privilege + rotation.** Each provider credential is a scoped service account,
   rotate-able without code changes or redeploys. HEx never holds an admin/god credential
   for any downstream system or for Authentik.

## The generation-instructions pattern

Instead of this anti-pattern:

```
# ❌ never do this
HEX_SECRET_KEY=your-secret-key-here
HEX_SECRET_KEY=changeme
DB_PASSWORD=password123
```

do this — empty value, exact generation command, and a stated consequence of leaving it
unset:

```
# Application signing key. REQUIRED. App refuses to start if unset or low-entropy.
# Generate (64-byte URL-safe, CSPRNG):
#   python -c "import secrets; print(secrets.token_urlsafe(64))"
HEX_SECRET_KEY=

# Key-encryption key for the secrets broker. REQUIRED.
# Generate (32 bytes, base64):
#   python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
# Store the source of this key OUTSIDE the database (KMS / Vaultwarden / injected env).
HEX_KEK=

# Postgres password. REQUIRED. Generate (32-byte URL-safe):
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
HEX_DB_PASSWORD=
```

## Boot-time secret validation (what "refuse to boot insecure" means concretely)

On startup, for every required secret, assert:

- present and non-empty,
- meets a minimum entropy/length bar appropriate to its role,
- is **not** on a denylist of known placeholder/default strings (`changeme`,
  `your-secret-key`, `password`, `admin`, the literal example values, etc.),
- decryptable / usable (e.g. the KEK actually decrypts the secrets store).

Any failure aborts startup with a specific, non-leaky error pointing the deployer at the
generation command. A misconfigured HEx must not run in a degraded-but-open state.

**First run is the one exception, and it is not a loophole.** On a genuine first run HEx
enters a secured **bootstrap mode** (guided setup; `docs/BOOTSTRAP.md`) rather than crashing
on not-yet-configured values — but bootstrap mode runs only the gated setup surface, not the
operational app. Boot-time validation above applies in full the moment setup completes.
Bundled Authentik secrets (its `SECRET_KEY`, bootstrap password hash, bootstrap token, and
datastore passwords) follow the same rules: generation instructions, no usable defaults,
never exposed to the browser.

## Provider credential lifecycle

- Stored envelope-encrypted; decrypted only inside the secrets broker, only when needed
  for a provider call, never held in plaintext longer than the call.
- Created as least-privilege service accounts on each downstream system. Document, per
  provider, the minimum scope required (this belongs in each provider's docs).
- `validate_config()` checks the credential works and — where the downstream API exposes
  it — that it is not over-scoped.
- Rotation: replacing a credential is a config operation, not a code change. Old
  credentials are revoked downstream as part of rotation.

## Break-glass credential

The optional break-glass owner login (disabled by default; see SECURITY_MODEL §13 and ADR
0008) follows the same rules with extra care because it is the one local credential:

- The password is stored as an **Argon2id hash** (tuned above the OWASP floor), never as
  plaintext; `.env.example` ships the generation command and leaves it empty.
- Its TOTP/MFA secret is a generated value (generation command provided), never a default.
- When `HEX_BREAKGLASS_ENABLED=false`, none of these are required and no local login path
  exists. When enabled, boot-time validation requires the hash (and, recommended, the TOTP
  secret) to be present and strong, exactly like other required secrets.

## What never goes in the repo

- No real secrets, tokens, keys, or `.env` files. `.gitignore` excludes them (see the
  shipped `.gitignore`).
- No real-looking example secrets anywhere — examples use empty fields + generation
  commands only.
- Pre-commit secret scanning (e.g. gitleaks) runs in CI and ideally as a local hook; a
  detected secret fails the build. See SUPPLY_CHAIN.
