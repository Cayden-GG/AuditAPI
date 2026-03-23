# Audit Queue Specification

## Overview

The audit queue manages the execution of website audit jobs submitted by customers. It enforces concurrency limits, tier-based priority rules, duplicate rejection, rate limiting, and timeout handling. A maximum of 2 audits run simultaneously with specific constraints on paid vs free tier mixing.

---

## Tiers

| Tier | Max URLs | Approx. Runtime |
|------|----------|-----------------|
| Free | 5 | 8–15 min |
| Paid | 100 | Up to 90 min |

---

## Concurrency Rules

- Maximum **2 audits running simultaneously** at any time.
- Maximum **1 paid audit running** at any time.
- **2 free audits** may run concurrently.
- If a paid audit is running, the second slot becomes **free-only** until the paid audit completes.

---

## Priority & Skip Logic

Free audits have queue priority over paid audits, but a paid audit cannot be skipped indefinitely.

### Skip counter

- Each paid job in the queue tracks its own independent `skip_count`.
- The counter increments **only for free jobs that joined the queue after the paid job**. Free jobs already ahead of it when it was submitted do not count.
- When a free job is promoted ahead of one or more waiting paid jobs, every paid job with a `queued_at` timestamp earlier than the free job gets its `skip_count` incremented by 1.
- Once a paid job reaches `skip_count >= 5`, it is promoted to the front of the selection order.

### Slot selection order (runs every time a slot frees up)

1. **Paid job with `skip_count >= 5`** — oldest first (FIFO among tied paid jobs).
2. **Next free job in queue** — FIFO.
3. **Next paid job in queue** — FIFO, and **only** if the freed slot is the paid slot (i.e. no paid audit is currently running).

If the freed slot is a free-only slot (because a free audit finished while a paid audit is still running), only steps 1 and 2 are eligible — a paid job cannot be started into that slot.

---

## Submission Validation

All checks run atomically within a single SQLite transaction before a job is accepted.

### Free tier — reject if any of the following are true

- The submitting customer already has a job with `status IN ('queued', 'running')`.
- The submitted domain already has a job with `status IN ('queued', 'running')` and `tier = 'free'`.
- The submitted domain has a job with `status = 'completed'` and `tier = 'free'` (1 free audit per domain, ever, globally — no auth required).
- The number of submitted URLs exceeds 5.

### Paid tier — reject if any of the following are true

- The submitting customer already has a job with `status IN ('queued', 'running')`.
- The submitted domain already has a job with `status IN ('queued', 'running')` and `tier = 'paid'`.
- The number of submitted URLs exceeds 100.

### Notes

- Free and paid tiers are checked **independently**. A completed free audit on a domain does not block a paid submission for the same domain, and vice versa.
- Jobs with `status = 'timeout'` or `status = 'failed'` do **not** block resubmission for either tier.
- Only `status = 'completed'` counts as a block for the free tier duplicate check.

---

## Rate Limiting

| Rule | Scope |
|------|-------|
| 1 active job at a time (queued or running) | Per customer |
| 1 free audit per domain ever | Global (domain-level, no auth required) |
| Paid audits per domain | Unlimited over time |

---

## Timeouts

- **Free audit hard timeout:** 30 minutes from `started_at`.
- **Paid audit hard timeout:** 90 minutes from `started_at`.
- `timeout_at` is calculated and stored when the job transitions to `running`: `started_at + timeout_duration`.
- A **watchdog process polls every 60 seconds** for jobs where `status = 'running'` and `timeout_at < now`. On detection, it sets `status = 'timeout'`, records `completed_at`, frees the slot, and triggers the next job selection.
- Timed-out jobs do not block resubmission.

---

## Job Status Lifecycle

```
queued → running → completed
                 → failed
                 → timeout
```

| Status | Description |
|--------|-------------|
| `queued` | Accepted and waiting in queue |
| `running` | Actively being audited |
| `completed` | Audit finished successfully; report available |
| `failed` | Audit process errored out |
| `timeout` | Audit exceeded the hard time limit |

Both `failed` and `timeout` free the runner slot immediately and trigger the next job selection.

---

## Customer-Facing Status

There is no live queue visibility. Customers click a button to poll the status of their job using the `job_token` returned at submission time.

| Job status | Message shown |
|------------|---------------|
| `running` | "Auditing your site now" |
| `queued` | "Estimated wait: X minutes" |
| `completed` | Link to the audit report |
| `failed` or `timeout` | Error message with option to resubmit |

### Estimated wait formula

```
estimated_minutes = floor(pos_in_q × 10 / 1.5)
```

- `pos_in_q` is the **raw queue position** — the count of all jobs ahead of this one regardless of tier.
- The `/ 1.5` divisor accounts for the mixed-slot dynamics (paid audits occupying one of the two slots some of the time).
- The result is presented as a rough estimate; no exact position is shown to the customer.

---

## SQLite Schema

### `customers`

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PRIMARY KEY | External user identifier |
| `tier` | TEXT NOT NULL | `'free'` or `'paid'` |
| `created_at` | INTEGER | Unix epoch ms |

### `audit_jobs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Internal job ID |
| `job_token` | TEXT NOT NULL UNIQUE | Returned to customer at submission; used for status polling |
| `customer_id` | TEXT NOT NULL | FK → customers.id |
| `domain` | TEXT NOT NULL | Normalised domain, no trailing slash |
| `tier` | TEXT NOT NULL | `'free'` or `'paid'` |
| `urls` | TEXT NOT NULL | JSON array of URLs; max 5 (free) or 100 (paid) |
| `status` | TEXT NOT NULL | `queued`, `running`, `completed`, `failed`, `timeout` |
| `skip_count` | INTEGER DEFAULT 0 | Paid jobs only; tracks how many free jobs have jumped ahead |
| `queued_at` | INTEGER NOT NULL | Unix epoch ms — set on insert |
| `started_at` | INTEGER | Unix epoch ms — set when job transitions to `running` |
| `completed_at` | INTEGER | Unix epoch ms — set on `completed`, `failed`, or `timeout` |
| `timeout_at` | INTEGER | Unix epoch ms — set on start: `started_at + timeout_ms` |
| `result_path` | TEXT | Filesystem path to the completed report; null until `completed` |

### `runner_slots`

Seeded with exactly 2 rows at initialisation and never modified structurally.

| Column | Type | Notes |
|--------|------|-------|
| `slot_id` | INTEGER PRIMARY KEY | `1` or `2` |
| `job_id` | INTEGER | FK → audit_jobs.id; `NULL` when slot is free |

Slot type (`'any'` vs `'free_only'`) is **derived at runtime**, not stored. If a paid audit is currently running (any slot's `job_id` points to a paid job), the other slot is treated as free-only during selection.

### Indexes

```sql
CREATE INDEX idx_jobs_status_tier   ON audit_jobs (status, tier, queued_at);
CREATE INDEX idx_jobs_customer      ON audit_jobs (customer_id, status);
CREATE INDEX idx_jobs_domain_tier   ON audit_jobs (domain, tier, status);
CREATE INDEX idx_jobs_timeout       ON audit_jobs (status, timeout_at);  -- watchdog query
```

---

## Core Queries

### Submission validation (run in a single transaction)

```sql
-- 1. Rate limit: customer already has an active job?
SELECT id FROM audit_jobs
WHERE customer_id = ? AND status IN ('queued', 'running');

-- 2. Duplicate domain active for same tier?
SELECT id FROM audit_jobs
WHERE domain = ? AND tier = ? AND status IN ('queued', 'running');

-- 3. Free tier only — completed audit exists for this domain?
SELECT id FROM audit_jobs
WHERE domain = ? AND tier = 'free' AND status = 'completed';
```

### Priority selection (runs each time a slot frees)

```sql
-- Step 1: paid job at skip limit
SELECT * FROM audit_jobs
WHERE status = 'queued' AND tier = 'paid' AND skip_count >= 5
ORDER BY queued_at ASC LIMIT 1;

-- Step 2: next free job
SELECT * FROM audit_jobs
WHERE status = 'queued' AND tier = 'free'
ORDER BY queued_at ASC LIMIT 1;

-- Step 3: next paid job (only if paid slot is available)
SELECT * FROM audit_jobs
WHERE status = 'queued' AND tier = 'paid'
ORDER BY queued_at ASC LIMIT 1;
```

### Skip counter increment (run when a free job is promoted)

```sql
UPDATE audit_jobs
SET skip_count = skip_count + 1
WHERE status = 'queued'
  AND tier = 'paid'
  AND queued_at < ?;  -- ? = queued_at of the free job being promoted
```

### Watchdog timeout check (runs every 60 seconds)

```sql
UPDATE audit_jobs
SET status = 'timeout',
    completed_at = unixepoch('subsec') * 1000
WHERE status = 'running'
  AND timeout_at < unixepoch('subsec') * 1000;
-- After this UPDATE: free the affected slot(s) and trigger next job selection
```

### Customer status poll

```sql
SELECT status, queued_at, started_at, result_path,
  (SELECT COUNT(*) FROM audit_jobs q2
   WHERE q2.status = 'queued' AND q2.queued_at < q1.queued_at) AS pos_in_q
FROM audit_jobs q1
WHERE job_token = ?;
```

---

## Job Token

A short opaque token (e.g. a hex-encoded random 8 bytes) is generated at submission and returned to the customer. It is the only identifier the customer holds and is used for all subsequent status poll requests. No session, cookie, or login is required.

---

## Component Responsibilities Summary

| Component | Responsibility |
|-----------|----------------|
| **Submission endpoint** | Validate inputs, run duplicate/rate-limit checks, insert job, return `job_token` |
| **Queue manager** | On slot free: run priority selection, increment skip counters, start next job, update `runner_slots` |
| **Audit runner** | Execute audit process, write report to disk, update job status on completion or error |
| **Watchdog** | Poll every 60s for timed-out jobs, mark them `timeout`, free slots, trigger queue manager |
| **Status endpoint** | Accept `job_token`, query `audit_jobs`, return formatted status and estimated wait |
