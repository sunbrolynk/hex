#!/usr/bin/env bash
#
# Generate deploy/.env from .env.example with freshly generated secrets.
# MAINTAINER-run (it writes secrets to disk). Contains generation logic only —
# never any secret values — and prints no secret to the terminal.
#
# Output: deploy/.env (gitignored). The compose stack reads it for ${VAR}
# substitution and `env_file`. Local non-docker dev does not need it.
set -euo pipefail

cd "$(dirname "$0")/.."  # repo root
OUT="deploy/.env"

[ -f .env.example ] || { echo "error: .env.example not found" >&2; exit 1; }
[ -f "$OUT" ] && { echo "error: $OUT already exists — move it aside first" >&2; exit 1; }

python3 - "$OUT" <<'PY'
import base64, pathlib, re, secrets, sys

out = pathlib.Path(sys.argv[1])
lines = pathlib.Path(".env.example").read_text().splitlines(keepends=True)

urlsafe = lambda n: secrets.token_urlsafe(n)
b64 = lambda n: base64.b64encode(secrets.token_bytes(n)).decode()

# Fill these REQUIRED empty secret fields. (HEX_SETUP_TOKEN is intentionally left
# blank so HEx generates-and-logs it on first run, per .env.example.)
gen = {
    "HEX_SECRET_KEY": lambda: urlsafe(64),
    "HEX_KEK": lambda: b64(32),
    "HEX_AUDIT_KEY": lambda: urlsafe(48),
    "HEX_DB_PASSWORD": lambda: urlsafe(32),
    "HEX_PROXY_SHARED_SECRET": lambda: urlsafe(48),
    "AUTHENTIK_SECRET_KEY": lambda: urlsafe(60),
    "AUTHENTIK_PG_PASSWORD": lambda: urlsafe(32),
    "AUTHENTIK_REDIS_PASSWORD": lambda: urlsafe(32),
    "AUTHENTIK_BOOTSTRAP_TOKEN": lambda: urlsafe(48),
}
filled = []
for line in lines:
    m = re.match(r"^([A-Z0-9_]+)=\s*$", line.rstrip("\n"))
    if m and m.group(1) in gen:
        filled.append(f"{m.group(1)}={gen[m.group(1)]()}\n")
    else:
        filled.append(line)
text = "".join(filled)

# Compose-coherent, non-secret settings (override the example defaults).
extra = {
    "HEX_AUTHENTIK_MODE": "bundled",
    "COMPOSE_PROFILES": "bundled-authentik",
    "HEX_DB_HOST": "hex-db",
    "HEX_PUBLIC_BASE_URL": "http://localhost:8000",
    "AUTHENTIK_BASE_URL": "http://authentik-server:9000",
}
for k, v in extra.items():
    pat = re.compile(rf"^{k}=.*$", re.M)
    repl = f"{k}={v}"  # callable replacement: never interpret backslashes/group refs in v
    text = pat.sub(lambda _m: repl, text) if pat.search(text) else f"{text}{repl}\n"

out.write_text(text)
PY

chmod 600 "$OUT"
echo "wrote $OUT (chmod 600; gitignored)."
echo
echo "Still required before bundled bring-up (need the Authentik image — see NOTES.md):"
echo "  - AUTHENTIK_BOOTSTRAP_PASSWORD_HASH  (docker compose run --rm authentik-server hash_password '<passphrase>')"
echo "  - AUTHENTIK_BOOTSTRAP_EMAIL          (your admin email)"
echo "OIDC client id/secret + AUTHENTIK_API_TOKEN are wired during first-run bootstrap."
