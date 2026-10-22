# Phase 6.2 — email delivery and verification

Implementation: real SMTP is ready when credentials are configured. No real Gmail
message or successful inbox delivery is claimed without an explicit live test.

## Existing behavior inspected

- `backend/app/routers/auth.py`: registration and resend created a CSPRNG token
  (`secrets.token_urlsafe`), stored only its SHA-256 hash, revoked older unused
  tokens, committed, then sent a plain-text email. Verification lifetime was 24
  hours; password reset 30 minutes. Both lifetimes are preserved.
- `app/services/email_service.py`: existing file and SMTP adapters selected through
  `EMAIL_BACKEND`; SMTP had a timeout but no explicit trusted TLS context and no
  recorded delivery result. File messages were stored privately in development.
- `/verify-email#token=...` already read the fragment and used POST confirmation.
  It never required token input. The confusing step was finding development mail
  and the lack of honest delivery feedback.
- Workspace invitation acceptance already requires a matching verified email.
  Verification does not accept invitations or create memberships.

## Provider and delivery architecture

`EmailProvider.send_email(to, subject, text_body, html_body)` has SMTP and file
implementations. The SMTP implementation uses Python's standard library; no new
package is required. It sets an explicit recipient envelope, sends multipart
plain-text/HTML messages, uses STARTTLS with `ssl.create_default_context()`, and
validates hostname and certificate against trusted CAs. It never disables TLS
validation, logs SMTP transcripts, or enables SMTP debug output.

`EMAIL_PROVIDER=smtp|file` is canonical. If unset/empty, `EMAIL_BACKEND` remains a
legacy alias; otherwise the development default is file. Production rejects file,
invalid/incomplete SMTP settings, insecure authentication, and non-HTTPS frontend
URLs/cookies/origins. Invalid frontend URL credentials, query or fragment are
rejected. Unencrypted SMTP is limited to unauthenticated local development servers.
Gmail requires port 587, STARTTLS, username and App Password.

Migration `0005_email_delivery` adds only `email_delivery_attempts`. Receipts contain
purpose, a related token/invitation ID, provider, status, safe error code and times.
No recipient, body, raw token, token hash or SMTP credential is stored in receipts.
Users, existing tokens, projects, workspaces and memberships are not rewritten.

For each send, token changes and a `prepared` receipt commit before any SMTP call.
An atomic `prepared` → `sending` claim prevents a repeated send for the same receipt.
One attempt becomes `sent` (SMTP accepted it), `development` (file saved), or
`failed`. SMTP acceptance does not guarantee inbox delivery. A process crash can
leave `prepared` or `sending`, indicating an interrupted/uncertain attempt. Operators inspect
receipts; users explicitly resend with a fresh token. There is no automatic retry,
no silently lost background task, no SMTP-to-file fallback and no plaintext-token
queue. This minimal delivery receipt is not a durable retryable outbox.

On registration delivery failure, the account remains and the 201 response carries
`email_delivery=failed`. Public resend and forgot-password use an identical generic
response for unknown, disabled, verified and eligible accounts. They never claim
delivery succeeded; file mode returns installation-wide `unavailable`. Actual
failure results remain in private receipts. Authenticated users get an exact
delivery status from `POST /api/auth/me/resend-verification`, with no arbitrary
email input. All paths are rate limited. Verification resend invalidates previous
unused links, so only the newest link should be used.

## Endpoints and UI

- Existing `POST /api/auth/register`, `/verify-email`, `/resend-verification`,
  `/forgot-password`, `/reset-password` are retained.
- Added `POST /api/auth/me/resend-verification` for signed-in users, including
  delivery feedback. Pending-verification users who cannot log in use public resend.
- `/check-email`: masked destination, delivery feedback, resend cooldown, login link.
- `/verify-email`: fragment token kept only in component memory, URL cleared,
  explicit **Verify Email** confirmation, POST, loading and success/unavailable/
  expired states. Success refreshes the current user's profile and links to
  Invitations or Login. A GET or link preview alone never verifies the email.
- Profile and workspace invitation pages share the resend component with loading,
  a 60-second browser cooldown and server rate-limit feedback. No filesystem path,
  token entry field, SMTP credentials or internal SMTP errors appear in end-user UI.
- HTML templates for verification, password reset and workspace invitation use the
  Sky Blue & White theme, escaped dynamic content, absolute URLs, expiration and
  security notices, plain-text alternatives and no external images/scripts.
- The app's HTML includes `Referrer-Policy: no-referrer` via its meta tag; API
  responses also set no-referrer and no-store. No third-party landing-page assets.

## Gmail setup on this Windows machine

1. Use a sender account you control. Enable Google 2-Step Verification if eligible,
   then create an App Password for this app. Never use the usual Gmail password.
   Google documents eligibility and restrictions at
   <https://support.google.com/accounts/answer/185833>.
2. Create/edit `annotation-platform/.env` locally (the file is ignored by Git).
   Do not paste the App Password into chat, terminal command arguments or commits.
   If a `.env` already exists, retain all unrelated settings. Copy `.env.example`
   only for a new file.
3. Set the following locally; replace placeholders, keeping the password private:

   ```dotenv
   EMAIL_PROVIDER=smtp
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USE_STARTTLS=true
   SMTP_TIMEOUT_SECONDS=10
   SMTP_USERNAME=your-sender@gmail.com
   SMTP_PASSWORD=your-private-app-password
   SMTP_FROM_EMAIL=your-sender@gmail.com
   SMTP_FROM_NAME=Data Annotation Platform
   FRONTEND_URL=http://localhost:5173
   ```

4. Recreate the backend with its new environment:

   ```powershell
   docker compose up -d --no-deps --force-recreate backend
   docker compose exec -T backend python -m app.email_diagnostics
   docker compose exec -T backend python -m app.email_diagnostics --check-network
   ```

   Diagnostics print only non-secret flags/status, never passwords or tokens.
   `--check-network` checks DNS, greeting and trusted STARTTLS without login or email.
   Avoid printing `docker compose config` or `docker inspect` environment output,
   because those can display secret environment variables.

5. Explicitly send one test to your own inbox, substituting your recipient address:

   ```powershell
   docker compose exec -T backend python -m app.email_diagnostics --send-to your-test-address@example.com
   ```

   Check inbox and spam. Then use **Resend verification email** in the actual app
   or register a new address you control. Open the newest message, click its button,
   confirm **Verify Email**, then view and accept the pending workspace invitation.
   Also test forgot/reset password with an expendable account you control.

Gmail's server/STARTTLS settings are documented at
<https://support.google.com/mail/answer/7104828>. App Passwords may be unavailable
for organization policy, security-key-only 2-Step Verification or Advanced
Protection. Do not weaken account security to work around restrictions. Instead
use an organization-approved SMTP relay or a transactional mail provider's SMTP
credentials with a verified sender/domain; the same adapter supports those.
OAuth-based Gmail delivery is not implemented by this SMTP password adapter.

`localhost` links work only on this computer. For another person's device set
`FRONTEND_URL` to the reachable app URL; configure `CORS_ORIGINS` and the frontend's
API URL accordingly. Production requires HTTPS, secure cookies, strong JWT secret,
a valid SMTP sender and appropriate domain SPF/DKIM/DMARC. A Gmail account's quotas
and spam filtering apply; this implementation does not bypass them.

## Development and operations

`EMAIL_PROVIDER=file` is explicit offline/test mode and never works in production.
Operators can inspect MIME `.eml` files under the private `storage/.emails` directory
with a mail client. Existing files are retained. No public mail viewer/debug token
endpoint exists. Mailpit is optional and not added to this deployment.

Receipt example (operator terminal only, no body/token/recipient returned):

```sql
SELECT purpose, provider, status, error_code, created_at
FROM email_delivery_attempts ORDER BY created_at DESC LIMIT 20;
```

SMTP authentication failure: recheck the local App Password and sender account.
Connection timeout: check DNS/egress/port settings without changing firewall rules
automatically. TLS failure: fix certificates/hostnames; never disable validation.
`prepared`/`sending` after interruption: request a new message; do not blindly replay unknown
SMTP outcomes. SMTP errors sent to users are generic; internal logs contain only
allowlisted error categories.

## Files and validation

Backend: `app/email_config.py`, `auth_config.py`, `models/email_delivery.py`,
`models/__init__.py`, `services/email_service.py`, `services/email_templates.py`,
`routers/auth.py`, `routers/workspaces.py`, `email_diagnostics.py`, migration
`alembic/versions/0005_email_delivery.py`, `tests/test_email.py`, `test_auth.py`,
`test_migrations.py`, `conftest.py`, `scripts/verify_phase6_postgres.py`.

Frontend: `pages/EmailVerification.tsx`, `EmailVerification.test.tsx`, `AuthPages.tsx`,
`AccountPages.tsx`, `InvitationPage.tsx`, `WorkspaceSettingsPage.tsx`, `App.tsx`,
`invitations/InvitationVerificationNotice.tsx`, `workspaces/Workspace.test.tsx`,
`styles.css`. Configuration: `.env.example`, `docker-compose.yml`, `README.md`.

Automated tests use private temporary databases/file mail or mocked SMTP; no real
emails are sent. They cover configuration, trusted TLS, exact recipient, both MIME
parts, authentication/timeout/delivery failures, no fallback or secret logging,
commit-before-send, token expiry/replay/revocation, rate limiting, generic public
responses, templates, register/verify, resend/verify, password reset and invited
user register/verify/accept. Frontend covers check-email, masking, confirmation,
fragment removal, loading, failures, cooldown, profile badge and invitation flows.

Production limits: SMTP remains synchronous with bounded timeout; receipts are not
an automatic queue. Rate limiting is process-local (deploy one backend worker until
a shared limiter is added). An SMTP-accepted email can still be rejected later or
land in spam. Sender credentials and inbox confirmation are required for live-mail
signoff. No automatic email verification or workspace membership bypass exists.

## Verified on this installation (2026-10-21)

- Docker backend: **107 tests passed** (including SMTP mocks, delivery receipts,
  token and existing detection/segmentation/export/auth/workspace regression).
- Docker frontend: **47 tests passed**; TypeScript + production build passed.
- PostgreSQL disposable databases: populated-schema migration, invitation and
  membership concurrency, owner protection, segmentation acceptance/export,
  stale membership denial and deletion isolation all passed.
- Real backend migrated to `0005_email_delivery`; backend/frontend start and
  health checks passed. Backup retained privately at
  `storage/.backups/annotation-before-phase62-20261021.dump`.
- Before/after count and checksum matched for all existing users, workspaces,
  memberships, projects, images, annotations and classes.
- Browser: Check Email and Verify Email render at a 390×844 mobile viewport with
  no horizontal overflow; fragment removal and invalid-link POST/error confirmed.
  Opening a new email link while verification is already mounted was repaired
  and covered by a regression test.
- A Docker network-only probe to `smtp.gmail.com:587` passed DNS, greeting and
  trusted STARTTLS. It used disposable placeholder configuration, **did not log in
  and did not send any email**.
- Current operator diagnostics report file provider and no credentials configured.
  The ignored local `.env` has blank SMTP credentials for the user to fill privately.
  Actual Gmail authentication, email receipt and inbox-based end-to-end testing
  remain pending real sender configuration. No Gmail delivery is claimed.
