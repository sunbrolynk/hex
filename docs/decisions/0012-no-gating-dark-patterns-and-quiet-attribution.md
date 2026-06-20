# 0012 — No gating, no dark patterns, and quiet attribution

- Status: **Accepted**
- Date: project inception

## Context

HEx and its Android app are free and open source and are meant to stay that way in spirit:
nothing withheld, nothing manipulative, and no project-run infrastructure that a self-hosted
tool has no business depending on. This ADR fixes that posture as a hard constraint so it
can't erode feature-by-feature.

## Decision

1. **Nothing is gated.** No feature, anywhere, is withheld or locked. Every build of every
   client is functionally identical for every user, however they obtained it. There is no
   tiering and no client-side gating logic to add.
2. **No dark patterns.** No nag prompts, no urgency, no guilt, no interstitials, no "upgrade"
   banners — none of it, in the web app or the app. The UI never pressures the user.
3. **Quiet About / Credits section (web + app).** Attribution and project links live in a
   single, tucked-away **About** section reached **near the GitHub link** — not on the main
   surface. It contains: the libraries and upstream apps that make HEx possible (proper OSS
   attribution), the project repo/site/GitHub links, and donation links. Hidden away, not in
   your face. Both clients implement exactly one such surface.
4. **No project-operated service of any kind.** HEx is fully self-hosted; there is **no
   phone-home and no maintainer-run backend** (licensing, telemetry, analytics, or anything
   else). A maintainer service would defeat the entire point of a self-hosted tool. The only
   network destination any client talks to is the user's own HEx instance.

## Consequences

- Claude Code must **never** add gating checks, "upgrade" prompts, nag dialogs,
  banners, analytics, or any project-operated backend. If a change would introduce any of
  these, **stop and flag it.**
- The web frontend and the Android app each implement exactly one quiet About/Credits surface
  per (3); dependency attribution is a maintained list (ideally generated from the lockfiles
  so it can't drift).
- Reinforces TRANSPARENCY (no phone-home) and the self-hosted, no-maintainer-service stance.

## Rejected alternatives

- **Gating / locked features / "upgrade" prompts / trial popups.** Rejected outright — dark
  patterns, against the project's values and its audience.
- **Maintainer-run licensing/telemetry/analytics service.** Rejected — defeats the purpose of
  a self-hosted tool and introduces phone-home.
- **Prominent placement of donation/links.** Rejected — offered quietly in About, never pushed.
