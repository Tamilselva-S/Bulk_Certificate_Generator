"""
app/routes/certificates.py

Routes for certificate download.

GET /api/certificates/{certificate_id}/download
"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Certificate, CertificateStatus

router = APIRouter(prefix="/api/certificates", tags=["Certificates"])
logger = logging.getLogger(__name__)


@router.get("/{certificate_id}/download")
def download_certificate(
    certificate_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    """
    Download the generated PDF for a certificate.

    HTTP status codes
    ─────────────────
    200  – PDF file returned.
    404  – Certificate ID not found in the database.
    409  – Certificate exists but is not yet successful (still PENDING /
           PROCESSING, or has FAILED).  A 409 Conflict communicates
           "the resource exists but is in the wrong state for this
           action", which is more informative than 404.

    Security
    ────────
    The file path stored in the database is a filename only (e.g.
    "abc-123.pdf").  We reconstruct the full path by joining it with
    the configured OUTPUT_DIR and then resolve() both paths to check
    that the resolved path sits inside the expected directory.
    This prevents path-traversal attacks even if a corrupted DB row
    contained a relative path like "../etc/passwd".
    """
    cert = db.get(Certificate, certificate_id)

    if cert is None:
        raise HTTPException(
            status_code=404,
            detail=f"Certificate '{certificate_id}' not found.",
        )

    if cert.status != CertificateStatus.SUCCESS:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Certificate is not yet available. "
                f"Current status: {cert.status}."
            ),
        )

    if not cert.file_path:
        # Should not happen if status is SUCCESS, but guard anyway.
        raise HTTPException(
            status_code=500,
            detail="Certificate record is in an inconsistent state.",
        )

    # ── Build and validate the file path ─────────────────────────────────────
    output_dir = settings.OUTPUT_DIR.resolve()
    candidate = (output_dir / cert.file_path).resolve()

    # Security check: ensure the resolved path is inside OUTPUT_DIR.
    if not str(candidate).startswith(str(output_dir)):
        logger.error(
            "Path traversal attempt detected for certificate %s", certificate_id
        )
        raise HTTPException(status_code=500, detail="Invalid file path.")

    if not candidate.exists():
        logger.error(
            "PDF file missing on disk for certificate %s: %s",
            certificate_id,
            candidate.name,  # Log filename only, not full path.
        )
        raise HTTPException(
            status_code=500,
            detail="Certificate file is missing. Please contact support.",
        )

    # Build a clean download filename: "certificate-<id>.pdf"
    download_filename = f"certificate-{certificate_id}.pdf"

    return FileResponse(
        path=str(candidate),
        media_type="application/pdf",
        filename=download_filename,
        headers={
            "Content-Disposition": f'attachment; filename="{download_filename}"'
        },
    )
