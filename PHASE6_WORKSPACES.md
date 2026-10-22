# Phase 6 — Workspaces, Team Collaboration & RBAC

## 1. Architecture and repository inspection

Implemented in the existing FastAPI/SQLAlchemy + React/Vite application; Phase 5 authentication was retained. Inspection found integer project/image/class/annotation IDs, UUID user IDs, functional JWT/rotating refresh sessions, nullable `projects.owner_user_id`, and no workspace tables. Existing authorization was centralized in `auth_dependencies.py`; it now resolves membership rather than comparing owner metadata. The annotation editor is the existing **SVG implementation**, not react-konva.

The access chain is **User → current DB membership → Workspace → Project → Image → Annotation/Prediction**. Every authenticated project operation resolves its workspace from the database. `owner_user_id` is retained as historical creator/legacy metadata and grants **no access**. A null workspace is locked, never publicly accessible. All workspace members can access all projects in that workspace at their role's permissions; per-project assignment is intentionally not implemented.

## 2. Database schema

Added UUID-keyed `workspaces`, `workspace_members`, `workspace_invitations`, and `audit_logs`; project IDs and all child IDs remain integers.

| Table | Important fields and constraints |
| --- | --- |
| workspaces | name, globally unique normalized slug, description, created_by, timestamps; unique nullable personal_user_id provides an idempotent personal-workspace identity, **not** authorization |
| workspace_members | workspace_id, user_id, role, joined_at, invited_by; unique (workspace_id,user_id); database check for the five roles |
| workspace_invitations | normalized email, role, SHA-256 token hash, invited_by, expiry, accepted/revoked timestamps; unique token hash; partial unique (workspace_id,email) while neither accepted nor revoked |
| audit_logs | historical workspace/actor UUIDs, action, resource_type/id, JSONB metadata on PostgreSQL, timestamp; indexed workspace/time |
| projects | new indexed nullable workspace_id FK; existing owner_user_id retained |

Expired invitation rows are explicitly closed under a workspace operation lock before re-inviting. The partial index does not rely on `now()` in an index predicate. Audit historical IDs intentionally have no cascading FK so deleting a workspace cannot erase the audit trail.

## 3. Alembic, dry-run and recovery

`0003_workspaces` follows `0002_auth`. It only adds tables/indexes/constraints and the nullable project FK. It does **not** automatically assign projects or rewrite child rows. PostgreSQL uses additive ALTER; SQLite migration compatibility is tested. Downgrade intentionally refuses destructive table removal.

Backfill is separate and operator-only:

```powershell
docker compose exec -T backend python -m app.migrate_workspaces --project-ids 1 2 4
docker compose exec -T backend python -m app.migrate_workspaces --project-ids 1 2 4 --apply --confirm-project-ids 1 2 4
```

Without `--apply`, no ownership data changes. Apply requires the same explicit ID set twice. Missing IDs fail; already-mapped IDs are reported and left alone. Only active, identified owners are mapped to their own personal workspace; unidentified/disabled-owner projects remain locked. An existing personal workspace must still have that original user as owner. User/project row locks and workspace operation locks protect the mapping. Original project timestamps are explicitly preserved.

`workspace_id` intentionally remains nullable for locked legacy/orphan records. A future NOT NULL migration must first validate that **all** projects are mapped; application create APIs never create an unassigned project. A new registered account receives its own personal workspace. Creating a project without workspace_id is an older-client compatibility path into the authenticated user's personal workspace; GET projects without a workspace filter aggregates **only** current memberships. The new frontend always sends the selected workspace explicitly.

Before upgrades: inspect owners, stop application writes gracefully, take `pg_dump -Fc` plus a storage backup, verify the dump with `pg_restore --list`, dry-run, and confirm exact mappings. Never reset PostgreSQL or delete Docker volumes.

Local backup artifacts from this deployment (private, git-ignored):

- `storage/.backups/annotation-before-phase6-20261021.dump` — 107,728 bytes.
- `storage/.backups/annotation-files-before-phase6-20261021.tar.gz` — 48,506,426 bytes; projects, shared models and the private development signing key.

Recovery: keep the app in maintenance mode, restore a backup into a **separate** database, validate IDs/owners/child rows and file paths, then deliberately switch DATABASE_URL/code version. Do not blindly restore over a live database or run `alembic downgrade`. After team collaboration begins, rolling code back to owner-only Phase 5 would also remove team access; reconcile any post-backup writes first. No automatic rollback deletes new workspace/team records.

## 4. Permission matrix

`backend/app/services/rbac.py` is the single source of role permissions; unknown roles and unregistered operations are denied.

| Action | Owner | Admin | Annotator | Reviewer | Viewer |
| --- | :---: | :---: | :---: | :---: | :---: |
| Read workspace/projects/images/classes/annotations/predictions/splits | ✓ | ✓ | ✓ | ✓ | ✓ |
| Create/update/delete annotations | ✓ | ✓ | ✓ | ✓ | — |
| Detection/segmentation inference and prediction accept/reject/edit | ✓ | ✓ | ✓ | ✓ | — |
| Save model class mappings | ✓ | ✓ | ✓ | ✓ | — |
| Create/rename/delete classes directly | ✓ | ✓ | — | — | — |
| Create/update/delete projects, upload/delete images | ✓ | ✓ | — | — | — |
| Configure split and export datasets | ✓ | ✓ | — | — | — |
| Workspace general settings | ✓ | ✓ | — | — | — |
| View member email list/invitations/audit logs | ✓ | ✓ | — | — | — |
| Invite/manage members | All roles | Annotator/Reviewer/Viewer only | — | — | — |
| Grant ownership / change or remove owners | ✓, except last active owner | — | — | — | — |
| Delete workspace | ✓ | — | — | — | — |

Reviewers currently share annotation and prediction-review permissions with annotators; formal quality approval belongs to Phase 7. Accepting an unmapped prediction may create its missing class **only** as part of that validated acceptance; this does not grant manual class administration. This preserves the existing AI-assisted workflow.

Ownership transfer is two-step: an owner promotes another **active** member to owner, then the departing owner can be demoted/removed. Concurrent demotions cannot eliminate the final active owner. Admins cannot manage other admins or owners or promote themselves.

## 5. APIs and authorization

All endpoints below require active authentication; accepting an invitation also requires a verified email.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST / GET | /api/workspaces | Atomic workspace+owner creation / list current memberships only |
| GET / PATCH / DELETE | /api/workspaces/{workspace_id} | Details/statistics, allowlisted settings, owner-confirmed deletion |
| GET | /api/workspaces/{workspace_id}/members | Member names, emails, roles, status and joined dates |
| PATCH / DELETE | /api/workspaces/{workspace_id}/members/{user_id} | Role changes / immediate removal |
| POST / GET | /api/workspaces/{workspace_id}/invitations | Invite / list without token hashes or raw tokens |
| DELETE | /api/workspaces/{workspace_id}/invitations/{invitation_id} | Revoke invitation under role policy |
| POST | /api/invitations/accept | Atomic, single-use acceptance by matching verified email |
| GET | /api/workspaces/{workspace_id}/audit-logs?limit=50 | Owner/Admin audit view; limit capped at 200 |
| GET | /api/projects?workspace_id={uuid} | Tenant-filtered project listing |
| POST | /api/projects | workspace_id supplied, membership/create permission checked; owner from session |
| PATCH | /api/projects/{project_id} | Only name and description; no owner/tenant movement |

Workspace DELETE body: `{"confirmation":"Exact workspace name"}`. Invitation body: `{"email":"member@example.com","role":"annotator"}`. Accept body: `{"token":"..."}`. Project responses include workspace_id and effective permission names for UI gating, never as an authorization substitute.

The central route-template registry covers every existing project/image/class/annotation/split/export/inference/prediction mutation and read. Reusable project/image/annotation/workspace checks traverse DB relationships. Bulk delete verifies **all** IDs belong to the authorized project before deleting any. Foreign-workspace resources return 404; an existing member lacking an action returns 403. Authenticated media uses the same workspace chain and path confinement; no public storage mount exists.

JWTs contain identity/session information, not cached workspace roles. Membership is re-read on each request. Removing a member immediately blocks subsequent API/media requests even with an unexpired JWT. No service-account or owner metadata bypass exists.

## 6. Frontend and usage

Added WorkspaceProvider, WorkspaceSwitcher, CreateWorkspaceModal, WorkspaceSettingsPage and InvitationPage. The existing sky-blue/white layout, project cards, image gallery, SVG canvas, export and authentication pages are reused.

1. Sign in at `http://localhost:5173`. Select a workspace in the sidebar, or use **New workspace**.
2. The dashboard shows real project/image/annotation/member totals and project cards for the selected workspace. Create Project attaches to that workspace.
3. Owners/Admins open **Workspace settings** → General / Members / Invitations / Audit log / Danger Zone.
4. Use **Invite member**, pick an allowed role, and send the invitation. Duplicate/permission/delivery errors are visible. Invitations expire after seven days.
5. Recipients open the invitation email link, sign in on that page or register in another tab, verify their email, return and accept. Tokens remain in page memory, not localStorage/sessionStorage; the URL fragment is removed. Reloading that page requires reopening the email link.
6. In Members, permitted role dropdowns and removal confirmation reflect actor policy. Owner transfers use the two-step process above.
7. Viewers see projects/images/classes/annotations with a **Read-only · Viewer** editor, no save/draw/delete/inference/export controls. Annotator/Reviewer keep annotation and AI controls but not administrative deletion/export.
8. Danger Zone shows affected counts, then requires typing the exact workspace name. Only owners can confirm.

Workspace context is keyed by validated workspace ID and role: switching remounts project/editor state, clears selections/drafts/cache, and navigates to Projects. Last workspace ID (non-secret) may be remembered per user, but is checked against API memberships. Focus/15-second refresh revalidates membership; denied project/media requests clear mounted data and revalidate immediately. Already-displayed pixels cannot be remotely erased instantaneously; server checks still block all subsequent unauthorized requests. Switching with unsaved work clears that work, so save before switching.

## 7. Actual migration results — 2026-10-21

User explicitly approved migrating all three identified projects after backup/testing. Result:

| Project ID | Name | Workspace | Original owner / current workspace role |
| --- | --- | --- | --- |
| 1 | first | MouhJi's workspace | giapnguyen1802@gmail.com / owner |
| 2 | segmentation | MouhJi's workspace | giapnguyen1802@gmail.com / owner |
| 4 | segment people | MouhJi's workspace | giapnguyen1802@gmail.com / owner |

Workspace UUID: `441b6dfc-1a00-4e16-8311-c228cf095057`. Unmapped projects: **0**. Revision: **0003_workspaces**. Repeated dry-run reported IDs 1,2,4 already mapped; it created no duplicate workspace or assignments.

Before/after full-row aggregate checksums matched for all original project metadata (excluding the new workspace column), images, annotations, classes, predictions and class mappings. Original project timestamps and owner IDs were preserved. Counts remain **3 projects / 55 images / 4 annotations**. All **55 original image files** were also compared byte-for-byte against the storage archive: identical. No paths were moved.

## 8. Security and concurrency testing

Test coverage includes default-deny matrix, explicit route coverage, owner-last-member protection, forged workspace/owner fields, IDOR across projects/images/classes/annotations/media, no partial bulk deletion, viewer mutations, annotator/reviewer AI acceptance, stale JWT after removal, verified/wrong-email acceptance, hashed tokens, expiry/revocation/replay, duplicate/re-invitation lifecycle, inviter-demotion invalidation and private audit metadata.

`scripts/verify_phase6_postgres.py` refuses non-disposable database names. It was run against two separate PostgreSQL test databases, including the final release image. Verified populated Phase-5→Phase-6 migration/backfill, preserving polygon data and orphan isolation; concurrent owner demotions leave one owner; concurrent invite/accept yields exactly one winner/membership; and a deliberately held real request locks out delete/member removal during segmentation inference. A subsequent removal blocks existing JWT/media access. Deleting the test workspace removed its detection/segmentation data while the independent legacy tenant remained intact.

Workspace mutations use a non-waiting **PostgreSQL session advisory lock on a dedicated connection**, held across existing services' commits. This serializes inference/save/export/delete/member changes across workers. A conflicting operation returns **409** for retry rather than racing a long AI request. The lock releases on normal failure or connection/process exit. SQLite tests use a process-local lock fallback; PostgreSQL is the supported collaboration deployment. Current inference is synchronous; no background queue/job exists. Actor and workspace are attached to the request, and no worker bypass was introduced.

## 9. Regression and browser results

Final release image:

- **84 backend tests passed**: original Phase 1–5 regression plus Phase 6, including migrations, SVG-compatible polygon schema, auth/refresh/reset/verification, classes, image/project deletion, detection/segmentation and exports.
- **32 frontend tests passed**: auth/API client plus 14 workspace tests covering switching, creation, settings/member UI, invite/error, role options, removal confirmation, acceptance, read-only editor, hidden actions and deletion confirmation.
- TypeScript + Vite production build passed inside Docker.
- PostgreSQL concurrency/migration smoke passed on the final image.
- Real YOLO detection and segmentation models both inferred on isolated demo images, each produced one prediction, accept-all had zero failures, and both exported valid ZIPs with data.yaml. Non-empty polygon/bbox acceptance is also covered by deterministic regression fixtures.
- Browser checks on isolated ports 5174/8001: owner login, switching, live statistics, member table, create-and-switch, logout, viewer login, hidden admin/upload/export actions, and Viewer polygon rendering. No JavaScript console errors. Screenshot: `docs/phase6-viewer.png` (demo data, not the user's dataset).
- Live deployment: health 200; anonymous workspace/project/media access 401; file and DB checksum verification as above.

Commands for repeatable container tests:

```powershell
docker compose run --rm --no-deps -e DATABASE_URL=sqlite:// -e STORAGE_PATH=/tmp/phase6-tests -e APP_ENV=test backend python -m pytest -q
docker compose run --rm --no-deps frontend npm test
docker compose run --rm --no-deps frontend npm run build
```

For PostgreSQL smoke use a **new empty** database whose name begins `annotation_phase6_test_`, a temporary storage path, and `python scripts/verify_phase6_postgres.py`. Never point fixture scripts at the app DB. `seed_phase6_ui.py` / `verify_real_yolo.py` have the same disposable-DB guard. Unit tests never need to download model weights; the optional real-model smoke can download the detection model.

Warnings remain from existing naive `datetime.utcnow` defaults and Starlette's httpx TestClient deprecation; tests pass. A clean `npm ci` corrected stale host node_modules inconsistent with the lockfile; no new frontend dependencies were needed.

## 10. Deployment and deletion safety

Backend/frontend images rebuilt and running at ports **8000/5173**. The existing PostgreSQL container remained healthy; its volume was not recreated, reset or removed. Backend startup only applies additive Alembic migrations. A brief graceful backend stop provided a consistent backup/backfill window; frontend/backend were then replaced. Shared `.pt` weights now default to persistent `storage/models/`, outside project folders; the existing segmentation weight was preserved and the tested detection weight cached there too. Explicit model-path overrides remain supported.

After verification the two temporary UI containers and the two explicitly named disposable PostgreSQL test databases were removed. Only generated demo/test records were discarded; real app data and both pre-Phase-6 backups remain intact. Browser screenshots and repeatable fixture scripts are retained.

Workspace deletion stages **only its projects' validated numeric-ID folders**, deletes their predictions/annotations/mappings/images/classes/projects and workspace memberships/invitations in one DB transaction, and retains audit evidence. DB failure restores staged folders (tested). Shared models are never included. Filesystem cleanup after commit is best-effort; a warning identifies pending `.trash/project-ID-UUID` quarantine. A crash can leave quarantine, not silently delete another tenant's files.

For recovery/retry of one exact project quarantine:

```powershell
docker compose exec -T backend python -m app.recover_storage --quarantine project-123-EXACT32HEXUUID
# Review dry-run first. Then repeat with --apply --confirm-quarantine and the exact same basename.
```

The operator CLI restores only if the project row still exists and the target is absent; otherwise it purges only that confirmed orphan quarantine. It refuses unrecognized names/paths and overwrites. Do not bulk-delete `.trash`, use broad shell deletion, or change storage paths casually.

Audit is append-only through application APIs. Owner/Admin can read the current workspace's audit log; no user can delete/edit it. Deleted-workspace logs remain available only to database operators. Retention policy: **at least 365 days**, no automatic purge. `python -m app.audit_retention --before YYYY-MM-DD` is dry-run; explicit apply requires matching `--confirm-before`. It rejects a cutoff that would remove the most recent 365 days. Keep audit/backups private; they contain operational/personal data, and the storage archive contains the development signing key. No password/token/request bodies are placed in audit metadata.

## 11. Known limitations and production readiness

- SMTP is **not configured locally**. Invitation/reset/verification `.eml` files are private under `storage/.emails`; the UI clearly labels development delivery. Operators can open those files locally for testing; they are never served by the API. Configure EMAIL_BACKEND=smtp, SMTP settings, HTTPS, secure cookies and production secrets before inviting real remote teammates. Failed invitation email delivery is shown separately; fix SMTP, revoke, then re-invite.
- All projects in a workspace inherit the same role; no project assignment/quality workflow, augmentation or new annotation formats are included.
- The pre-existing SVG editor has bbox/polygon creation and display but does **not** fully implement draggable polygon vertices or zoom/pan; older README wording overstated these features. Phase 6 keeps that implementation and its geometry unchanged, not a canvas rewrite. Full manual shape editing remains separate work.
- Workspace writes are serialized; simultaneous operations can receive retryable 409. This is a conservative collaboration foundation, not high-throughput multi-editor realtime synchronization. Existing annotation APIs do not implement optimistic versioning or conflict merging.
- No background job queue exists. A future queue must persist actor/workspace/project, check at enqueue **and execution**, and coordinate deletion/revocation with the same tenant boundary; do not blindly reuse a stale grant.
- Local compose is still a development deployment with Vite dev server and local database credentials. Production must use a static frontend build, HTTPS reverse proxy, managed secrets/database backup controls, configured SMTP and a shared rate limiter for multiple processes/hosts.
- Operators must transfer ownership before directly disabling the final active owner in the database; no account-status administration API is added here.

## 12. Phase 7 readiness

UUID tenant/membership identities, centralized permissions, audit actions, resource ancestry and verified invitations provide the base for assignment and quality review. Phase 7 should add real task-assignment/review models, scoped assignment permissions, revision/conflict management, durable jobs and execution-time authorization before exposing those controls. No placeholder assignment or fake approval UI is shipped in Phase 6.
