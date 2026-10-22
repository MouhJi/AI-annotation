# Phase 6.3 — Annotation attribution

Implemented for the existing SVG editor (the application no longer uses Konva).

## Database and migration

`0006_annotation_attribution` adds nullable indexed `created_by` and `updated_by`
foreign keys to `users.id`, with `ON DELETE SET NULL`. Existing rows are left
unattributed; no guessed backfill. Added `source` (legacy/manual/ai_accepted) and
integer `version`. Existing UTC timestamps are converted to PostgreSQL TIMESTAMPTZ,
interpreting the former naive values as UTC. IDs, classes, coordinates and polygon
JSON are preserved. User removal from a workspace and account disabling do not
remove attribution. Permanent user deletion, if implemented separately, anonymizes
these references without cascading annotation deletion; other account references
still follow their own retention policies.

Before deployment the real PostgreSQL database was backed up privately to
`storage/.backups/annotation-before-phase63-20261022.dump`. All 16 original annotation
rows retained their original-column checksum after migration, including timestamps.
All 16 retained null authors. No database/volume reset was performed.

## Backend API and save behavior

Annotation responses now include `created_by` and `updated_by` as `{id, full_name}`
or null, UTC `created_at`/`updated_at`, `source` and `version`. No author email,
password or session fields are exposed. Listing joins both authors and class in
one query, independent of object count. Author IDs come from authenticated users;
client-supplied authors/source are ignored. Renaming a user is reflected on reload.

Manual POST assigns both authors to the creator. PUT preserves the creator and
updates the last editor/time/version only when geometry or class actually changes.
Polygon comparison ignores JSON whitespace. Existing individual PUT supports an
optional `expected_version` and returns 409 for a stale version.

The editor now uses `PUT /api/images/{image_id}/annotations` with `items` and
`expected_versions` (the full original ID/version map). It validates the complete
payload and checks the image snapshot before mutation. Existing IDs/authors survive;
only removed IDs are deleted and only new objects are inserted. Changes commit in
one transaction. A stale image, including another member adding/deleting an object,
returns 409 without partial writes. Reload before retrying, since automatic merge
is not implemented. Save is disabled during an active request.

The existing centralized workspace permission and lock system remains in effect.
Batch creation/deletion additionally checks the relevant create/delete permissions.
Viewers can read attribution but cannot save. Foreign workspace objects remain
inaccessible.

## Editor and AI review

Canvas labels display `Class · Creator` for boxes and polygons, selected or not.
Labels use a dark background, bounded placement, Unicode-aware truncation, and
ignore pointer events so selection remains available. The object list and selected
object details display full names; details also show creation time, last editor,
last edit time and source. New drafts show Unsaved, old unattributed rows show
Unknown annotator.

Pending AI proposals retain their distinct dashed pink/confidence display and have
no official author. Accept and Accept All create official annotations with both
authors set to the authenticated accepting member and source `ai_accepted`.
Class mapping and missing-class creation remain unchanged. Existing prediction
links retain model class/confidence provenance; the old schema does not persist
the model filename/version, so this phase does not invent one. Repeated acceptance
does not change the original accepting author.

## Validation

- Complete backend regression suite: 112 passed (auth, workspace RBAC, management,
  detection/segmentation, predictions, exports, deletion, migration and attribution).
- Attribution/migration rerun after the final comparison change: 6 passed.
- Frontend: 54 passed; TypeScript and Vite production build passed.
- PostgreSQL populated migration and workspace concurrent permission/invitation
  checks passed, including segmentation acceptance, export and tenant isolation.
- Dedicated PostgreSQL attribution script checks two-member editing, no-op saves,
  rename, removed-member retention, and competing atomic saves (one 200, one 409).
- Running backend health returns ok; frontend returns HTTP 200; Alembic is at head.

Tests use private temporary files/file-mode emails; no test mail is sent to Gmail.
YOLO tests mock inference rather than download or run new model weights. Existing
datetime/httpx deprecation warnings remain.

## Limits

The existing SVG canvas has fit-to-image scaling, not interactive zoom/pan. This
phase preserves those controls and does not add new geometry editing tools. Dense
labels can still overlap; full names are available in the object list/details.
Custom clients omitting `expected_version` on the legacy single-object API retain
last-write behavior; the shipped editor uses mandatory batch snapshot checks.
Direct single-object deletion and Delete All retain their existing semantics.
Attribution is creator plus latest editor, not a complete version-by-version audit.
