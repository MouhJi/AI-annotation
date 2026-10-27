# Repository Guidelines

## Project Structure & Module Organization

- `backend/app/`: FastAPI routers, Pydantic schemas, SQLAlchemy models, and business services. Authorization lives in `auth_dependencies.py` and `services/rbac.py`.
- `backend/alembic/versions/`: database migrations; `backend/tests/`: Pytest tests; `backend/scripts/`: integration and maintenance utilities.
- `frontend/src/`: React/TypeScript pages, components, hooks, and the `auth/`, `workspaces/`, `invitations/`, and `admin/` modules. Tests sit beside frontend source files.
- `docs/`: documentation assets; `storage/`: runtime images, model weights, and private development files. Consult `README.md` and the relevant `PHASE*.md` guide before changing an existing workflow.

## Build, Test, and Development Commands

Run Compose commands from the repository root with Docker Desktop’s Linux engine running:

- `docker compose up -d --build`: build and start PostgreSQL, backend, and frontend; backend startup applies Alembic migrations.
- `docker compose exec backend pytest -q`: run backend tests.
- `docker compose logs -f backend`: inspect backend logs.
- `docker compose down`: stop services while retaining database volumes.

From `frontend/`, run `npm ci` to install locked dependencies, `npm run dev` for Vite development, `npm test` for Vitest, and `npm run build` for TypeScript checks and a production bundle. The app uses port 5173; API documentation is at `http://localhost:8000/docs`.

## Coding Style & Naming Conventions

Prefer four-space Python and two-space TypeScript indentation for new code; preserve surrounding conventions without unrelated reformatting. Use `snake_case` for Python functions/modules, `PascalCase` for React components/types, and `camelCase` for JavaScript functions. Keep routers thin and reusable business rules in services. TypeScript strict mode is enabled; no dedicated formatter or lint command is configured.

## Testing Guidelines

Use `test_*.py` and `test_*` functions for Pytest; use `*.test.ts`/`*.test.tsx` for Vitest and Testing Library. Backend fixtures isolate SQLite, temporary storage, and file email. Mock inference/SMTP when appropriate. Cover changed behavior, especially geometry, version conflicts, tenant isolation, and permission denial. No numeric coverage threshold is configured.

## Commit & Pull Request Guidelines

History uses short descriptive messages, without an established Conventional Commits scheme. Write concise, imperative subjects and keep changes focused. PRs should explain behavior, validation commands/results, migration implications, and related issues. Include screenshots for UI changes and describe permission changes explicitly.

## Security & Configuration

Copy `.env.example` to a private `.env`; never commit secrets, tokens, emails, backups, or model weights. Enforce permissions in the backend: Platform Admin does not imply workspace access. Preserve annotation identity, attribution, version checks, and soft-delete behavior. Maintenance scripts may mutate data; inspect their safeguards before running them.
