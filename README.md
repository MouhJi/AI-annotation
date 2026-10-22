# Data Annotation Platform MVP

## Phase 6.4 — public landing page

Visit `http://localhost:5173/` for the public product page and interactive sample
annotation preview. Get Started opens registration for guests or `/projects` for
signed-in users. Existing protected application routes remain unchanged. See
[PHASE6_4_LANDING.md](PHASE6_4_LANDING.md) for components, validation and limitations.

## Phase 6.3 — annotation attribution

Saved boxes/polygons show `Class · Creator`. Select an object to see its creator,
last editor, timestamps and manual/AI-assisted source. Accepting AI results credits
the accepting member. Legacy objects show Unknown annotator. Image Save is atomic
and rejects concurrent changes with a reload message. See
[PHASE6_3_ATTRIBUTION.md](PHASE6_3_ATTRIBUTION.md) for API, migration, tests and limits.

## Phase 6.2 — real email delivery

Gmail/SMTP delivery, HTML + plain-text templates, delivery receipts, a Check Your
Email page and verification confirmation are implemented. Configure `EMAIL_PROVIDER=smtp`
and private SMTP credentials in your local `.env` to enable real delivery. File mode
is for offline development/tests and cannot deliver to Gmail. See
[PHASE6_2_EMAIL.md](PHASE6_2_EMAIL.md) for secure Gmail App Password setup, diagnostics,
real-inbox testing, endpoints, migration and operational limitations.

## Phase 6 — workspaces and team roles

Workspaces, switching, members, verified-email invitations, centralized five-role RBAC, read-only Viewer editor, confirmed workspace deletion and audit logging are implemented. See [PHASE6_WORKSPACES.md](PHASE6_WORKSPACES.md) for the architecture/schema, permission matrix, all endpoints, migration/backup/recovery instructions, test results and known limitations.

Select a workspace in the sidebar. Owners/Admins use **Workspace settings** to manage the team; only Owners can delete a workspace. Annotators/Reviewers can annotate and use AI but cannot administer datasets/export; Viewers are read-only. Each project inherits workspace membership, **not** its historical owner_user_id. Existing owner-to-workspace migration is an explicit dry-run/operator command, never automatic at startup. The confirmed local migration preserved all 3 projects, 55 images and 4 annotations.

Invitations require the matching **verified** email. Existing users receive them in the in-app notification bell and **Invitations** page, where they can accept or decline without handling a token. Email links remain supported for onboarding and are saved privately under `storage/.emails` in development; configure SMTP and HTTPS for production. Owners/Admins can resend or revoke a pending invitation. Save changes before switching workspaces, since switching clears project/editor selections and drafts.

## Phase 5 — accounts and private projects

Authentication, profile/security settings, refresh sessions, email verification and password reset are now implemented. See [PHASE5_AUTH.md](PHASE5_AUTH.md) for migration, API, security configuration and tests.

On upgrade the backend runs inspected Alembic migrations automatically. Register/sign in at `http://localhost:5173`. Existing project/image/annotation data is preserved, but legacy projects stay locked until an operator confirms their owner using the documented dry-run/claim command. No project is assigned automatically to the first registered user. Keep your PostgreSQL volume; never run `docker compose down -v` to upgrade.

For local Python startup, run `alembic upgrade head` before Uvicorn. Development reset/verification emails are private `.eml` files under `storage/.emails`; production needs configured SMTP and HTTPS. The following earlier feature guide still applies after authentication and ownership claim.

An image-labeling application built with React/Vite and an SVG annotation canvas, plus FastAPI/SQLAlchemy/PostgreSQL. Images are stored in the local `storage/` directory; only metadata and original-image pixel coordinates are persisted in the database.

## Run with Docker

```bash
cd annotation-platform
docker compose up --build
```

Open `http://localhost:5173`; API docs are at `http://localhost:8000/docs`. To seed the default Traffic Detection project, run `docker compose exec backend python seed.py`.

## Run locally

Install Python 3.11+ and Node 20+. In `backend`, create an environment, install `requirements.txt`, set `DATABASE_URL` (SQLite is supported for single-process tests), run `alembic upgrade head`, then `uvicorn app.main:app --reload --port 8000`. Collaboration deployment uses PostgreSQL. In `frontend`, run `npm ci`, copy `.env.example` to `.env`, then `npm run dev`.

## Main API

| Area | Endpoints |
|---|---|
| Projects | `POST/GET /api/projects`, `GET /api/projects/{id}` |
| Classes | `POST/GET /api/projects/{id}/classes`, `DELETE /api/classes/{id}` |
| Images | `POST/GET /api/projects/{id}/images`, `GET /api/images/{id}` |
| Annotations | `GET/POST /api/images/{id}/annotations`, `PUT/DELETE /api/annotations/{id}` |
| Dataset | `GET/PUT /api/projects/{id}/dataset/split`, `POST /api/projects/{id}/dataset/export/yolo` |

## Export a YOLO dataset

On a project's detail page, set **Train**, **Validation**, and **Test** percentages (the default is 80/10/10), then click **Save split**. The assignments are stored per image and remain stable across exports. Small datasets prioritize at least one training image; validation or test may be empty when there are too few images.

Click **Export YOLO** to download a ZIP containing `data.yaml`, `images/{train,val,test}`, and matching `labels/{train,val,test}` directories. Labels use normalized YOLO detection rows: `class_id x_center y_center width height`. The class id is the zero-based project-class order. Empty-label images are included with an empty `.txt` file, which is valid for YOLO training.

Train, for example, with Ultralytics after unzipping:

```bash
yolo detect train data=/path/to/dataset/data.yaml model=yolo11n.pt epochs=50
```

## AI-assisted labeling and safe class mapping

Phase 3 uses Ultralytics detection with the stable `yolo11n.pt` fallback (rather than `yolo26n.pt`, which is not consistently available across Ultralytics environments). The model is loaded lazily and cached after the first **Run Auto Labeling** request; startup and tests never download model weights.

Set these backend variables in `.env` or Docker Compose:

```text
YOLO_MODEL_PATH=yolo11n.pt
YOLO_DEVICE=cpu
YOLO_CONFIDENCE_THRESHOLD=0.25
YOLO_IOU_THRESHOLD=0.45
```

Put a downloaded `.pt` file at the configured path, or use the `yolo11n.pt` name and allow Ultralytics to download it only on the first inference request. Use `YOLO_DEVICE=cuda` only on a host with CUDA available; the API returns a clear error otherwise.

The supplied Docker image installs CPU PyTorch for portable inference. For CUDA inference, build an equivalent image with the matching NVIDIA PyTorch wheel and NVIDIA Container Toolkit, then set `YOLO_DEVICE=cuda`.

### Headless Docker runtime

The backend deliberately replaces GUI OpenCV with `opencv-python-headless`. This prevents Linux GUI/X11 dependencies such as `libxcb.so.1` from being loaded during YOLO inference. The image retains `libglib2.0-0`, which is a non-GUI runtime dependency used by common image-processing wheels. Do not install `opencv-python` alongside the headless package.

### Annotation and class deletion

The editor's **Delete All Labels** action deletes only saved annotations on the current image; it deliberately leaves pending AI predictions untouched. Accepted prediction records linked to deleted labels are marked rejected so their annotation foreign keys cannot become invalid. It sends `DELETE /api/images/{image_id}/annotations` and resets client state before a subsequent save can restore stale boxes.

Project classes can be deleted from Project Detail. The backend returns `409 Conflict` instead of deleting a class that is referenced by annotations, AI predictions, or an AI class mapping. Delete or remap those references first; existing annotation data is never cascaded away.

Images can be deleted from the **⋯** menu in the Images tab, or in bulk after selecting images. The API is `DELETE /api/images/{image_id}` and `POST /api/images/bulk-delete`. Bulk deletion validates every ID belongs to the specified project before changing anything. Related predictions are removed before annotations and image rows, while project classes and all other images remain untouched. Image files are moved into `storage/.trash` before the database commit, restored if the commit fails, and physically removed after it succeeds. A successful response includes `cleanup_warnings` if a file was already missing or the final filesystem cleanup needs attention.

Projects can be deleted from the Projects-card **⋯** menu through `DELETE /api/projects/{project_id}`. The UI requires the exact project name before it enables deletion. The backend quarantines only `storage/projects/{project_id}` then, in one transaction, removes that project's predictions, annotations, mappings, images, classes, and project record. It never touches model weights, other project folders, or database volumes. A response can include `cleanup_warnings` if post-commit storage cleanup needs follow-up.

An explicit mapping always has priority. Otherwise the API only matches a project class by the same trimmed, case-insensitive name; it never uses a model class index, database ID, first class, or fuzzy match. A prediction with no match is displayed as **New Class**. Accepting it (or Accept All) creates that class and the annotation atomically; rejecting it creates nothing. This makes `dog` remain `dog`, rather than being silently assigned to an unrelated project class.

Select a project class and choose **Save mapping** to persist an explicit override. Pink dashed shapes are AI proposals; solid shapes are saved annotations. Review, edit, accept, or reject each prediction, or Accept All. From Project Detail, select up to 20 detection images and run batch auto-labeling; individual failures are reported without cancelling other images.

## Instance segmentation

Create a project as **Instance Segmentation** to use polygons. In the editor, choose a class and **Polygon**, click vertices on the image, then double-click, press Enter, or select **Finish polygon**. Escape/Cancel discards the unfinished shape. Polygon coordinates are stored in original-image pixels; the API rejects fewer than three distinct points, zero-area polygons, self-intersections, and vertices outside the image. The current SVG editor supports drawing/display; draggable vertex editing and zoom/pan are not fully implemented. Viewers cannot draw, save, delete or run AI.

Instance Segmentation projects use **Auto Segment**, which produces reviewable dashed polygon proposals. Configure the cached CPU model with:

```text
YOLO_SEG_MODEL_PATH=yolo11n-seg.pt
YOLO_SEG_DEVICE=cpu
YOLO_SEG_CONFIDENCE_THRESHOLD=0.25
YOLO_SEG_IOU_THRESHOLD=0.45
```

The confidence control is sent per request. The segmentation model is loaded lazily only once per backend process. Download or provide the configured `.pt` model before its first inference. A single YOLO mask contour is stored as one polygon. Masks with holes or separate disconnected components cannot be represented losslessly in the Phase 4 single-polygon schema, so this MVP does not claim to preserve that geometry.

For a segmentation project, **Export YOLO** writes normalized polygon rows:

```text
class_id x1 y1 x2 y2 x3 y3 ...
```

Every saved segmentation annotation must be a valid polygon; bounding boxes are never silently converted to segmentation labels. Detection export remains `class_id x_center y_center width height`.

## Coordinates and architecture

The editor displays a scaled SVG canvas and converts every rectangle and polygon to original image pixels before it reaches FastAPI. Backend validation rejects geometry outside image dimensions and classes from another project. The frontend uses `useAnnotations` to diff new, changed, and removed annotations when **Save** is clicked.

`backend/app` is split into models, schemas, services, and routers. `frontend/src` contains pages, a reusable SVG canvas component, workspace/auth contexts, API service, types, hooks, and coordinate utilities. Future annotation types can extend the `annotations` domain without changing the project/image APIs. Docker model weights persist in `storage/models`, outside deletable project folders.

## Tests

Run backend tests with `pytest` from `backend`; frontend coordinate tests with `npm test` from `frontend`.
