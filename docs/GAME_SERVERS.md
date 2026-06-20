# Game Servers

How HEx onboards users onto the owner's game servers: **grant access, then show them how to
connect.** This doc covers how game-server access is actually controlled and how it maps onto
the provider contract (`docs/PROVIDER_CONTRACT.md`). **Proposed design** — it feeds the
provider contract and is frozen alongside it; verify each game/panel against its live docs
before building a provider (per CLAUDE.md "when unsure about an external system").

## The key insight: a game server is a Plex-shaped problem

A player connects with **their own account** — a Mojang/Minecraft profile, a Steam account —
that HEx does **not** own and cannot create or delete. Granting access means **adding that
player's existing game identity to the server's allowlist**; offboarding means **removing it.**
That is exactly the asymmetry the two-axis model exists for (ADR 0002):

- **`identity_owner = external`** — the game account is the user's, on a platform HEx doesn't
  control. Deprovision **revokes the allowlist entry; it never deletes the account** (same as
  Plex). Status = "is this identity still on the allowlist?"
- **No fifth integration mode.** Game servers collapse into the existing modes:
  - **`api_local`** when the allowlist is automatable — RCON, a management-panel API, or a
    scriptable config reload. HEx calls out to add/remove the identity.
  - **`manual`** when there is no API — HEx renders owner-authored steps and the owner adds the
    identity by hand; HEx tracks state but performs no automation.

Approval (request-more) stays the workflow layer above, as for every provider.

## How game-server access actually works (researched landscape, June 2026)

| Mechanism | Examples | Grant / revoke | HEx mode |
|---|---|---|---|
| **Whitelist by name/UUID over RCON** | Minecraft (Java): `whitelist add/remove <name>`; name→UUID auto-resolved via Mojang | RCON command, then `whitelist reload` | `api_local` |
| **Allowlist by platform ID in a config file** | Steam games — Rust, ARK, Valheim, Space Engineers (SteamID64 lines) | edit allowlist/config, then reload or restart | `api_local` (if scriptable) or `manual` |
| **Management-panel API** | [Pterodactyl](https://pterodactyl.io/) / Pelican **subusers** | API grants *panel* access (console/restart/files) to one server | `api_local` — but see note below |
| **Platform group** | Steam group the server allowlists | add the user to the group | `manual` / `api_local` |
| **No API** | many games / bespoke servers | owner edits config by hand | `manual` |

> **Panel access ≠ play access.** A Pterodactyl/Pelican subuser can *manage* a server (a
> co-admin), which is different from being *allowed to play* on it (the in-game whitelist). HEx
> should model these as distinct grants — most user onboarding is play-access (the whitelist),
> not panel access.

## The structured grant

`perms` for a game-server provider is never a boolean. It carries:

- **The user's game identity** — the field depends on platform: a Minecraft username (resolved
  to a UUID) or a SteamID64, etc. **Collected during signup/onboarding**, validated server-side
  (resolve via the platform API where one exists — e.g. Mojang/PlayerDB for Minecraft — rather
  than trusting raw input).
- **Owner-set options** where the game supports them (which server/world, role/permission tier,
  panel-subuser permissions if granting management).

`grant_schema()` per game-server provider drives the wizard controls and the server-side
validation.

## Provision (grant)

1. Validate/resolve the user's game identity (e.g. Minecraft name → UUID).
2. Add it to the allowlist via the configured mechanism (RCON command / scripted config edit +
   reload / panel API call).
3. **Fail-secure:** any uncertain result → `FAILED`, nothing granted; surface to the owner.
   Idempotent — re-running must not double-add or error.
4. Return the **connection instructions** (below): `GRANTED` carrying the instructions, or
   `PENDING_MANUAL` for a manual server (carrying the steps for the owner and/or user).

## Connection instructions (owner-authored, per server)

This is the "tell the user how to get in" half, and it is **owner-authored data, never
hardcoded** — there are too many games. Per game server the owner configures a short template
HEx renders to the user once access is granted:

- address / port (or "join via the launcher"), edition/version, required mods or modpack (with
  links), rules, and any join steps specific to that server.

HEx surfaces these on the user's dashboard / signup wizard. Treat the integrated-game list as
**data, not assumptions** (the same discipline as the Android app's app-handoff list).

## Deprovision (revoke) — the part that must be reliable

- Remove the user's game identity from the allowlist (RCON `whitelist remove` / scripted config
  edit / panel API / owner instruction for `manual`).
- **Idempotent and aggressive.** Re-running on an already-removed entry succeeds. Revoke the
  **entry**, never attempt to delete the user's Mojang/Steam account (`identity_owner =
  external`). The ledger/audit record reads "allowlist entry revoked," not "account deleted."

## Status / reconciliation

`status()` checks whether the user's identity is still on the server's allowlist, so HEx
detects drift — someone added or removed out-of-band — and flags unmanaged access as a security
signal (`docs/PROVIDER_CONTRACT.md`).

## Security

- **Game-server credentials are per-provider, least-privilege, envelope-encrypted secrets**
  (RCON password, panel API key, or a constrained SSH/script path) — never exposed to the
  browser, decrypted only for the call (`docs/SECRETS.md`).
- **RCON is dangerous on the wire:** it is effectively a remote console, often unauthenticated
  beyond a single password and unencrypted. Bind it to the internal network only; never expose
  it. Prefer a panel API or a narrowly-scoped helper over raw RCON where possible.
- **Provider responses are untrusted input** — parse defensively; a compromised or flaky game
  server must not corrupt HEx state or leak another user's identity.
- Validate user-supplied game IDs; resolve via the platform API instead of trusting input.

## Per-platform notes (verify before building each provider)

- **Minecraft (Java):** RCON `whitelist add/remove <name>` + `whitelist reload`; name→UUID via
  Mojang API; `whitelist.json` on disk. **Bedrock:** `allowlist.json`.
- **Steam games (Rust/ARK/Valheim/Space Engineers/…):** SteamID64 in a server allowlist/config
  file; reload or restart to apply; some support Steam-group allowlists. Often needs file access
  + restart → may be `manual` or a scripted helper.
- **Pterodactyl/Pelican:** subuser API = management access to a server (not play access); useful
  for granting a trusted co-admin scoped control. Account vs Application API keys differ.
- **No-API games:** `manual` mode with owner-authored steps.

Do **not** hardcode or guess a game's mechanism — confirm against that game/panel's current docs
first, and treat snippets here as shape, not copy-paste.

## Conformance (every game-server provider)

Same bar as any provider (`docs/TESTING.md`): `validate_config` fails closed on bad creds;
`provision` is idempotent and fail-secure; `deprovision` revokes the allowlist entry and never
attempts an (impossible) account deletion; `status`/`widget_data` never leak another user's
identity.

## Decisions (confirmed)

- **Timing: post-v1.** Game-server connectivity is **not in v1.** v1 first proves the lifecycle
  against the core apps/services; game servers are added during the **service-expansion phase
  after a working v1** (ROADMAP → Beyond v1). This doc captures the design now so the provider
  contract is shaped with it in mind.
- **Management vs play are separate grants.** "Manage the server" (e.g. a Pterodactyl/Pelican
  subuser — console/restart/files) and "allowed to play" (the in-game allowlist) are modeled as
  **distinct grants**; a user may hold one without the other. Never conflate them.

## Still to settle when the time comes

- The first game server(s) to support, and whether the first cut automates any (Minecraft via
  RCON is the cleanest) or ships **`manual`-only** and gains automation later.

## Sources

- Sonarr/Radarr have no native multi-user (context for why *arr is not a user-provisioned
  service): Sonarr issues [#1682](https://github.com/Sonarr/Sonarr/issues/1682),
  [#3242](https://github.com/Sonarr/Sonarr/issues/3242); Radarr
  [#7047](https://github.com/Radarr/Radarr/issues/7047).
- Minecraft whitelist via RCON + Mojang UUID resolution:
  [docker-minecraft-server docs](https://docker-minecraft-server.readthedocs.io/),
  [Minecraft Wiki: /whitelist](https://minecraft.fandom.com/wiki/Commands/whitelist).
- Game-server management panels + subusers/API:
  [Pterodactyl](https://pterodactyl.io/), [pydactyl API wrapper](https://github.com/iamkubi/pydactyl).
- Steam allowlist / SteamID64 patterns: vendor allowlist guides (Rust, ARK, Space Engineers).
