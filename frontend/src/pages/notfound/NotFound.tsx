// Generic 404 for unknown routes — and for the break-glass page when reached off its listener, so
// neither is distinguishable from a page that simply doesn't exist. This is NOT a security control
// (the break-glass boundary is the server-side LAN listener); it just avoids a special-looking tell.

export function NotFound() {
  return (
    <main>
      <h1>404</h1>
      <p>This page could not be found.</p>
    </main>
  )
}
