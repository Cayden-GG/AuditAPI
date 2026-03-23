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
- `app/main.py`: FastAPI app, queue-backed endpoints, and audit runner.
- `app/audit_service/`: audit pipeline (discovery, Lighthouse, formatting, AI summaries, PDF reports).
- `app/audit_queue/`: audit queue (validation, dispatch, watchdog).
- `app/emails/`: Brevo integration + HTML templates.
- `app/gcs/`: upload/download helpers for GCS.
- `storage/`: SQLite database.
- `audit_results/`: runtime output (JSON/PDF).

## Setup
```
python -m venv venv
source venv/bin/activate
pip install -r app/services/full_website_performance_audit.egg-info/requires.txt
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

Optional:
- `OPENAI_API_KEY` (for AI summaries)
- `AUDIT_QUEUE_WORKER` (set to `0` to disable the in-process queue worker)

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
  --platform desktop \
  --max-urls 50
```

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

Start a paid audit (queued):
```
POST /api/v1/paidAudit
{
  "url": "https://example.com",
  "email": "client@example.com",
  "client_name": "Acme Co"
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

## Tiers
- Free: max 5 URLs, performance + SEO reports, client + company emails.
- Paid: max 100 URLs, performance + SEO + accessibility reports, company email only.
