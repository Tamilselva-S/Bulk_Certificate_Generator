"""
app/routes/jobs.py

Routes for job creation and status inspection.

POST /api/jobs/       – Submit a bulk certificate generation job.
GET  /api/jobs/{id}   – Get overall job status and progress.
GET  /api/jobs/{id}/certificates – List per-recipient results.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Certificate, CertificateStatus, GenerationJob, JobStatus
from app.schemas import (
    CertificateListResponse,
    CertificateResult,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
)
from app.services.job_processor import process_job

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])
logger = logging.getLogger(__name__)


# ── POST /api/jobs/ ───────────────────────────────────────────────────────────

@router.post("/", response_model=JobCreateResponse, status_code=202)
def create_job(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
) -> JobCreateResponse:
    """
    Submit a bulk certificate generation job.

    Validation policy
    ─────────────────
    • The overall request (event_name, issuer, recipient list size) is
      validated by Pydantic.  An invalid overall request returns 422.
    • Individual recipient records are also validated by Pydantic
      (name length, email format).  Because FastAPI validates the whole
      request body at once, any invalid recipient causes a 422 response
      for the *entire* request.

    Design note: If you want to accept a batch where some recipients are
    invalid and process only the valid ones, you would need to accept a
    raw dict/list and validate each item manually.  That approach adds
    complexity.  For this assessment, the simpler whole-body validation
    is used, which is clearly documented here and in the README.

    Returns 202 Accepted with the job_id immediately.
    Background processing starts asynchronously.
    """
    # Check the maximum recipient limit (settings-aware, not hardcoded in schema).
    if len(payload.recipients) > settings.MAX_RECIPIENTS_PER_JOB:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Too many recipients. Maximum allowed per request is "
                f"{settings.MAX_RECIPIENTS_PER_JOB}."
            ),
        )

    # ── Persist job and all recipient records BEFORE starting background work ──
    job = GenerationJob(
        event_name=payload.event_name,
        issuer=payload.issuer,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    db.flush()  # Assign job.id without committing yet.

    certificates: list[Certificate] = []
    for recipient in payload.recipients:
        cert = Certificate(
            job_id=job.id,
            recipient_name=recipient.name,
            recipient_email=str(recipient.email),
            status=CertificateStatus.PENDING,
        )
        db.add(cert)
        certificates.append(cert)

    db.commit()
    # After commit, job.id and all cert.id values are available.

    total = len(certificates)
    job_id = job.id
    logger.info("Job %s created with %d recipients.", job_id, total)

    # ── Schedule background processing ────────────────────────────────────────
    # IMPORTANT: The session used in this route is closed after the request.
    # process_job() creates its own session — it must NOT use this `db`.
    background_tasks.add_task(process_job, job_id)

    return JobCreateResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        total=total,
        message="Certificate generation job created",
    )


# ── GET /api/jobs/{job_id} ────────────────────────────────────────────────────

@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> JobStatusResponse:
    """
    Return overall status and progress counts for a job.

    Progress is calculated from the actual Certificate rows — no
    redundant counters are maintained on the job record itself.
    """
    job = _get_job_or_404(db, job_id)

    all_certs = (
        db.query(Certificate).filter(Certificate.job_id == job_id).all()
    )
    total = len(all_certs)
    successful = sum(1 for c in all_certs if c.status == CertificateStatus.SUCCESS)
    failed = sum(1 for c in all_certs if c.status == CertificateStatus.FAILED)
    # "processed" = reached a terminal state (SUCCESS or FAILED)
    processed = successful + failed
    progress_pct = round((processed / total * 100) if total > 0 else 0.0, 1)

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        event_name=job.event_name,
        issuer=job.issuer,
        total=total,
        processed=processed,
        successful=successful,
        failed=failed,
        progress_pct=progress_pct,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


# ── GET /api/jobs/{job_id}/certificates ───────────────────────────────────────

@router.get("/{job_id}/certificates", response_model=CertificateListResponse)
def list_certificates(
    job_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> CertificateListResponse:
    """
    List per-recipient results for a job.

    Download URLs are constructed dynamically so they work regardless
    of the hostname the server is running on.  File-system paths are
    never exposed.
    """
    _get_job_or_404(db, job_id)

    certs = (
        db.query(Certificate).filter(Certificate.job_id == job_id).all()
    )

    results: list[CertificateResult] = []
    for cert in certs:
        # Build a download URL only for successful certificates.
        download_url: str | None = None
        if cert.status == CertificateStatus.SUCCESS:
            base_url = str(request.base_url).rstrip("/")
            download_url = f"{base_url}/api/certificates/{cert.id}/download"

        results.append(
            CertificateResult(
                certificate_id=cert.id,
                recipient_name=cert.recipient_name,
                recipient_email=cert.recipient_email,
                status=cert.status,
                error_message=cert.error_message,
                download_url=download_url,
            )
        )

    return CertificateListResponse(
        job_id=job_id,
        total=len(results),
        certificates=results,
    )


# ── Shared helpers ────────────────────────────────────────────────────────────

def _get_job_or_404(db: Session, job_id: str) -> GenerationJob:
    """Return the job or raise HTTP 404."""
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job
