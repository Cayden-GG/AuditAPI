# Valvanta Audit API

FastAPI service that runs a full website audit (performance + SEO), generates PDF/JSON reports, optionally uploads them to Google Cloud Storage, and emails results via Brevo. All audits are scheduled through the queue system.

## What This Program Does
- Accepts audit requests via API (target URL + client email) and queues them with tier-based limits.
- Discovers sitemap URLs, runs Lighthouse audits, and formats results.
- Generates PDF reports and JSON outputs in `audit_results/`.
- Uploads reports/logs to GCS (if configured) and stores object names in the database.
- Sends branded client emails with report attachments, plus internal company notifications.
- Supports resending completed audit emails from stored GCS objects.

## Project Structure
- `app/main.py`: FastAPI app setup, middleware, and the audit runner (subprocess dispatch, GCS upload, emails, paid-audit callback).
- `app/routes/`: API routers — `audit.py` (audit + status + resend), `email.py` (generic send), `brevo.py` (newsletter/audit list signup).
- `app/audit_service/`: audit pipeline (discovery, Lighthouse, formatting, AI summaries, PDF reports).
- `app/audit_queue/`: audit queue (validation, dispatch, watchdog).
- `app/emails/`: Brevo integration + HTML templates.
- `app/gcs/`: upload/download helpers for GCS.
- `app/database.py` / `app/models.py`: SQLAlchemy session + Pydantic/ORM models for audits.
- `app/rate_limit.py`: request rate limiting middleware.
- `app/logging_utils.py`: structured JSONL audit logging.
- `app/cleanup.py`: cleanup of old local audit artifacts.
- `storage/`: SQLite database.
- `audit_results/`: runtime output (JSON/PDF).

## Setup
```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables
Required for email:
- `BREVO_API_KEY`
- `BREVO_SENDER_EMAIL`
- `BREVO_SENDER_NAME` (optional, default: Valvanta Digital)
- `BREVO_COMPANY_EMAIL` (optional, for internal notifications)

Required for GCS uploads/downloads:
- `GCS_BUCKET_NAME`
- `GCS_SERVICE_ACCOUNT_JSON` (path to service account JSON)

Required for paid-audit status callbacks:
- `VALVANTA_AUDIT_SECRET_KEY` (sent as the `Authorization` header when POSTing status back to `callback_url`; callback is skipped if unset)

Required for the Brevo list-signup endpoints:
- `BREVO_NEWSLETTER_SIGNUP_LIST_ID` (used by `/api/signupNewsletter`)
- `BREVO_AUDIT_SIGNUP_LIST_ID` (used by `/api/signupAuditList`)

Optional:
- `OPENAI_API_KEY` (for AI summaries)
- `CHROME_PATH` (path to a Chrome/Chromium binary for Lighthouse; auto-detected if unset, the audit fails if none is found)
- `RATE_LIMIT_DISABLED` (set to `1`, `true` or `True` to disable rate limiting, default enabled)
- `RATE_LIMIT_REQUESTS` (max requests per window, default `30`)
- `RATE_LIMIT_WINDOW_SECONDS` (window length in seconds, default `60`)

## Run the API
```
uvicorn app.main:app --reload
```

## Run a Full Audit from CLI
```
python app/audit_service/cli.py \
  --client-name "Acme" \
  --domain-url https://example.com \
  --only-categories seo,performance \
  --max-urls 50
```
Other flags: `--audit-id`, `--output-dir`, `--log-path`, `--debug-mode` (skips paid AI requests).

## API Endpoints
Start a free audit (queued):
```
POST /api/v1/audit
{
  "url": "https://example.com",
  "email": "client@example.com",
  "client_name": "Acme Co"
}
```

Start a paid audit (queued). Field names are camelCase; `socialLinks`, `orderId`, and `callbackUrl` are required — `callbackUrl` receives a status POST (`{"orderId", "status"}`, authenticated with `VALVANTA_AUDIT_SECRET_KEY`) when the audit completes or fails:
```
POST /api/v1/paidAudit
{
  "customerName": "Acme Co",
  "customerEmail": "client@example.com",
  "websiteUrl": "https://example.com",
  "socialLinks": ["https://twitter.com/acme"],
  "orderId": "order_123",
  "callbackUrl": "https://example.com/audit-callback"
}
```

Unified status (job token or audit id):
```
GET /api/v1/status/{identifier}
```

Resend completed audit email (downloads reports from GCS):
```
POST /api/v1/audit/resend
{
  "job_id": "...",
  "to_email": "optional-override@example.com"
}
```
You can also send with `target_url` instead of `job_id`.

Send a generic email (used internally, e.g. for one-off notifications):
```
POST /api/sendEmail
{
  "to_email": "client@example.com",
  "send_email": "sender@valvanta.com",
  "subject_line": "Subject",
  "html_content": "<p>Hello</p>",
  "attachments": "optional/path/one.pdf,optional/path/two.pdf"
}
```

Sign up a contact to the newsletter list (requires `BREVO_NEWSLETTER_SIGNUP_LIST_ID`):
```
POST /api/signupNewsletter
{
  "name": "Jane Doe",
  "email": "jane@example.com"
}
```

Sign up a contact to the audit list (requires `BREVO_AUDIT_SIGNUP_LIST_ID`):
```
POST /api/signupAuditList
{
  "name": "Jane Doe",
  "email": "jane@example.com"
}
```

## Email Template Testing
Send all templates to a test inbox:
```
python -m app.emails.send_test_emails --to-email you@example.com
```

## Tests
```
pytest
```

## Notes
- `audit_results/` and credentials should not be committed.
- Resend relies on stored GCS object names in the database.
- Reports upload to `audits/free/{audit_id}` or `audits/paid/{audit_id}` in the configured GCS bucket.
- Requests are rate-limited by default; see `RATE_LIMIT_*` env vars above.

## Tiers
- Free: max 5 URLs, performance + SEO reports, client + company emails.
- Paid: max 100 URLs, performance + SEO + accessibility reports, company email only (plus an optional status callback to `callbackUrl`).
