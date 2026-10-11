"""
app/schemas.py

Pydantic models used for request validation and response serialisation.

Design decision: Keeping request schemas (what comes IN) and response
schemas (what goes OUT) separate prevents accidental exposure of internal
fields (e.g. file paths) and makes it easy to evolve the API independently
of the database model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Request schemas ───────────────────────────────────────────────────────────

class RecipientIn(BaseModel):
    """A single recipient submitted inside a job creation request."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Recipient's full name as it should appear on the certificate.",
    )
    email: EmailStr = Field(
        ...,
        description="Recipient's email address (used for identification only; no email is sent).",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Recipient name must not be blank or whitespace only.")
        return v.strip()


class JobCreateRequest(BaseModel):
    """
    Body for POST /api/jobs/

    Validation rules enforced here:
    - event_name: 1–200 characters, not blank.
    - issuer:     1–200 characters, not blank.
    - recipients: 1–MAX_RECIPIENTS_PER_JOB items (hard limit validated
                  in the route where `settings` is available, so we keep
                  the Pydantic min at 1 here).
    """

    event_name: str = Field(
        ..., min_length=1, max_length=200, description="Name of the event or course."
    )
    issuer: str = Field(
        ..., min_length=1, max_length=200, description="Organisation issuing the certificates."
    )
    recipients: list[RecipientIn] = Field(
        ..., min_length=1, description="List of recipients; must contain at least one entry."
    )

    @field_validator("event_name", "issuer")
    @classmethod
    def strip_and_check_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be blank or whitespace only.")
        return v.strip()


# ── Response schemas ──────────────────────────────────────────────────────────

class JobCreateResponse(BaseModel):
    """Returned immediately after POST /api/jobs/."""

    job_id: str
    status: str
    total: int
    message: str


class JobStatusResponse(BaseModel):
    """Returned by GET /api/jobs/{job_id}."""

    job_id: str
    status: str
    event_name: str
    issuer: str
    total: int
    processed: int   # recipients that have reached a terminal state
    successful: int
    failed: int
    progress_pct: float  # 0.0 – 100.0
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CertificateResult(BaseModel):
    """One entry in the GET /api/jobs/{job_id}/certificates list."""

    certificate_id: str
    recipient_name: str
    recipient_email: str
    status: str
    error_message: Optional[str] = None
    # Present only when status == SUCCESS. Built by the route, not stored.
    download_url: Optional[str] = None

    model_config = {"from_attributes": True}


class CertificateListResponse(BaseModel):
    """Returned by GET /api/jobs/{job_id}/certificates."""

    job_id: str
    total: int
    certificates: list[CertificateResult]


class HealthResponse(BaseModel):
    """Returned by GET /health."""

    status: str
    version: str
