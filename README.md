<div align="center">

# HEx — The Homelab Experience

### Turn an invite into real, governed access across your entire homelab — and revoke it everywhere in one click.

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Status: early development](https://img.shields.io/badge/status-early%20development-orange.svg)](ROADMAP.md)
[![Self-hosted](https://img.shields.io/badge/self--hosted-%E2%9D%A4-d7263d.svg)](#)
[![Telemetry: none](https://img.shields.io/badge/telemetry-none-2ea043.svg)](docs/TRANSPARENCY.md)

</div>

---

HEx is the **front door to your self-hosted world**. Invite a friend or family member, and HEx
sets up their access across the services you choose, drops them on a dashboard that's *theirs*,
lets them request more access (with your approval), and — when the time comes — **cleanly removes
them from everything at once.**

The dashboard is the face. The **lifecycle orchestration is the product.**

```
   INVITE  →  ACCEPT  →  PROVISION  →  DASHBOARD  →  REQUEST MORE  →  OFFBOARD
  (you)      (capability   (across       (personal     (you approve)    (everywhere,
              link)         services)     to them)                       one action)
```

## Why HEx?

If you run a homelab for more than just yourself, you know the friction:

- **Onboarding** someone means setting up access across Jellyfin, Plex, Seerr, a game
  server, a shared wiki… one panel at a time — every app its own silo.
- Everyone ends up with **all-or-nothing** access, because fine-grained is too much manual work.
- And when someone should **lose** access? You're hunting through a dozen admin pages, hoping
  you didn't miss one — leaving a door open you forgot about.

HEx makes onboarding *one link*, access a *governed decision*, and **offboarding a single,
reliable action** — the part almost nobody else does well.

## What makes HEx different

🧩 **Every service is a "provider."** HEx models each app by *how* it grants access **and** *who
owns the user account* — the two questions that, kept separate, make correct offboarding actually
possible (revoke a Plex share or a game-server allowlist entry, delete a Jellyfin user, drop an
Authentik group). New services plug into one contract.

🔑 **Identity done right — Authentik, bundled *or* bring-your-own.** HEx never reinvents auth. It
ships and orchestrates [Authentik](https://goauthentik.io) so a single command brings everything
up and first run is a guided setup — *or*, if you already run Authentik, point HEx at your
existing instance. Your call.

🧹 **Offboarding is a first-class feature.** "Remove this person everywhere" is the hardest and
most valuable operation in shared self-hosting, and it's built into the core — not bolted on.

🛡️ **Security is the mission, not a checkbox.** HEx is the most privileged box in your lab, and
it's designed that way from commit one: least-privilege everywhere, fail-secure provisioning, an
append-only audit trail, capability-based invite links, and signed, provenance-attested releases.

🔍 **Open and quiet.** The code and the *entire* security model are public. HEx makes **zero**
outbound connections except to the systems you configure — no telemetry, no analytics, no
phone-home, no harvesting your data. Auditable like the *arr stack.

🎁 **Free, forever, for everyone.** Nothing is gated, locked, or upsold. No nag screens, no "pro"
tier, no project-run servers. Every build is identical for everyone, however you install it.

## Not another dashboard

The ecosystem already nails the pieces HEx deliberately *won't* rebuild — dashboards (Homepage,
Homarr, Dashy) and media-onboarding wizards (Wizarr). HEx's own dashboard is intentionally
minimal. The unclaimed ground is the **cohesive, generalized lifecycle** — onboard → request →
personalized experience → **offboard** — across *arbitrary* services, driven through your identity
provider.

## 🚧 Project status

**Early development — built in the open.** HEx isn't ready to run yet; we're laying the
foundation slice by slice, with every step reviewable.

➡️ **See the [Roadmap](ROADMAP.md)** for the plan and exactly where we are today.

⭐ **Star** and **watch** the repo to follow along as it comes together.

## Built on

[FastAPI](https://fastapi.tiangolo.com) · [React 19](https://react.dev) · PostgreSQL ·
[Authentik](https://goauthentik.io) · Docker — open standards, no lock-in.

## For the curious & contributors

HEx is documented in depth. Good starting points:

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — the system shape and the one decision
  everything hangs off.
- **[docs/PROVIDER_CONTRACT.md](docs/PROVIDER_CONTRACT.md)** — the spine: how any service plugs in.
- **[docs/LIFECYCLE.md](docs/LIFECYCLE.md)** — the full arc, end to end.
- **[docs/TRANSPARENCY.md](docs/TRANSPARENCY.md)** — our open / no-phone-home posture, in detail.
- **[docs/decisions/](docs/decisions/)** — the architectural decisions and *why* they were made.

Contributions and security reports are welcome even at this early stage — see
**[CONTRIBUTING.md](CONTRIBUTING.md)** and **[SECURITY.md](SECURITY.md)**.

## License

**[AGPL-3.0](LICENSE).** Strong copyleft that also covers running a modified version as a network
service — anyone who hosts a modified HEx must share their changes under the same license. This
keeps HEx, and everything built on it, open.

## Credits

HEx stands on the shoulders of [Authentik](https://goauthentik.io) and the broader self-hosted and
*arr communities. Full dependency and upstream attribution lives in the app's About page.

<div align="center">
<sub>Built for people who host things for the people they care about.</sub>
</div>
