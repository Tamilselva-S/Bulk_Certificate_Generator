# Bulk Certificate Generator

A FastAPI backend that accepts bulk certificate-generation requests, generates a professionally designed PDF for each recipient, tracks per-recipient progress, and serves the files for download.

---

## Table of Contents

1. [Project Purpose and Features](#1-project-purpose-and-features)
2. [Technology Stack](#2-technology-stack)
3. [Architecture and Request-to-Download Flow](#3-architecture-and-request-to-download-flow)
4. [Prerequisites](#4-prerequisites)
5. [Setup Instructions](#5-setup-instructions)
6. [Database Initialisation](#6-database-initialisation)
7. [Starting the Server](#7-starting-the-server)
8. [API Endpoints](#8-api-endpoints)
9. [Example curl Requests](#9-example-curl-requests)
10. [Running Tests](#10-running-tests)
11. [Folder Structure](#11-folder-structure)
12. [Design Decisions and Alternatives](#12-design-decisions-and-alternatives)
13. [Validation and Failure-Handling Policy](#13-validation-and-failure-handling-policy)
14. [Background-Task Limitations](#14-background-task-limitations)
15. [Security Considerations](#15-security-considerations)
16. [Future Scope](#16-future-scope)

---

## 1. Project Purpose and Features

**Purpose:** Accept a list of event recipients in a single API call, generate a personalised PDF certificate for each, and allow the client to track progress and download results.

**Implemented Features:**
- `POST /api/jobs/` – Submit a bulk job with N recipients.
- `GET /api/jobs/{id}` – Poll job status and progress counts.
- `GET /api/jobs/{id}/certificates` – List per-recipient results with download URLs.
- `GET /api/certificates/{id}/download` – Stream a generated PDF.
- `GET /health` – Liveness probe.
- Automatic SQLite database initialisation on first run.
- Professional landscape-A4 PDF layout with decorative border, gold accents, and clear hierarchy.
- Per-recipient failure isolation — one error does not stop other recipients.
- Configurable maximum recipients per request (default 500).

---

## 2. Technology Stack

| Layer | Choice | Reason |
|---|---|---|
| Framework | FastAPI 0.111 | Modern, async-ready, auto-generates OpenAPI docs |
| Database | SQLite | Zero-setup, file-based, sufficient for local/dev |
| ORM | SQLAlchemy 2.0 | Industry standard, type-safe with mapped_column |
| Validation | Pydantic 2 | First-class FastAPI integration, clear error messages |
| PDF | ReportLab | Mature, pure-Python PDF library; no external binaries |
| Server | Uvicorn | ASGI server recommended for FastAPI |
| Tests | Pytest + httpx TestClient | Standard Python testing stack |

---

## 3. Architecture and Request-to-Download Flow

```
Client
  │
  │  POST /api/jobs/  (JSON with event_name, issuer, recipients[])
  ▼
FastAPI Route (app/routes/jobs.py)
  │  1. Pydantic validates the entire request body.
  │  2. Job + Certificate rows written to SQLite.
  │  3. BackgroundTask registered: process_job(job_id)
  │  4. Returns 202 { job_id, status: QUEUED, total }
  │
  ▼ (background, same process)
Job Processor (app/services/job_processor.py)
  │  5. Opens its own DB session.
  │  6. Sets job → PROCESSING.
  │  7. For each Certificate row:
  │       a. Set status → PROCESSING
  │       b. Call generate_certificate_pdf(...)
  │       c. On success: file_path saved, status → SUCCESS
  │       d. On error:   error_message saved, status → FAILED
  │  8. Sets job → COMPLETED / COMPLETED_WITH_ERRORS / FAILED
  │
  ▼
PDF Generator (app/services/generator.py)
  │  Draws landscape A4 canvas with ReportLab.
  │  Saves file to OUTPUT_DIR/{uuid}.pdf.
  │  Verifies file exists before returning.
  │
  ▼ (client polls)
GET /api/jobs/{job_id}         → progress counts
GET /api/jobs/{job_id}/certificates  → list with download URLs
GET /api/certificates/{id}/download  → PDF FileResponse
```

---

## 4. Prerequisites

- **Python 3.11+** (3.10 may work but is not tested)
- **pip** (comes with Python)
- No external databases, message brokers, or runtime services required.

---

## 5. Setup Instructions

### Windows PowerShell

```powershell
# 1. Clone / navigate to the project directory
cd C:\path\to\bulk-certificate-generator

# 2. Create a virtual environment
python -m venv venv

# 3. Activate it
venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -r requirements.txt

# 5. Copy the example environment file
Copy-Item .env.example .env
```

> If you see an execution policy error on step 3, run:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## 6. Database Initialisation

The database is **automatically initialised** when the server starts for the first time. The file `certificates.db` will be created in the project root.

No migration tool or manual setup is required for SQLite. If you add new columns in a future iteration, delete `certificates.db` and restart the server (or use Alembic).

---

## 7. Starting the Server

```bash
uvicorn app.main:app --reload
```

The server will be available at: **http://127.0.0.1:8000**

Interactive API docs (Swagger UI): **http://127.0.0.1:8000/docs**

ReDoc alternative docs: **http://127.0.0.1:8000/redoc**

---

## 8. API Endpoints

### A. Create a Bulk Generation Job

```
POST /api/jobs/
```

**Request Body:**

```json
{
  "event_name": "Python Workshop 2026",
  "issuer": "Agni College of Technology",
  "recipients": [
    { "name": "Arun Kumar",   "email": "arun@example.com"  },
    { "name": "Priya Sharma", "email": "priya@example.com" }
  ]
}
```

**Constraints:**
- `event_name`: 1–200 characters, not blank.
- `issuer`: 1–200 characters, not blank.
- `recipients`: 1–500 items (configurable via `MAX_RECIPIENTS_PER_JOB`).
- Each recipient: `name` 1–200 chars, `email` must be a valid email address.
- An invalid overall request returns **422 Unprocessable Entity**.

**Response (202 Accepted):**

```json
{
  "job_id": "a4f3c2d1-...",
  "status": "QUEUED",
  "total": 2,
  "message": "Certificate generation job created"
}
```

---

### B. Get Job Status and Progress

```
GET /api/jobs/{job_id}
```

**Response (200 OK):**

```json
{
  "job_id": "a4f3c2d1-...",
  "status": "COMPLETED",
  "event_name": "Python Workshop 2026",
  "issuer": "Agni College of Technology",
  "total": 2,
  "processed": 2,
  "successful": 2,
  "failed": 0,
  "progress_pct": 100.0,
  "created_at": "2026-10-09T14:05:00",
  "started_at": "2026-10-09T14:05:00",
  "completed_at": "2026-10-09T14:05:01"
}
```

**Job statuses:** `QUEUED` → `PROCESSING` → `COMPLETED` / `COMPLETED_WITH_ERRORS` / `FAILED`

Returns **404** if `job_id` is unknown.

---

### C. List Per-Recipient Results

```
GET /api/jobs/{job_id}/certificates
```

**Response (200 OK):**

```json
{
  "job_id": "a4f3c2d1-...",
  "total": 2,
  "certificates": [
    {
      "certificate_id": "b5e6d7f8-...",
      "recipient_name": "Arun Kumar",
      "recipient_email": "arun@example.com",
      "status": "SUCCESS",
      "error_message": null,
      "download_url": "http://localhost:8000/api/certificates/b5e6d7f8-.../download"
    },
    {
      "certificate_id": "c9a1b2c3-...",
      "recipient_name": "Priya Sharma",
      "recipient_email": "priya@example.com",
      "status": "SUCCESS",
      "error_message": null,
      "download_url": "http://localhost:8000/api/certificates/c9a1b2c3-.../download"
    }
  ]
}
```

Returns **404** if `job_id` is unknown.

---

### D. Download a Certificate

```
GET /api/certificates/{certificate_id}/download
```

Returns the PDF as a file download (`Content-Type: application/pdf`).

| Condition | HTTP Status |
|---|---|
| Certificate found and successful | **200 OK** + PDF body |
| Certificate ID unknown | **404 Not Found** |
| Certificate exists but not yet successful | **409 Conflict** |

---

### E. Health Check

```
GET /health
```

**Response (200 OK):**

```json
{ "status": "ok", "version": "1.0.0" }
```

---

## 9. Example curl Requests

### Create a job

```bash
curl -X POST http://localhost:8000/api/jobs/ \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Python Workshop 2026",
    "issuer": "Agni College of Technology",
    "recipients": [
      {"name": "Arun Kumar",   "email": "arun@example.com"},
      {"name": "Priya Sharma", "email": "priya@example.com"}
    ]
  }'
```

### Check progress

```bash
curl http://localhost:8000/api/jobs/<job_id>
```

### List results

```bash
curl http://localhost:8000/api/jobs/<job_id>/certificates
```

### Download a certificate

```bash
curl -O -J http://localhost:8000/api/certificates/<certificate_id>/download
```

### Health check

```bash
curl http://localhost:8000/health
```

---

## 10. Running Tests

```bash
# Activate your virtual environment first, then:
pytest -v
```

Tests use an isolated in-memory SQLite database and a temporary output directory. They never touch the production database or generated certificates.

**Expected output (all passing):**

```
tests/test_downloads.py::test_list_certificates_returns_correct_structure  PASSED
tests/test_downloads.py::test_successful_certificate_has_download_url      PASSED
tests/test_downloads.py::test_download_successful_certificate              PASSED
tests/test_downloads.py::test_download_unknown_certificate_returns_404     PASSED
tests/test_downloads.py::test_unknown_job_certificates_returns_404         PASSED
tests/test_downloads.py::test_download_before_success_returns_409          PASSED
tests/test_failures.py::test_one_failure_does_not_stop_others              PASSED
tests/test_failures.py::test_all_failure_job_status_is_failed              PASSED
tests/test_failures.py::test_failed_certificate_has_error_message          PASSED
tests/test_generator.py::test_generates_non_empty_pdf                      PASSED
tests/test_generator.py::test_pdf_has_correct_filename                     PASSED
tests/test_generator.py::test_pdf_starts_with_pdf_magic_bytes              PASSED
tests/test_generator.py::test_different_recipients_get_different_files     PASSED
tests/test_generator.py::test_safe_filename_strips_special_chars           PASSED
tests/test_generator.py::test_truncate_text_no_truncation_needed           PASSED
tests/test_generator.py::test_truncate_text_truncates_long_text            PASSED
tests/test_generator.py::test_output_directory_created_if_missing          PASSED
tests/test_jobs.py::test_create_job_multiple_recipients                    PASSED
tests/test_jobs.py::test_job_status_returns_correct_fields                 PASSED
tests/test_jobs.py::test_job_status_progress_completes                     PASSED
tests/test_jobs.py::test_unknown_job_returns_404                           PASSED
tests/test_progress.py::test_all_success_job_status_is_completed           PASSED
tests/test_progress.py::test_progress_counts_add_up                        PASSED
tests/test_validation.py::test_missing_event_name_returns_422              PASSED
tests/test_validation.py::test_missing_issuer_returns_422                  PASSED
tests/test_validation.py::test_empty_recipients_list_returns_422           PASSED
tests/test_validation.py::test_invalid_email_in_recipient_returns_422      PASSED
tests/test_validation.py::test_blank_recipient_name_returns_422            PASSED
tests/test_validation.py::test_blank_event_name_returns_422                PASSED
tests/test_validation.py::test_too_many_recipients_returns_422             PASSED
```

---

## 11. Folder Structure

```
bulk-certificate-generator/
├── app/
│   ├── __init__.py          # Package marker
│   ├── main.py              # FastAPI app, lifespan, router registration
│   ├── config.py            # All settings from environment variables
│   ├── database.py          # SQLAlchemy engine, session, init_db()
│   ├── models.py            # ORM models: GenerationJob, Certificate
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── jobs.py          # POST /api/jobs/, GET /api/jobs/{id}, GET /api/jobs/{id}/certificates
│   │   └── certificates.py  # GET /api/certificates/{id}/download
│   └── services/
│       ├── __init__.py
│       ├── generator.py     # Pure PDF generation function (no DB, no HTTP)
│       └── job_processor.py # Processing loop, status transitions, error isolation
├── tests/
│   ├── conftest.py          # Shared fixtures: test DB, test client, output dir
│   ├── test_jobs.py         # Job creation and status tests
│   ├── test_validation.py   # Request validation tests
│   ├── test_generator.py    # Unit tests for PDF generator (no HTTP)
│   ├── test_progress.py     # Progress calculation tests
│   ├── test_failures.py     # Failure injection and isolation tests
│   └── test_downloads.py    # Download and listing tests
├── generated_certificates/  # Runtime output (gitignored)
├── .env.example             # Non-secret config template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 12. Design Decisions and Alternatives

### Why SQLite?
SQLite requires zero external services, making the project runnable immediately after cloning. For production, swap `DATABASE_URL` in `.env` to PostgreSQL or MySQL and install the appropriate SQLAlchemy driver.

### Why UUID primary keys?
UUIDs are generated in Python before the INSERT, so the ID is known immediately. This avoids a round-trip to the DB to read back the auto-increment ID.

### Why BackgroundTasks instead of Celery?
Celery requires Redis and significant extra configuration. BackgroundTasks is built into FastAPI and is sufficient for a local-development assessment. See [Section 14](#14-background-task-limitations) for the trade-offs.

### Why store only the filename (not the full path)?
The full output directory path (`OUTPUT_DIR`) is configurable and may change between environments. Storing only the filename makes it portable. The route reconstructs the full path at download time.

### Why 409 (Conflict) instead of 404 for not-yet-ready downloads?
404 means the resource doesn't exist. A 409 means "the resource exists but is in the wrong state for this request", which is more accurate and gives the client a clear signal to retry later.

### Why not Celery/Redis now?
Adding Celery correctly (with a broker, worker process, result backend, and serialisation) would significantly increase setup complexity and make the project harder to explain in an interview. The README and INTERVIEW_PREP document the trade-off honestly.

---

## 13. Validation and Failure-Handling Policy

**Overall request validation:**
- Pydantic validates the entire request body atomically.
- If _any_ field (including any recipient) fails validation, the entire request is rejected with a `422 Unprocessable Entity` containing a detailed error list.
- This is the simplest, most consistent approach. An alternative (accept the batch, mark invalid recipients as FAILED) would require manually parsing the raw JSON and is not implemented.

**Per-recipient PDF failures:**
- Each recipient's PDF generation is wrapped in a `try/except`.
- A crash on one recipient is caught, a safe error message is stored, and the loop continues.
- A single failure does not stop other recipients or fail the overall job (unless all recipients fail).

**Partial success final statuses:**
- All succeed → `COMPLETED`
- Some succeed, some fail → `COMPLETED_WITH_ERRORS`
- All fail → `FAILED`
- Job-level crash (before/after the loop) → `FAILED`

---

## 14. Background-Task Limitations

> **Important:** FastAPI `BackgroundTasks` are not a durable queue.

| Property | BackgroundTasks | Celery + Redis |
|---|---|---|
| Runs in | Same process | Separate worker process(es) |
| Survives server restart | ❌ No | ✅ Yes |
| Scalable across machines | ❌ No | ✅ Yes |
| Setup complexity | Very low | Medium–high |
| Suitable for | Dev/assessment | Production with many jobs |

If the server is restarted while a job is `PROCESSING`, those records will stay in `PROCESSING` forever. A production system should use a durable queue (Celery + Redis, RQ, AWS SQS, Google Cloud Tasks) and implement a job recovery/timeout mechanism.

---

## 15. Security Considerations

- **Path traversal prevention:** Output file paths are built from UUID-based filenames only. When serving files, the resolved path is checked to be inside `OUTPUT_DIR`.
- **No stack traces in responses:** All error messages in API responses are safe, human-readable strings. Internal paths and tracebacks are logged server-side only.
- **No secrets in `.env.example`:** Only non-sensitive defaults are included.
- **No user input used as filesystem paths:** Recipient names/emails are stored in the DB; filenames come from UUIDs.
- **CORS:** Not configured (disabled by default). Enable only if a frontend needs to call this API from a different origin.
- **Authentication:** Not implemented. Add OAuth2/API keys for any non-internal deployment.

---

## 16. Future Scope

The following features are **not implemented** but are reasonable next steps:

- **Persistent job queue:** Replace BackgroundTasks with Celery + Redis.
- **Alembic migrations:** For evolving the schema without dropping the database.
- **Email delivery:** Send each recipient their certificate after generation.
- **Custom templates:** Allow uploading a custom certificate design.
- **Authentication and multi-tenancy:** API keys or OAuth2, per-organisation isolation.
- **Pagination:** Add `limit`/`offset` query parameters to the certificates list endpoint.
- **Admin UI:** A simple web interface for managing jobs.
- **Horizontal scaling:** Deploy workers separately from the API server.
- **Async PDF generation:** Offload blocking PDF work to a thread pool or process pool for better throughput under load.
