# Phase 6.6 — Direct in-place annotation correction

Implemented in the existing SVG canvas; no Konva renderer or duplicate editor was
introduced. The running application is upgraded to `0008_annotation_correction`.

## How to use

1. Open an image and choose **Select**.
2. Click an existing box or polygon (or its entry in Objects).
3. For a box, drag its body to move it, or drag one of eight handles to resize a
   corner/edge. For a polygon, drag a vertex or drag the filled body to move it.
4. Use **Object class** in the details sidebar to change its class.
5. Click **Save**. The same database ID is updated, the creator/source remain,
   and the latest editor, timestamp and version change.

Read-only objects can still be selected and inspected. They have no editing
handles, class editing or Delete action. Canvas operations remain in original
image pixels even when the displayed image is scaled. Movement and resizing are
bounded to the image. Invalid polygon outlines are rejected by the existing API
validation and remain unsaved for correction.

## Permissions

The backend applies `Owner > Admin > Reviewer > Annotator > Viewer` per object,
using the creator's current membership role in that workspace. Members may edit
or delete their own annotations if their current role permits annotation edits.
For other authors, the actor must have a strictly higher role. Peers cannot edit
one another; Viewers cannot edit even their own old annotations. Workspace access
is checked first, so foreign projects/objects remain inaccessible.

For legacy/removed authors whose role cannot be established, only Owner/Admin
may correct the object; the creator is not reassigned. This exception is explicit
and does not guess a legacy author to be an Annotator. API response `can_edit` and
`can_delete` flags drive the UI; the backend checks all mutations independently.
Membership changes are protected by the existing workspace operation lock.

## Save, deletion and audit behavior

The editor continues using `PUT /api/images/{image_id}/annotations`. It supplies
the full original ID/version map and final item list. The transaction validates
every operation before mutation: existing changed objects are UPDATEs, new draft
objects are INSERTs, removed objects are soft deleted, and unchanged objects are
NO OPs. An unchanged locked object can remain in the batch without being edited.
Any unauthorized changed/deleted object rejects the entire batch.

Single-object `PUT /api/annotations/{id}` accepts `expected_version`; a changed
object without it returns 428. Stale versions return 409. Single-object DELETE
requires the `expected_version` query parameter. Delete All requires a JSON body
with `expected_versions` and verifies every target's hierarchy permission.

Migration `0008_annotation_correction` adds nullable indexed `deleted_at` and
nullable `deleted_by` (users FK, SET NULL). No existing row or geometry is changed.
The default ORM SELECT policy excludes soft-deleted annotations from listings,
counts and relationship loads, including YOLO export. Historical class references
still prevent deleting a referenced class. Full image/project deletion retains
its existing explicit physical cleanup behavior.

Corrections write `annotation.updated` audit entries to the existing workspace
AuditLog with before/after class, geometry, source and version. Deletion writes
`annotation.deleted`, retains original geometry/creator/source in the annotation,
and records the deleting user/time. Linked accepted predictions are detached and
marked rejected so a removed object is not silently accepted again. Audit entries
share the annotation transaction; rejected requests create no history entries.

## Files changed

- `frontend/src/components/AnnotationCanvas.tsx`: captured pointer gestures,
  selected-object resize/vertex controls and per-object permission enforcement.
- `frontend/src/components/annotationGeometry.ts`: bounded translation, box resize
  and vertex editing, with polygon bounding-box recomputation.
- `frontend/src/pages/EditorPage.tsx`: selected object class control, permission
  aware deletion, canonical state after Save and version-aware Delete All.
- `frontend/src/types/index.ts`: per-object permission flags.
- `backend/app/services/annotation_permissions.py`: role hierarchy, snapshots,
  edit audit and soft deletion.
- `backend/app/routers/annotations.py`: per-object checks on single/batch/delete,
  response permissions, concurrency preconditions and audit integration.
- `backend/app/database.py`: default soft-delete SELECT filter.
- `backend/app/models/annotation.py`, `schemas/annotation.py`,
  `routers/classes.py`, migration `0008_annotation_correction.py`.
- Backend correction tests and updated attribution/segmentation/delete/migration
  regression expectations; frontend pointer and geometry tests; isolated
  `scripts/verify_correction_postgres.py`.

## Validation and deployment

- Full backend suite: **146 passed**, including all 25 actor/creator role pairs,
  single/batch bypass prevention, no duplicate IDs, attribution, source retention,
  before/after audit, soft delete and detection/segmentation export geometry.
- Full frontend suite: **73 passed**. Includes actual component pointer events
  for box movement/resize and polygon vertex editing, plus locked-object handles.
- TypeScript/Vite production build passed.
- PostgreSQL integration: migration to head, two concurrent permitted edits
  produce 200/409, creator/ID preservation, no-op, rename and removed-member
  attribution retention passed. The isolated database was removed afterward.
- Deployment health: backend ok; frontend HTTP 200.
- Private backup: `storage/.backups/annotation-before-phase66-20261023.dump`.
  All original annotation columns retained checksum
  `f0df25b3cab19aaf897772929ef9c0bc`; 17 annotations, 125 images and 2 projects
  were preserved. No annotation was soft deleted by the migration itself.

## Limits

Adding/removing polygon vertices and interactive zoom/pan are not part of this
update. No Undo/Redo system existed in this editor, so none is claimed; cancelling
a pointer gesture restores the geometry at gesture start. Invalid/self-crossing
polygons must be corrected before Save. Soft deletion has no end-user restore UI
yet; audit/deleted rows are retained for controlled recovery. Tests use isolated
fixtures and mocked model inference; no new real-account browser session was
created for QA. Saved creator labels keep displaying the original author, not
the person making the correction.
