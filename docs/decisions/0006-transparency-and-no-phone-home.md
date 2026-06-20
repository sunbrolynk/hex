# 0006 — Transparency, open source, and no phone-home

- Status: **Accepted**
- Date: project inception

## Context

HEx holds the keys to an entire homelab. The self-hosted community has recently been burned
by telemetry added quietly, license rug-pulls, and apps exfiltrating data. A tool with
HEx's privilege level cannot ask for trust; it has to be auditable. The owner wants HEx to
be open like the *arr stack, with the explicit goal that anyone can verify HEx is not
stealing information or phoning home — while still allowing surfaces to be hardened where
there is a concrete, documented security reason.

## Decision

1. **HEx is open and auditable.** The codebase and the full security model (architecture,
   threat model, controls) are public on purpose.
2. **Kerckhoffs's principle governs:** security rests on the secrecy of **keys**, never on
   the secrecy of code or design. **No security through obscurity, anywhere.**
3. **No telemetry, no phone-home, by default.** A default build makes zero outbound
   connections except to owner-configured systems (Authentik, enabled providers). No
   analytics, no usage reporting, no licensing/activation callbacks. All user data, ledger,
   and audit content stay local and are never transmitted by HEx.
4. **Every outbound destination is documented**, and not exfiltrating user data is an
   architectural invariant that is tested for and modeled in the threat model.
5. **Exactly two bounded exceptions to full publicity**, both stated in the docs and
   neither involving hidden code: secrets/keys (never in the repo), and *pre-fix
   vulnerability details* held only for coordinated-disclosure timing.
6. **Reducing transparency requires a written justification** (an ADR). The default is
   open; "closing up" may harden defaults or narrow what an endpoint reveals, but never
   means hiding code or the security model.

## Consequences

- `docs/TRANSPARENCY.md` is the canonical statement; README and SECURITY.md summarize it.
- Verifiable releases (signing + provenance + SBOM) become part of the transparency story,
  not just supply-chain hygiene: deployers can prove the running image matches public
  source.
- Any future opt-in diagnostics must be off by default, fully documented in payload, free
  of secrets/PII, and to an owner-approved destination.
- Community auditing and responsible disclosure (SECURITY.md, CONTRIBUTING.md) are the
  intended mechanism for "warn us if there's a hole."
