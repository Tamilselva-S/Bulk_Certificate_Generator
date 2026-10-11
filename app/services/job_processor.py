"""
app/services/job_processor.py

Contains the core logic that processes a certificate generation job:
  - Iterates over each recipient.
  - Updates statuses in the database.
  - Calls the PDF generator.
  - Catches per-recipient failures without stopping other recipients.

Design decisions
────────────────
1. Separate from routes
   This module knows nothing about HTTP or FastAPI.  It only works with
   plain Python types, SQLAlchemy sessions, and the generator module.
   This separation makes it easy to test directly without spinning up
   the HTTP layer (see tests/test_failures.py).

2. Own database session
   The function creates its own SessionLocal() because it runs inside a
   FastAPI BackgroundTask — which executes *after* the route's request
   session is closed.  Reusing the route's session would cause errors.

3. Per-recipient exception isolation
   Each recipient is wrapped in its own try/except block.  A crash
   generating one PDF does not abort the loop.  The error message stored
   in the database is a safe, readable string — not a raw Python
   traceback that might expose sensitive paths.

4. Status transitions
   Job:         QUEUED → PROCESSING → COMPLETED / COMPLETED_WITH_ERRORS / FAILED
   Certificate: PENDING → PROCESSING → SUCCESS / FAILED

5. Transaction scoping
   Each status update is committed immediately so that polling clients
   see real-time progress even before the job finishes.

IMPORTANT LIMITATION — BackgroundTasks
───────────────────────────────────────
FastAPI BackgroundTasks run in the same process as the web server.
If the server restarts while a job is being processed:
  - In-flight jobs will be stuck in PROCESSING state.
  - No automatic retry occurs.

For production use with many jobs or high reliability requirements,
replace BackgroundTasks with a durable worker queue such as:
  - Celery + Redis (most common Python choice)
  - RQ (simpler, Redis-backed)
  - Dramatiq
  - Cloud-native queues (AWS SQS, Google Cloud Tasks, etc.)

These systems persist job state externally so workers can be restarted
without losing work.
"""

import logging
from datetime import date, timezone, datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Certificate, CertificateStatus, GenerationJob, JobStatus
from app.services.generator import generate_certificate_pdf

logger = logging.getLogger(__name__)


def process_job(job_id: str) -> None:
    """
    Process all certificates for the given job.

    This function is called by a FastAPI BackgroundTask immediately after
    the job record and all Certificate records have been committed to the
    database.  It creates its own database session.

    The function is deliberately NOT async.  FastAPI runs synchronous
    background tasks in a thread pool, which is fine for CPU-bound PDF
    generation.
    """
    db: Session = SessionLocal()
    try:
        _run_job(db, job_id)
    except Exception as exc:
        # Job-level failure: something went wrong before/after the recipient
        # loop (e.g. the job record itself could not be loaded).
        logger.error("Unexpected error processing job %s: %s", job_id, exc)
        _mark_job_failed(db, job_id, str(exc))
    finally:
        db.close()


# ── Internal implementation ───────────────────────────────────────────────────

def _run_job(db: Session, job_id: str) -> None:
    """Core processing loop (called inside process_job with error handling)."""

    # Load job.
    job: GenerationJob | None = db.get(GenerationJob, job_id)
    if job is None:
        raise RuntimeError(f"Job {job_id} not found in database.")

    # Transition job to PROCESSING.
    job.status = JobStatus.PROCESSING
    job.started_at = _utcnow()
    db.commit()

    # Load all pending recipient records for this job.
    certificates: list[Certificate] = (
        db.query(Certificate)
        .filter(Certificate.job_id == job_id)
        .all()
    )

    today = date.today()  # Used as the issue date on every certificate in this job.

    for cert in certificates:
        _process_one_certificate(db, cert, job, today)

    # ── Determine final job status ────────────────────────────────────────────
    # Reload counts from DB to get the authoritative tallies.
    db.refresh(job)
    all_certs = (
        db.query(Certificate).filter(Certificate.job_id == job_id).all()
    )
    success_count = sum(1 for c in all_certs if c.status == CertificateStatus.SUCCESS)
    failed_count = sum(1 for c in all_certs if c.status == CertificateStatus.FAILED)
    total = len(all_certs)

    if failed_count == 0:
        job.status = JobStatus.COMPLETED
    elif success_count == 0:
        # Every recipient failed — treat as full failure.
        job.status = JobStatus.FAILED
    else:
        job.status = JobStatus.COMPLETED_WITH_ERRORS

    job.completed_at = _utcnow()
    db.commit()
    logger.info(
        "Job %s finished. status=%s success=%d failed=%d total=%d",
        job_id,
        job.status,
        success_count,
        failed_count,
        total,
    )


def _process_one_certificate(
    db: Session,
    cert: Certificate,
    job: GenerationJob,
    today: date,
) -> None:
    """
    Attempt to generate the PDF for one recipient.

    Any exception is caught; the certificate is marked FAILED with a
    safe error message and processing continues.
    """
    # Mark as PROCESSING.
    cert.status = CertificateStatus.PROCESSING
    db.commit()

    try:
        output_path = generate_certificate_pdf(
            certificate_id=cert.id,
            recipient_name=cert.recipient_name,
            event_name=job.event_name,
            issuer=job.issuer,
            issue_date=today,
            output_dir=settings.OUTPUT_DIR,
        )

        # Store the filename only (relative to OUTPUT_DIR), not the absolute path.
        cert.file_path = output_path.name
        cert.status = CertificateStatus.SUCCESS
        logger.info("Certificate %s generated successfully.", cert.id)

    except Exception as exc:
        # Catch everything so other recipients are not affected.
        safe_msg = _safe_error_message(exc)
        cert.status = CertificateStatus.FAILED
        cert.error_message = safe_msg
        logger.warning(
            "Certificate %s failed for recipient %s: %s",
            cert.id,
            cert.recipient_email,  # email is less sensitive than full path
            safe_msg,
        )

    finally:
        # Always commit so the status is visible to polling clients.
        db.commit()


def _mark_job_failed(db: Session, job_id: str, reason: str) -> None:
    """
    Mark a job as FAILED at the job level.

    Called only when an unexpected error happens outside the recipient
    loop (e.g. the job row is missing or the DB is unavailable).
    """
    try:
        job = db.get(GenerationJob, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.completed_at = _utcnow()
            db.commit()
    except Exception as inner:
        logger.error(
            "Could not mark job %s as FAILED: %s", job_id, inner
        )


def _safe_error_message(exc: Exception) -> str:
    """
    Return a human-readable error message that does NOT include file
    system paths, stack traces, or other internal details.
    """
    msg = str(exc)
    # Remove anything that looks like an absolute path.
    import re
    msg = re.sub(r"[A-Za-z]:\\[^\s]*", "<path>", msg)   # Windows paths
    msg = re.sub(r"/[^\s]{5,}", "<path>", msg)            # Unix paths
    # Limit length.
    return msg[:500] if len(msg) > 500 else msg


def _utcnow() -> datetime:
    """Return current UTC time as a timezone-naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
