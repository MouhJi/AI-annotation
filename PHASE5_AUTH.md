# Phase 5: authentication and account management

## Architecture and compatibility

FastAPI/SQLAlchemy 2.0 now authenticates API requests with Argon2id passwords and HS256 JWT access tokens. React keeps access tokens only in module memory, restores login with an HttpOnly refresh cookie, and serializes refresh calls (including tabs using Web Locks). React Router protects project/editor/account routes. No tokens are written to localStorage or sessionStorage.

Existing integer primary keys, bounding-box pixel coordinates, polygon JSON, class order (class ID order in YOLO export), image storage paths and split assignments are preserved. New auth entities use UUIDs with timezone-aware timestamps. The SVG annotation editor remains in place.

New tables: `users`, `user_sessions`, `used_refresh_tokens`, `password_reset_tokens`, `email_verification_tokens`. `projects.owner_user_id` is nullable only to represent unclaimed legacy records. New projects always receive the authenticated owner.

## Start / upgrade on Windows

```powershell
cd "C:\Users\Admin\OneDrive\Tài liệu\ChatGPT\roboflow\annotation-platform"
docker compose up -d --build frontend backend
docker compose logs --tail=50 backend
```

The backend starts with `alembic upgrade head` before Uvicorn. Keep the existing PostgreSQL volume. Never use `docker compose down -v` for an upgrade. A backup is recommended before upgrading a database you rely on.

Migrations:

* `0001_legacy`: inspect and validate existing tables; create missing Phase 1–4 tables only on an empty/partial supported schema; add the known earlier geometry/split columns if needed. It does not drop/recreate existing legacy tables or blindly stamp the DB. Unexpected schemas stop the migration.
* `0002_auth`: create auth tables/indexes and add the nullable owner FK. PostgreSQL uses additive ALTER TABLE statements; SQLite's test fallback uses Alembic batch mode for its FK limitation. No ownership assignment or annotation rewriting occurs.

For direct local development install `backend/requirements.txt`, set `DATABASE_URL` and `STORAGE_PATH`, run `alembic upgrade head` from `backend`, then `uvicorn app.main:app --reload`. `create_all()` is used only to initialize isolated test fixtures, not at application startup or by the seed command.

## Legacy project ownership: explicit operator claim

Legacy projects are **preserved but not visible to any registered account** until claimed. Registration never assigns the old dataset to the first user. This is intentional access protection, not data loss.

1. Register the intended owner through `/register` and verify their email if verification is required.
2. Review the proposed mapping without changing anything:

```powershell
docker compose exec backend python -m app.claim_legacy --email owner@example.com
```

3. Only after the operator/user confirms the email and specific project IDs, apply the mapping, for example:

```powershell
docker compose exec backend python -m app.claim_legacy --email owner@example.com --project-ids 1 2 --apply --confirm-email owner@example.com
```

The script requires explicit IDs, refuses already-owned/missing projects, locks rows, and updates only `owner_user_id`. There is no public claim endpoint. Do not run the apply example without reviewing the real mapping. This implementation does not execute that ownership change on your behalf.

## Ownership policy

The central `require_resource_access` dependency checks project ownership for project, image, annotation, class and prediction IDs. Bulk image deletion checks the payload project before executing. Batch inference retains the existing same-project ID check. All project-scoped routes, including destructive actions, mapping, splits and exports, are protected. Collections are filtered to the current owner. A missing or inaccessible resource consistently returns 404. Anonymous access returns 401. Unclaimed projects are inaccessible to ordinary accounts.

`/storage` is no longer a public static directory. Image requests require a Bearer access token and owner check, and allow only project image paths. React downloads images as authenticated blobs and revokes their object URLs. Auth secrets and development emails under storage cannot be served by this endpoint.

Phase 6 can replace this central ownership dependency with workspace membership/RBAC and migrate the nullable owner relation. No roles or implicit admin privileges are granted in Phase 5.

## API

| Endpoint | Purpose |
|---|---|
| POST `/api/auth/register` | Normalize email, create account, send verification link |
| POST `/api/auth/login` | Verify credentials/status, create independent session, set refresh cookie |
| POST `/api/auth/refresh` | Atomically rotate opaque refresh token and issue access token |
| POST `/api/auth/logout` | Revoke cookie session and clear cookie |
| POST `/api/auth/logout-all` | Revoke all sessions immediately |
| GET `/api/auth/me` | Current public user fields |
| PATCH `/api/users/me` | Explicitly allow only full_name |
| POST `/api/auth/change-password` | Verify current password; invalidate all sessions and one-time tokens |
| POST `/api/auth/forgot-password` | Generic response and reset email if eligible |
| POST `/api/auth/reset-password` | Consume hashed single-use reset token, update password, revoke sessions |
| POST `/api/auth/verify-email` | Consume hashed single-use verification token |
| POST `/api/auth/resend-verification` | Generic response, rate-limited resend |
| GET `/api/auth/sessions` | Active sessions, timestamps, current indicator |
| DELETE `/api/auth/sessions/{uuid}` | Revoke own session only |

All POST/DELETE auth requests require an exact allowlisted `Origin`, or a matching Referer origin. This also prevents login/logout CSRF. Native API clients must send the configured Origin explicitly. Profile APIs and project APIs use Bearer headers. Health remains public at `/health`. API responses never include password or token hashes. Auth responses are `no-store`.

Access tokens require `sub`, `sid`, `exp`, `iat`, `iss`, `aud`, `jti`, `type=access`, a valid signature and an active database session. Revoking a session invalidates its existing access tokens immediately. Refresh tokens are random, stored only as SHA256 hashes (passwords separately use Argon2id), rotate atomically using row locks/CAS, and expire after 7 days by default. JWT access expires after 15 minutes by default. Spent refresh hashes identify replay at any generation and revoke that session family. Concurrent refresh replay fails closed: one request succeeds, another reusing the same token revokes that family. The frontend single-flight/Web Locks avoid legitimate duplicate rotations; clients without Web Locks should avoid simultaneous refresh from multiple tabs. Logout all/reset/password change revoke all families. Password change intentionally signs out the current session too.

## Frontend

Pages: `/login`, `/register`, `/forgot-password`, `/reset-password`, `/verify-email`, `/settings/profile`, `/settings/security`.

The top-right menu provides name/email, My Profile, Security Settings and Logout. Registration includes confirmation and visibility control; passwords accept 12–1024 characters without trimming or arbitrary composition rules. There is no fake Remember Me checkbox. Security settings show/revoke active sessions and change passwords. Restore/refresh uses one shared in-flight request, retries a failed API call once and stops on another 401. Redirect destinations are restricted to safe internal paths.

## Development email and production configuration

Copy `.env.example` to `.env` if customizing configuration. Development defaults to `EMAIL_BACKEND=file`: messages appear as private `storage/.emails/*.eml` files. Open the appropriate file locally and follow its verification/reset link. Tokens are in URL fragments, removed from browser history by the form, expire, and are single-use. They are not returned from public APIs or printed to server logs. Do not publish or commit the email directory. Set `EMAIL_VERIFICATION_REQUIRED=true` to require verification before login; default local development allows login while still offering verification.

Local HTTP uses `AUTH_COOKIE_SECURE=false`, `SameSite=Lax`, HttpOnly, and cookie path `/api/auth`, with no broad cookie domain. If JWT_SECRET_KEY is empty in development, a unique random persistent secret is generated in private `storage/.auth-secret`; no shared default secret exists.

Production must set:

* `APP_ENV=production`, an externally provisioned `JWT_SECRET_KEY` of at least 32 characters, issuer and audience.
* HTTPS, `AUTH_COOKIE_SECURE=true`, HTTPS `FRONTEND_URL`, exact HTTPS `CORS_ORIGINS` (never `*` with credentials).
* `EMAIL_BACKEND=smtp`, `SMTP_HOST`, `SMTP_PORT` (STARTTLS, default 587), `SMTP_FROM_EMAIL`, and credentials if required.
* `EMAIL_VERIFICATION_REQUIRED=true` if verified email is required by your policy.
* Secure PostgreSQL credentials, restricted network access, backup/restore, and HTTPS reverse proxy.

Startup rejects insecure production auth/email settings. SMTP adapter exists but production delivery is **not verified until a working SMTP account is configured and tested**. The adapter logs a generic failure without recipients/tokens; inspect deployment configuration if mail does not arrive.

The included frontend Docker service runs Vite for local development. For production, serve `npm run build` output behind your HTTPS static server/reverse proxy and set the API URL at build time. Do not expose the Vite development server as an internet production frontend.

Rate limiting is an IP plus normalized-account digest sliding window in bounded process memory: login 10/minute, register 5/minute, forgot/reset 5–10/5 minutes, resend 3/5 minutes, refresh 60/minute. It resets on restart and is not shared across workers. The current single Uvicorn process is supported; multiple replicas need a shared limiter or gateway policy. Forwarded IP headers are not trusted by the limiter. Old spent token/session records currently require scheduled retention maintenance at scale. There is no MFA or workspace/team membership in this phase.

## Validation

Backend: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` (`$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'` in PowerShell). Tests use a fresh SQLite database, temporary storage, real auth dependencies and independent clients. Coverage includes credentials/status, JWT claims/signature, sessions, rotation/reuse, password reset/verification, CSRF/rate limits, project/image ownership, polygon/export regression and populated unversioned Alembic upgrades.

Frontend: `npm test` and `npm run build`. Auth tests cover validation/loading/errors, profile/password forms, user menu, protected redirects, reload restore, in-memory tokens, concurrent refresh, logout and bounded retry.

`backend/scripts/verify_postgres.py` performs an additional smoke test on a separately created disposable PostgreSQL DB named `annotation_phase5_test_*`, refusing the actual application DB. It checks the populated unversioned baseline, preserved geometry, concurrent duplicate registration, owner-only image/annotation/export access and concurrent refresh replay. Create/provide this test DB separately and pass its DATABASE_URL; the script does not drop any database.

## Verified results for this implementation

* Backend: 39 tests passed both on Windows and in the Linux Docker image (only deprecation warnings in older legacy timestamp helpers and the test HTTP client).
* Frontend: 18 tests passed; TypeScript and Vite production build passed.
* PostgreSQL smoke: populated unversioned migration, geometry preservation, concurrent registration, resource isolation, authenticated images, polygon/export and refresh replay checks passed.
* Browser E2E used separate test services on ports 5174/8001 and a disposable PostgreSQL database. Registration, login, user menu, profile save, reload/session restore, password change/sign-in-again, logout and protected redirects passed with no console errors. Login and security layouts were inspected at desktop/mobile sizes.
* Actual database upgrade reached `0002_auth`. Before/after checksums match for all 37 image rows and 4 annotation rows. Both legacy projects remain unclaimed. A pre-upgrade backup is at `storage/.backups/annotation-before-phase5.dump`.
* The existing React Router, Vitest and Tailwind dependencies were updated to patched versions while preserving the current React/SVG UI. `npm audit` reported zero vulnerabilities after these updates. This does not claim an exhaustive audit of every backend/AI transitive dependency.

No SMTP delivery or legacy owner assignment is claimed as completed; both need the deployment configuration/operator choice described above.
