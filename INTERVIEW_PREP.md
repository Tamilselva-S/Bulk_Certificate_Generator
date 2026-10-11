# Interview Preparation Guide — Bulk Certificate Generator

> This guide is written in plain English so you can understand and explain the project in your own words. **Do not memorise answers — understand them.**

---

## 1. Your 60–90 Second Project Introduction

> Practice saying this out loud until it flows naturally.

"I built a backend API using Python and FastAPI that lets an organisation generate PDF certificates in bulk. You send one HTTP request with a list of recipients, and the server creates a personalised PDF certificate for each person. The certificates include the recipient's name, event name, issuer, date, and a unique ID.

The key features are: the server tracks the status of each individual certificate, so if one person's PDF fails to generate, the others still succeed. You can poll the API to see progress in real time, and once a certificate is ready, you can download it directly.

I used SQLite to store job and certificate records, SQLAlchemy as the ORM, ReportLab to draw the PDF, and Pytest for automated testing. The project has 30 tests covering creation, validation, failure isolation, progress tracking, and downloads."

---

## 2. Architecture Explanation

Think of the system in four layers:

```
Client (curl / browser / frontend)
    │
    ▼
Routes (HTTP handlers in app/routes/)
    │  - Validate request data
    │  - Write to database
    │  - Schedule background work
    ▼
Services (app/services/)
    │  - job_processor.py: loops over recipients, updates statuses
    │  - generator.py: draws and saves the PDF (no DB access)
    ▼
Database (SQLite via SQLAlchemy)
    - GenerationJob table
    - Certificate table (one row per recipient)
```

The **routes layer** handles HTTP — it should be thin. The **services layer** contains the real business logic. The **generator** is a pure function that knows nothing about HTTP or databases.

---

## 3. Request Lifecycle (From Request to Download)

1. **Client sends POST /api/jobs/** with event name, issuer, and recipient list.
2. **Pydantic** validates the entire request body. If anything is wrong, a 422 error is returned immediately.
3. A **GenerationJob** row is inserted into the database with status `QUEUED`.
4. One **Certificate** row is inserted for every recipient, each with status `PENDING`.
5. The route **commits** the database records, then schedules a `BackgroundTask`.
6. The route **returns 202** immediately with the `job_id`.
7. In the background, `process_job()` runs:
   - Sets job status to `PROCESSING`.
   - For each Certificate: sets status to `PROCESSING`, calls `generate_certificate_pdf()`, then sets status to `SUCCESS` or `FAILED`.
8. When all recipients are done, the job status is set to `COMPLETED`, `COMPLETED_WITH_ERRORS`, or `FAILED`.
9. **Client polls** `GET /api/jobs/{id}` to check progress.
10. **Client fetches** `GET /api/jobs/{id}/certificates` to get download URLs.
11. **Client calls** `GET /api/certificates/{id}/download` to receive the PDF.

---

## 4. Explanation of Each Module/File

| File | What it does |
|---|---|
| `app/main.py` | Creates the FastAPI app, registers routes, runs startup tasks (init DB, create output dir). |
| `app/config.py` | Reads environment variables (from `.env`) into a `settings` object. One place for all tuneable values. |
| `app/database.py` | Sets up the SQLAlchemy engine and `SessionLocal` factory. `get_db()` is the dependency that routes use to get a database session. `init_db()` creates the tables on first run. |
| `app/models.py` | Defines the database table structure as Python classes (`GenerationJob`, `Certificate`). SQLAlchemy converts these to SQL. |
| `app/schemas.py` | Defines what the API accepts (`JobCreateRequest`, `RecipientIn`) and what it returns (`JobCreateResponse`, `JobStatusResponse`, etc.). Pydantic enforces types and constraints. |
| `app/routes/jobs.py` | Handles POST /api/jobs/, GET /api/jobs/{id}, GET /api/jobs/{id}/certificates. |
| `app/routes/certificates.py` | Handles GET /api/certificates/{id}/download. Includes path safety checks. |
| `app/services/generator.py` | A pure function that uses ReportLab to draw a certificate and save it as a PDF. Has no database access and no HTTP knowledge. |
| `app/services/job_processor.py` | The processing loop. Iterates over recipients, calls the generator, updates statuses, handles per-recipient exceptions. |
| `tests/conftest.py` | Shared test setup: creates a temporary test database and overrides the app's database dependency so tests use isolated data. |

---

## 5. Database Relationship Explanation

```
GenerationJob (one job)
    │
    │  1 ───── N
    ▼
Certificate (many recipients per job)
```

- One job can have many certificates (one-to-many relationship).
- `Certificate.job_id` is a foreign key pointing to `GenerationJob.id`.
- When you query job progress, you count the Certificate rows — you don't store counters on the job itself.

**Why UUID primary keys instead of auto-increment integers?**
UUIDs are generated in Python before the INSERT, so the ID is known immediately. With auto-increment, you need to read back the assigned ID after the INSERT. UUIDs also don't reveal how many records exist in the system.

---

## 6. Why These Technology Choices?

### FastAPI
- Modern Python web framework with automatic request validation (via Pydantic) and automatic API documentation (Swagger at `/docs`).
- Much less boilerplate than Flask for building APIs with strict schemas.
- Built-in support for async, dependency injection, and background tasks.

### SQLite
- Zero setup — it's a single file. No database server to install or configure.
- Perfect for local development and assessments.
- SQLAlchemy makes it easy to switch to PostgreSQL later by just changing `DATABASE_URL`.

### SQLAlchemy
- Industry-standard ORM for Python. Lets you write Python classes instead of raw SQL.
- Handles connection pooling, transaction management, and query building.
- Works with SQLite, PostgreSQL, MySQL, and others.

### ReportLab
- The most mature, well-documented, pure-Python PDF library.
- No external binaries needed (unlike tools that wrap wkhtmltopdf or Chrome).
- The canvas API gives precise control over layout.

---

## 7. How Validation Works

**Two levels:**

1. **Overall request validation (Pydantic):**
   When a POST request arrives, FastAPI passes the JSON body to `JobCreateRequest`. Pydantic checks every field — types, lengths, email format. If anything fails, FastAPI returns a 422 error automatically with a list of exactly what was wrong and where.

2. **Maximum recipient limit:**
   Pydantic schemas don't know about `settings.MAX_RECIPIENTS_PER_JOB` (which is runtime config), so this check is done manually in the route after Pydantic validates the shape.

**What is NOT validated per-recipient at the route level:**
Individual email or name problems cause a 422 for the *entire* request. The project documents this clearly. An alternative design would accept a raw list, validate each item manually, and mark invalid recipients as FAILED — this would be more complex to implement.

---

## 8. How Job Progress Is Calculated

Progress is never stored as a counter on the `GenerationJob` row. Instead, it is calculated on-the-fly from the actual `Certificate` rows:

```python
total = len(all_certs)
successful = count of certs where status == "SUCCESS"
failed     = count of certs where status == "FAILED"
processed  = successful + failed   # certificates in a terminal state
progress_pct = (processed / total) * 100
```

**Why not store counters?** Because counters can get out of sync with the actual data if the background task crashes mid-way. Deriving counts from the actual row states is always accurate.

---

## 9. How One Certificate Failure Is Isolated

In `job_processor.py`, the processing loop looks like this (simplified):

```python
for cert in certificates:
    try:
        cert.status = "PROCESSING"
        db.commit()
        path = generate_certificate_pdf(...)
        cert.file_path = path.name
        cert.status = "SUCCESS"
    except Exception as exc:
        cert.status = "FAILED"
        cert.error_message = safe_error_message(exc)
    finally:
        db.commit()
# loop continues to next recipient regardless
```

The `try/except` catches **any** exception from the generator. The `finally` block commits the status (SUCCESS or FAILED) and then the loop moves to the next recipient. The other recipients are unaffected.

---

## 10. Why In-Process Background Tasks Are Not Durable

FastAPI `BackgroundTasks` run inside the same Python process as the web server. This means:

- **No persistence:** If the server crashes or is restarted while a job is `PROCESSING`, the background function is lost. The job is left stuck in `PROCESSING` forever.
- **No retry:** There is no built-in retry mechanism if the task fails.
- **No scaling:** You cannot run the background work on a different machine.

For production, you would use **Celery + Redis** (or a similar durable queue):
- The job request is persisted to Redis/a database.
- A separate worker process picks it up and runs it.
- If the worker crashes, the job can be retried or recovered.
- Multiple workers can run in parallel on different machines.

---

## 11. What Would Change for Thousands or Millions of Recipients?

| Concern | Current (SQLite + BackgroundTasks) | Production solution |
|---|---|---|
| Queue durability | Tasks lost on restart | Celery + Redis / AWS SQS |
| PDF generation speed | Sequential, single-threaded | Parallel workers, process pool |
| Database | SQLite (single file, no concurrency) | PostgreSQL with connection pooling |
| Storage | Local filesystem | Cloud storage (S3, GCS) |
| Download serving | FastAPI FileResponse | CDN or pre-signed URLs |
| Monitoring | Server logs | Structured logging + metrics (Prometheus, Grafana) |
| Error recovery | Manual | Automatic retry with backoff |

---

## 12. At Least 15 Likely Interview Questions

**Q1: What does FastAPI return if Pydantic validation fails?**
A: A 422 Unprocessable Entity response with a JSON body listing every validation error, including the field name, location, and a human-readable message.

**Q2: Why do you use BackgroundTasks instead of just processing synchronously?**
A: If PDF generation for 500 recipients takes 30 seconds, a synchronous request would keep the HTTP connection open for 30 seconds. BackgroundTasks lets the route return immediately with the job ID, and the client can poll for progress.

**Q3: What happens if the server restarts while a job is running?**
A: The BackgroundTask is lost. The job stays in `PROCESSING` state in the database. The correct production fix is to use a durable queue like Celery that persists jobs externally.

**Q4: Why does the download endpoint return 409 instead of 404 for a not-yet-complete certificate?**
A: 404 means "resource not found". The certificate *does* exist — it just hasn't succeeded yet. 409 Conflict means "the resource exists but is in the wrong state for this operation", which tells the client to retry later rather than to stop trying.

**Q5: Why are PDFs stored by UUID filename, not by recipient name?**
A: Two reasons: (1) security — user-supplied names could contain path-traversal characters like `../`; (2) uniqueness — two recipients could have the same name.

**Q6: What is the difference between `session.flush()` and `session.commit()`?**
A: `flush()` sends pending SQL statements to the database but does not end the transaction — changes can still be rolled back. `commit()` ends the transaction and makes changes permanent. We use `flush()` after adding the job to get the `job.id` assigned without committing yet, so we can use it for the Certificate foreign key in the same transaction.

**Q7: Why does `process_job` create its own database session instead of using the route's session?**
A: The route's session is closed when the HTTP request ends. `process_job` runs in a background task that starts *after* the response is sent. Using the closed session would cause errors. Background work must always create its own session.

**Q8: How does the path traversal guard work in the download route?**
A: We join `OUTPUT_DIR` with the stored filename, then call `.resolve()` on both. `resolve()` converts to an absolute, normalised path (resolving any `..` segments). We then check that the resolved file path starts with the resolved `OUTPUT_DIR` string. If it doesn't, we reject the request.

**Q9: How are timestamps stored and what timezone?**
A: All timestamps are Python `datetime` objects stored in SQLite as text. They represent UTC time (timezone-naive by convention, documented in `models.py`). Clients should apply their local timezone offset when displaying times.

**Q10: What does `from_attributes = True` mean in the Pydantic model config?**
A: It tells Pydantic that it can read attributes from Python objects (like SQLAlchemy model instances) instead of only from plain dicts. Without it, you can't do `MySchema.model_validate(orm_object)`.

**Q11: What is the purpose of `conftest.py` in tests?**
A: It defines shared pytest fixtures. Any fixture defined in `conftest.py` is automatically available to all test files in the same directory and subdirectories without needing to import it.

**Q12: Why did you choose ReportLab over other PDF libraries?**
A: ReportLab is pure Python (no external binaries), mature, well-documented, and gives precise canvas-level control for custom layouts. Alternatives like WeasyPrint require a browser engine, and PDFKit requires wkhtmltopdf — both need external dependencies that complicate deployment.

**Q13: What would you use instead of SQLite in production?**
A: PostgreSQL. It handles concurrent writes properly, supports proper indexing, has mature connection pooling (with PgBouncer), and is widely available on cloud platforms. Changing it requires only updating `DATABASE_URL` — SQLAlchemy abstracts the difference.

**Q14: How do you ensure that test data does not pollute the production database?**
A: The `conftest.py` creates a completely separate SQLite database in a temporary directory for the test session. The app's `get_db` dependency is overridden via `app.dependency_overrides` to use the test session factory instead of the production one.

**Q15: What is the difference between `COMPLETED` and `COMPLETED_WITH_ERRORS`?**
A: `COMPLETED` means every recipient's certificate was generated successfully. `COMPLETED_WITH_ERRORS` means the job finished processing all recipients, but at least one failed. `FAILED` (job-level) means the job could not complete at all — for example, the job row was missing from the database, or a crash happened outside the recipient loop.

---

## 13. Five Realistic Change Requests and How to Handle Them

### Change 1: "Add pagination to the certificate list endpoint"
**File to modify:** `app/routes/jobs.py` (the `list_certificates` route)
**What to do:** Add `limit: int = 100` and `offset: int = 0` query parameters. Use `.offset(offset).limit(limit)` on the SQLAlchemy query. Update `CertificateListResponse` in `schemas.py` to include `limit`, `offset`, and `total_count`.

---

### Change 2: "Store the issue date on the Certificate record"
**Files to modify:** `app/models.py` (add `issue_date` column), `app/schemas.py` (add to response), `app/services/job_processor.py` (save `today` to the cert record).

---

### Change 3: "Support a custom certificate template per event"
**Files to modify:** Add a `template_name` field to `JobCreateRequest` (schemas.py) and `GenerationJob` (models.py). In `generator.py`, add a `template_name` parameter and branch the drawing logic based on it.

---

### Change 4: "Limit the API to authenticated users only"
**Files to modify:** `app/main.py` (add a middleware or dependency), add a new dependency function (e.g., `get_current_user`) and apply it to the router or individual routes. Use FastAPI's `Depends()` pattern — no route logic changes needed if you add it at the router level.

---

### Change 5: "Send an email to each recipient after their certificate is generated"
**Files to modify:** `app/services/job_processor.py` — after setting `cert.status = SUCCESS`, call an email service function. Create `app/services/email_service.py` with a `send_certificate_email(to, cert_path)` function. Add `smtplib` or an email SDK dependency. Add SMTP config to `config.py`.

---

## 14. Debugging Walkthrough — A Failed Certificate

**Scenario:** A user reports that their certificate shows `FAILED` in the list.

**Step 1:** Call `GET /api/jobs/{job_id}/certificates` and find the failed certificate.
```json
{
  "certificate_id": "abc-123",
  "status": "FAILED",
  "error_message": "Something went wrong with the PDF"
}
```

**Step 2:** Look at the `error_message`. It is intentionally sanitised (file paths stripped), but it should point to the general problem.

**Step 3:** Check the **server logs** (`stderr`/stdout of Uvicorn). The full error (including stack trace) is logged at `WARNING` level in `job_processor.py`:
```
WARNING  app.services.job_processor  Certificate abc-123 failed for recipient failme@example.com: ...
```

**Step 4:** Identify the cause from the stack trace in the log. Common causes:
- Disk full (OSError writing the PDF).
- Font or resource file missing (ReportLab error).
- Output directory permissions issue.
- A bug introduced in `generator.py`.

**Step 5:** Fix the underlying issue, then decide: can you re-process just that certificate? (Not implemented — a future feature would allow retrying individual failed certificates.)

**Step 6:** For a quick fix in dev, you can delete the job and re-submit it.

---

## 15. What I Should Never Claim Unless I Implemented It

This section is about honesty in interviews. Only claim credit for what is actually in the code.

**Do NOT claim:**
- "The system sends emails" — no email delivery is implemented.
- "This scales to millions of users" — BackgroundTasks does not scale horizontally.
- "Jobs are retried automatically on failure" — no retry logic exists.
- "The API is secured with authentication" — no auth is implemented.
- "I used Celery for distributed processing" — Celery is not in this project.
- "The system uses a custom template per event" — one hard-coded template exists.
- "Data is paginated" — the certificate list returns all records without pagination.
- "I used Alembic for database migrations" — `create_all()` is used, not Alembic.

**What you CAN honestly claim:**
- "I built a REST API with FastAPI that handles bulk PDF generation."
- "I implemented per-recipient failure isolation so one failure doesn't stop others."
- "I used SQLAlchemy ORM with SQLite and wrote automated tests with Pytest."
- "I used ReportLab to generate PDF certificates."
- "I documented the trade-offs of BackgroundTasks vs. a durable queue."
- "I validated user input with Pydantic and returned appropriate HTTP status codes."
- "I wrote 30 automated tests covering creation, validation, failures, progress, and downloads."

---

## Summary of Key Concepts to Review Before the Interview

1. **HTTP status codes** — 200, 202, 404, 409, 422, 500 and when to use each.
2. **FastAPI dependency injection** — how `Depends(get_db)` works.
3. **SQLAlchemy sessions** — commit, flush, rollback, and session scoping.
4. **Pydantic v2** — model_config, field_validator, EmailStr.
5. **Python context managers** — `with` and `yield` in dependencies.
6. **UUID generation** — why UUIDs over auto-increment for this use case.
7. **Background tasks vs. task queues** — the durability trade-off.
8. **Path traversal** — what it is and how to prevent it.
9. **pytest fixtures** — conftest.py, scope, and dependency_overrides.
10. **ReportLab canvas API** — basic drawing operations.
