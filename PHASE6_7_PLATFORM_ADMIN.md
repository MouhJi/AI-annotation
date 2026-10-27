# Phase 6.7 — Platform Administration

Implemented at `/admin`, independently of workspace roles. This document is the
operator guide and implementation report. No existing user is promoted by the
migration or by application startup.

## Bootstrap and revoke

First register an account normally and complete email verification. The account
must be active. Use the trusted backend environment; there is no HTTP bootstrap
endpoint, built-in administrator email, password or default account.

Inspect a grant without changing anything:

~~~bash
docker compose exec backend python -m app.cli.grant_platform_admin --email YOUR_VERIFIED_EMAIL
~~~

Apply with an explicit matching confirmation:

~~~bash
docker compose exec backend python -m app.cli.grant_platform_admin --email YOUR_VERIFIED_EMAIL --apply --confirm-email YOUR_VERIFIED_EMAIL
~~~

Revoke a grant:

~~~bash
docker compose exec backend python -m app.cli.grant_platform_admin --email YOUR_VERIFIED_EMAIL --revoke --apply --confirm-email YOUR_VERIFIED_EMAIL
~~~

Replace both email placeholders with the same real verified address. Omit
`--apply` for a dry run. Commands are idempotent and audit actual changes as
`platform_admin.granted` / `platform_admin.revoked`. A dry run never creates a
user, verifies an email or changes privileges. Revoking the final active verified
administrator is rejected. Reload/sign in after granting to update navigation;
the backend reads the flag live for every admin request.

## Authorization design and migration

`users.is_platform_admin` is a required boolean with default false. A separate
role-assignment schema is unnecessary for this foundation's single platform role.
Workspace Owner/Admin remains completely independent. Registration/profile schemas
reject mass-assignment of this flag, and no browser mutation API can change it.

Migration `0009_platform_admin` adds this column and indexes on user/workspace
registration dates and audit actor/action fields. Existing rows are preserved and
not promoted. Current authentication, rotating refresh cookies, idle enforcement
and workspace checks remain in effect.

`require_platform_admin` requires an authenticated, active, verified user with
the database flag. It protects the entire admin router. Sensitive mutations also
recheck this state inside a cross-worker PostgreSQL advisory lock shared with CLI
role changes, preventing concurrent loss of the final administrator. Self-disable
is rejected. Account actions require target-ID confirmation, trusted Origin and
per-actor/IP rate limiting (20/minute).

## Backend endpoints

All paths have the `/api/admin` prefix.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | /dashboard/summary | Real SQL aggregate counts and definitions |
| GET | /dashboard/activity | Daily registrations, annotation creation and workspace growth, plus recent audit events |
| GET | /users | Search name/email, verification/status filters, sort/order and pagination |
| GET | /users/{id} | Safe profile, memberships, historical project ownership and recent activity |
| POST | /users/{id}/disable | Disable account, revoke sessions, retain all data/memberships |
| POST | /users/{id}/enable | Enable according to email verification policy |
| POST | /users/{id}/revoke-sessions | Revoke all unrevoked refresh sessions |
| GET | /workspaces | Search, personal/team filter and pagination |
| GET | /workspaces/{id} | Workspace metadata, owner names, paginated members, project summary and recent activity |
| GET | /projects | Metadata with search, workspace/type filters and pagination |
| GET | /audit-logs | Actor/action/resource/date filters and pagination |
| GET | /audit-logs/{id} | Read-only sanitized event detail |

Account mutation bodies contain `{"confirm_user_id":"TARGET_UUID"}`.
Paginated responses contain `items`, `total`, `page`, `page_size`.
List defaults are 20 rows, maximum 100; invalid sort/status/UUID/date values are
rejected. Detail membership lists paginate independently; project ownership is
bounded to the first 100 references. Workspace owner displays are bounded to five
names per workspace. SQL count subqueries and batched owner lookup avoid N+1
collection loads. Timestamps are serialized as UTC.

## Dashboard definitions

- Total/verified users include existing accounts in all statuses.
- Active users are accounts currently marked active that have recorded session
  activity within the last seven days. This is not an online-presence metric.
- Annotation counts and daily annotation creation exclude soft-deleted objects.
  Daily counts describe retained objects by creation date, not all historical
  edits. Current sources (manual, ai_accepted, legacy) are counted separately;
  unaccepted AI proposals are not official annotations.
- Activity series defaults to 30 UTC days (1–90 supported), including zero days.
  All values come from the database. No production demo metrics are used.

## Privacy and audit

Platform administrators receive administrative metadata only. No membership is
created for them. Existing private image/editor/export/edit APIs retain workspace
authorization. Admin metadata responses omit image URLs/filesystem paths,
annotation coordinates, passwords, token hashes and credentials.

The existing AuditLog table is reused. Account status changes and session
revocations record actor/target, previous/current status and counts. The admin
audit serializer has an explicit metadata allowlist. In particular, pre-existing
annotation correction logs contain geometry: the admin API removes those values
and retains only source/version summaries. Audit events cannot be changed or
deleted through an admin API. Account disabling never removes attribution,
objects, memberships or history. Enabling does not revive revoked sessions.

## Frontend

A separate AdminLayout/route guard sits outside WorkspaceProvider so platform
access does not depend on membership in any particular workspace. The guard checks
the current account against the server before rendering admin content.

Routes: `/admin`, `/admin/users`, `/admin/users/:userId`,
`/admin/workspaces`, `/admin/workspaces/:workspaceId`, `/admin/projects`,
`/admin/audit-logs`, `/admin/profile`.

The layout includes a responsive navigation drawer, breadcrumbs, administrator
identity, logout and Back to App. Users see loading/error/empty states, tables,
search/filter/pagination controls, real activity charts with accessible daily
count tables, and explicit account action confirmations. Profile/security reuses
the existing own-account controls. The ordinary user menu shows Admin Panel only
for flagged users; hiding navigation is not the authorization boundary.

## Files created/modified

- Backend: `models/auth.py`, `routers/auth.py`, `routers/admin.py`,
  `schemas/admin.py`, `services/platform_admin.py`, `main.py`,
  `cli/__init__.py`, `cli/grant_platform_admin.py`, migration 0009.
- Frontend: `admin/AdminLayout.tsx`, `admin/AdminPages.tsx`,
  `admin/Admin.css`, `App.tsx`, `components/AppLayout.tsx`,
  `services/api.ts`.
- Tests: `tests/test_platform_admin.py`, updated migration head assertion,
  `scripts/verify_platform_admin_postgres.py`, `admin/Admin.test.tsx`.
- Documentation: README and this report.
- Git ignore: narrowed the old `models/` rule, which also hid
  `backend/app/models/` source, to root/storage model-weight directories.
  All model source files must be included when committing; private weights,
  uploads, email files, backups and secrets retain their existing exclusions.

## Validation and deployment

- Full Docker backend regression: **160 passed**, including authentication,
  verification, idle timeout, invitations/RBAC, attribution/correction,
  boxes/polygons, mocked YOLO, export and admin security.
- Full frontend regression: **85 passed** in 12 files, including 12 admin tests.
- Strict TypeScript and Vite production build passed.
- PostgreSQL integration: migration from a populated pre-admin user database,
  zero automatic promotion, dashboard/list APIs, competing administrator-disable
  requests, final-admin retention, session revocation and audit all passed.
- Unit checks cover forbidden normal/workspace-admin/workspace-owner access,
  self-promotion, unverified/missing CLI users, dry run, grant/revoke/last-admin,
  pagination/search/filter, safe fields, disable/enable/revoke, CSRF, live role
  removal, tenant isolation and audit geometry redaction.
- Deployment: private backup saved to
  `storage/.backups/annotation-before-phase67-20261025.dump` before upgrade.
  After migration, 3 users (0 platform admins), 1 workspace, 2 projects, 125 images,
  25 sessions and 23 stored annotation rows were retained. Annotation checksum
  remained `475019962310ac9f30af49976891044c`. The test database was removed;
  no application volume was reset.

## Limitations

This phase does not grant support access to private workspace contents, implement
impersonation, billing, MFA, or a support-access approval workflow. Permission
grants/revocations are trusted CLI operations rather than browser actions.
Dashboard aggregates are uncached and count retained data, not a historical
analytics warehouse. Account mutations use the existing per-process rate limiter.
Large installations should plan index-creation maintenance and shared rate limits.
Frontend behavior is covered by component tests; no real user was promoted or
used to perform admin actions for browser QA. Responsive CSS/mobile navigation
controls are implemented/tested; a real-device visual admin review remains useful.
Existing datetime/httpx deprecation warnings remain.
