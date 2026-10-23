# Phase 6.5 — Session inactivity timeout

The default session idle deadline is 60 minutes, with a warning in the final 5
minutes. The frontend receives policy and remaining duration from the backend;
it does not carry a separate 60-minute configuration.

## Configuration

Set `SESSION_IDLE_TIMEOUT_MINUTES=60` and `IDLE_WARNING_MINUTES=5` in the private
root `.env`, then recreate the backend with Docker Compose. Both settings must be
positive integers and warning must be less than timeout. Defaults are wired in
Compose and documented in `.env.example`.

## Schema and APIs

Migration `0007_session_idle` adds required timezone-aware `last_activity_at` to
`user_sessions`. Existing `revoked_at`, `expires_at` and rotation-specific
`last_used_at` are reused. Old sessions are initialized from `created_at`, not a
background-refresh timestamp; some existing users must sign in again on upgrade.
No users, sessions or application data are deleted by the migration.

`services/session_idle.py` defines the shared backend policy and serialization.
Protected bearer-session validation and refresh reject sessions when server UTC
time reaches the idle deadline, persisting revocation. Refresh rotation does not
change activity. An expired session cannot be extended or resurrected.

- `GET /api/auth/session`: current session ID, server time, effective deadline,
  timeout seconds and warning seconds; does not extend activity.
- `POST /api/auth/activity`: authenticated, origin-checked, rate-limited to 120
  requests/minute; updates only the authenticated session using server time.
  Client-supplied timestamps/other session IDs have no effect. Conditional SQL
  prevents updates to expired/revoked sessions and prevents timestamp regression
  during concurrent requests.
- Login/refresh responses include the same session policy metadata.
- Logout optionally accepts an expected session ID, so a delayed old-tab logout
  cannot revoke a newly signed-in session using the browser's new refresh cookie.
- Unauthorized refresh/activity responses clear the HttpOnly refresh cookie.

## Frontend behavior

`auth/IdleSession.tsx`, mounted once inside AuthProvider, listens for trusted
pointerdown, keydown, wheel and touchstart events. Activity reporting is limited
to once per 15 seconds and never emitted by polling, rendering, token rotation,
visibility changes or the idle countdown. Focus/visibility checks compare absolute
deadlines and read backend session status; they do not extend the session.

The warning is an accessible dialog with keyboard focus trapping/restoration,
countdown, Stay Logged In, and Logout Now. Ordinary interactions do not dismiss
an already displayed warning. Stay Logged In closes it only after backend
confirmation; network failure leaves an actionable error. The editor publishes its
dirty state so unfinished annotations receive a specific warning. No draft is
automatically submitted or written to browser storage.

At expiry, client auth is cleared immediately and Login displays
`Your session expired due to inactivity.` Logout is attempted with a network
timeout; server enforcement remains effective offline. Stale refresh responses
cannot restore a client session that has already been cleared.

BroadcastChannel plus a storage-event fallback synchronize confirmed activity and
logout for matching session IDs. Web Locks and a non-sensitive per-session ended
marker suppress duplicate automatic logout requests. Activity deadlines and
logout markers may be stored; access/refresh tokens are never placed in
localStorage. Different browser sessions/user identities do not share activity.

## Changed files

- Backend: `models/auth.py`, `auth_dependencies.py`, `routers/auth.py`, `main.py`,
  `services/session_idle.py`, Alembic `0007_session_idle.py`.
- Frontend: `auth/IdleSession.tsx`, `auth/AuthProvider.tsx`, `services/api.ts`,
  `pages/AuthPages.tsx`, `pages/EditorPage.tsx`.
- Configuration: `.env.example`, `docker-compose.yml`.
- Tests: `tests/test_session_idle.py`, migration assertion, frontend idle tests,
  auth-provider mock; `scripts/verify_idle_postgres.py` for isolated PostgreSQL.

## Validation

- Full backend regression: **118 passed**, including authentication, workspace
  RBAC, annotation/AI workflows, export, email verification and migration.
- Full frontend regression: **67 passed**; TypeScript/Vite build passed.
- Final idle/auth/API client rerun: **16 passed**, production build passed.
- Isolated PostgreSQL test: migration, four concurrent activity updates, refresh
  without idle extension, four expired activity requests and persisted revocation
  all passed.
- Boundary tests exercise 55/60 minutes using fake clocks, sleep/wake, warning
  confirmation/failure, unsaved work, reload duration, and remote-tab events.
- Backend tests verify exact expiry, revocation, origin checks, no cross-user
  session update, and ignoring a future client timestamp.

Private pre-upgrade backup:
`storage/.backups/annotation-before-phase65-20261023.dump`.

After deployment, the application database is at `0007_session_idle`. Annotation
checksum matched before/after; all 17 annotations, 125 images, 2 projects, 3 users
and 20 sessions were retained. All 20 sessions have the new activity timestamp.
Backend health returned ok and frontend returned HTTP 200. The isolated test
database was removed after verification; the application database was retained.

## Limits and operations

Human interaction cannot be proven by an activity endpoint; this is session
management, not bot detection. The server uses the time it receives the report.
The 15-second reporting throttle can conservatively expire a session up to one
reporting interval before the last unreported interaction would suggest. Long
running AI jobs do not keep a session alive without human interaction.

There is no draft autosave/recovery system: saved database annotations remain
safe, but unsaved in-memory work is discarded when a session ends. Users should
choose Stay Logged In and save before expiry. Browser suspension can prevent the
warning from being displayed until wake; backend expiry still applies.

Web Locks provide cross-tab serialization in supported browsers. Without Web
Locks or usable storage, duplicate idempotent logout requests are possible.
Rate limiting remains per backend process as in the existing authentication
implementation. Browser multi-tab behavior is covered by simulated event tests;
no claim is made of a real 60-minute browser soak test.
