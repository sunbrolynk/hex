/**
 * Quiet About / Credits surface (ADR 0012): attribution + project links only, reached from
 * the footer, never surfaced prominently and never nagging. Dependency attribution is a
 * placeholder here and is generated from the lockfiles in a later slice.
 */
export function AboutPage() {
  return (
    <section>
      <h1>About HEx</h1>
      <p>HEx — a self-hosted access-orchestration and experience layer for a homelab.</p>

      <h2>Built with</h2>
      <p>React, FastAPI, Authentik, and the open-source projects HEx builds on.</p>

      <h2>Project</h2>
      <ul>
        <li>
          <a href="https://github.com/sunbrolynk/hex">GitHub</a>
        </li>
        <li>
          <a href="/api-docs">API docs</a>
        </li>
      </ul>
    </section>
  )
}
