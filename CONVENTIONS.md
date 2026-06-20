# Conventions

Code style for HEx, uniform across the **entire** repo — backend and frontend. For the
directory layout, see `docs/FILE_ARCHITECTURE.md`.

## Docstrings & comments — terse by default, full where it earns it

The governing rule: **say the minimum that adds clarity, in one uniform style, and never
add noise.**

- **Three words if three words suffice.** Don't write multiple sentences where a short
  phrase does the job. Simple, obvious functions get a one-line docstring or none.
- **Never restate the name or the file path.** No `# src/api/foo_routes/router.py` header
  at the top of a file. No `"""BookService class."""` that just echoes the symbol name. No
  "This module contains the functions for…". If the docstring only repeats what the
  signature already says, delete it.
- **Comment the *why*, not the *what*.** Don't narrate obvious code (`# loop over items`).
  Comment non-obvious intent, tradeoffs, gotchas, and the reason a thing is done a
  surprising way.
- **No noise.** No decorative banner comments, no commented-out code, no redundant inline
  comments, no over-markup. A file should read clean.
- **Full docstrings where they earn it** — public API, non-obvious behavior, anything with
  non-trivial args or failure modes. When a docstring *is* warranted, it is **professional
  and complete**: a one-line summary, then `Args` / `Returns` / `Raises`, and an `Example`
  where it helps. Same structure every time.
- **One docstring style for the whole repo.** Python uses **Google-style**; TypeScript/React
  uses **TSDoc/JSDoc**. Pick the section style once and apply it everywhere — uniformity is
  the rule, not author preference.

The aim is that the documentation and docstrings are good enough that someone new to the
codebase (including the maintainer returning later) can understand a module without reading
its whole implementation — without being padded with length for its own sake.

### Python (Google-style)

Terse, when that's all that's needed:

```python
def slugify(value: str) -> str:
    """Normalize a string into a URL-safe slug."""
```

Full, when the behavior earns it:

```python
async def provision(self, user: User, grant: Grant) -> ProvisionResult:
    """Grant a user access to this provider.

    Idempotent. On any uncertain downstream result, returns ``FAILED`` rather than
    optimistically reporting success (fail-secure).

    Args:
        user: The HEx user being provisioned.
        grant: Structured, provider-specific grant validated against ``grant_schema``.

    Returns:
        The provisioning outcome, including an ``external_ref`` where applicable.

    Raises:
        ProviderConfigError: If the provider's credentials are missing or invalid.

    Example:
        >>> await jellyfin.provision(user, Grant(libraries=["movies"]))
        ProvisionResult(state=GRANTED, external_ref="jf-user-123")
    """
```

### TypeScript / React (TSDoc)

```ts
/** Format a byte count as a human-readable size. */
export function formatBytes(n: number): string { ... }
```

```ts
/**
 * Fetch a user's dashboard payload.
 *
 * @param userId - HEx user id; the caller must already be authorized for this user.
 * @returns The widgets the user is entitled to see.
 * @throws If the session is unauthenticated.
 */
```

## Naming (uniform)

- Route groups: `{resource}_routes/` containing `__init__.py` + `router.py`.
- Services: `{concern}_service.py` (flat); orchestration tasks: `{task}_handler.py` under
  `services/handlers/`.
- Pluggable providers: a `base.py` interface plus one file per implementation.
- Test files mirror source names: `test_{module}.py`; factories: `{model}_factory.py`
  exposing `{Model}Factory`.
- Python: `snake_case` modules/functions, `PascalCase` classes. TS/React: `PascalCase`
  components/files, `camelCase` functions/vars, `useXxx` hooks.

## File size — one responsibility AND kept small, from the outset

**"No god files" means two things here: one clear responsibility per file, AND the file
kept genuinely small.** Because HEx is greenfield and built end-to-end with an agent (no
copy-paste accretion), we hold this line from commit one instead of retrofitting it later.

- **One responsibility per file.** A file does one thing. The moment it starts doing two
  unrelated things, split it — by concern.
- **Aim small.** Soft target: keep files **under ~300 lines**. Crossing **~400 lines** is a
  split trigger — stop and split unless the file is an irreducibly single unit (e.g. a
  generated schema or a model registry).
- **Extract reused sections into shared modules** the moment logic is duplicated, rather
  than letting two files both grow it. Shared helpers live in their own small modules and
  are imported.
- **Split sub-concerns granularly.** Prefer several small, obvious modules over one large
  clever one. A large router becomes per-action handlers; a large service becomes a small
  service plus focused helpers.
- **Don't pad-split a cohesive unit** just to hit a number, and **don't combine** unrelated
  concerns to save a file. The target serves readability and reviewability, not bean-counting.
- **Security-critical modules are stricter.** Auth, authz, provisioning, secrets, invite
  handling, break-glass, and audit aim **under ~200 lines** and are split aggressively so
  each unit is small, individually reviewable, and testable to the 95% bar.

## Linting / formatting

Backend: **ruff** (zero warnings) + formatter; types via mypy. Frontend: eslint
(`eslint.config.js`) + the project formatter; TS strict. These run in CI and in the
PostToolUse hook (see `docs/WORKFLOW.md`); zero warnings is a merge gate.
