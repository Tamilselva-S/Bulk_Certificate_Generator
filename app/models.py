"""
app/models.py

SQLAlchemy ORM models (database table definitions).

Timezone convention: ALL timestamps are stored as UTC (timezone-naive
datetime objects that implicitly represent UTC).  The README documents
this so API consumers know they must apply their own local offset.

ID convention: UUIDs are used for all primary keys.  They are generated
in Python (not the database) so the ID is known before the INSERT
commits — important for returning the job_id in the creation response
without a round-trip.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_uuid() -> str:
    """Return a new UUID4 string.  Used as a default for primary keys."""
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    """Return current UTC time (timezone-naive, stored as UTC by convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Enumerations ──────────────────────────────────────────────────────────────

class JobStatus:
    """Valid states for a GenerationJob."""
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


class CertificateStatus:
    """Valid states for a Certificate (per-recipient record)."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# ── ORM Models ────────────────────────────────────────────────────────────────

class GenerationJob(Base):
    """
    Represents one bulk certificate generation request.

    One job → many Certificate records (one per submitted recipient).
    """
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    event_name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=JobStatus.QUEUED
    )

    # UTC timestamps — see timezone convention note at the top of this file.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationship: access all certificate records via job.certificates
    certificates: Mapped[list["Certificate"]] = relationship(
        "Certificate", back_populates="job", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<GenerationJob id={self.id} status={self.status}>"


class Certificate(Base):
    """
    One record per submitted recipient inside a job.

    Tracks the status of generating that individual's PDF certificate.
    """
    __tablename__ = "certificates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("generation_jobs.id"), nullable=False
    )
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CertificateStatus.PENDING
    )

    # Relative path from the OUTPUT_DIR root, e.g. "abc123.pdf".
    # NULL until generation succeeds.
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Human-readable error message stored on failure.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationship: navigate back to the parent job
    job: Mapped["GenerationJob"] = relationship(
        "GenerationJob", back_populates="certificates"
    )

    def __repr__(self) -> str:
        return (
            f"<Certificate id={self.id} "
            f"recipient={self.recipient_email} status={self.status}>"
        )


# ── Database indexes ──────────────────────────────────────────────────────────
# Index on certificates.job_id speeds up queries that filter by job.
Index("ix_certificates_job_id", Certificate.job_id)
