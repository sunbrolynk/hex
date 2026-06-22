import { startLogin } from '../../api/auth'

/** Shown when no session exists: hand off to Authentik for login (pure OIDC). */
export function LoginGate() {
  return (
    <section>
      <h1>Sign in to HEx</h1>
      <p>HEx uses Authentik for login.</p>
      <button type="button" onClick={() => startLogin()}>
        Log in with Authentik
      </button>
    </section>
  )
}
