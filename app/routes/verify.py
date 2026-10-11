"""
app/routes/verify.py

Public verification endpoint for certificates.
GET /verify/{certificate_id}
Opens when a QR code is scanned; returns a styled HTML confirmation page.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Annotated

from app.database import get_db
from app.models import Certificate, CertificateStatus

router = APIRouter(tags=["Verify"])
logger = logging.getLogger(__name__)


@router.get("/verify/{certificate_id}", response_class=HTMLResponse)
def verify_certificate(
    certificate_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """
    Publicly accessible verification page linked from each certificate QR code.
    Returns HTML so it can be opened directly in a browser after scanning.
    """
    cert = db.get(Certificate, certificate_id)
    if cert is None or cert.status != CertificateStatus.SUCCESS:
        html = _render_invalid(certificate_id)
    else:
        html = _render_valid(cert)
    return HTMLResponse(content=html)


def _render_valid(cert: Certificate) -> str:
    name = cert.recipient_name
    email = cert.recipient_email
    event = cert.job.event_name if cert.job else "N/A"
    issuer = cert.job.issuer if cert.job else "KS Foundation"
    issued = cert.updated_at.strftime("%B %d, %Y") if cert.updated_at else "N/A"
    cert_id = cert.id
    now_str = datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC")

    return (
        "<!DOCTYPE html>"
        "<html lang='en'>"
        "<head>"
        "<meta charset='UTF-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'/>"
        f"<title>Certificate Verified - KS Foundation</title>"
        "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap' rel='stylesheet'/>"
        "<style>"
        "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:Inter,sans-serif;min-height:100vh;"
        "background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 50%,#0f172a 100%);"
        "display:flex;align-items:center;justify-content:center;padding:24px}"
        ".card{background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);"
        "border:1px solid rgba(255,255,255,0.15);border-radius:24px;"
        "padding:48px 52px;max-width:520px;width:100%;text-align:center;"
        "box-shadow:0 24px 80px rgba(0,0,0,0.5)}"
        ".badge{width:72px;height:72px;background:linear-gradient(135deg,#22c55e,#16a34a);"
        "border-radius:50%;display:flex;align-items:center;justify-content:center;"
        "margin:0 auto 20px;font-size:32px;box-shadow:0 0 0 8px rgba(34,197,94,0.18);"
        "animation:pop 0.5s cubic-bezier(0.175,0.885,0.32,1.275)}"
        "@keyframes pop{0%{transform:scale(0);opacity:0}100%{transform:scale(1);opacity:1}}"
        ".org{color:#60a5fa;font-size:12px;font-weight:700;letter-spacing:3px;text-transform:uppercase;margin-bottom:8px}"
        "h1{color:#f0fdf4;font-size:28px;font-weight:800;line-height:1.2;margin-bottom:6px}"
        ".sub{color:#94a3b8;font-size:14px;margin-bottom:32px}"
        ".divider{height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.15),transparent);margin:24px 0}"
        ".field{text-align:left;margin-bottom:16px}"
        ".field-label{color:#64748b;font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:4px}"
        ".field-value{color:#e2e8f0;font-size:16px;font-weight:600}"
        ".cert-id{background:rgba(96,165,250,0.1);border:1px solid rgba(96,165,250,0.25);"
        "border-radius:8px;padding:10px 14px;color:#93c5fd;font-size:12px;"
        "font-family:monospace;word-break:break-all;text-align:center;margin-top:24px}"
        ".footer{color:#475569;font-size:11px;margin-top:28px}"
        "</style>"
        "</head>"
        "<body>"
        "<div class='card'>"
        "<div class='badge'>&#10003;</div>"
        "<div class='org'>KS Foundation</div>"
        "<h1>Certificate Verified</h1>"
        "<p class='sub'>This certificate is authentic and officially issued.</p>"
        "<div class='divider'></div>"
        f"<div class='field'><div class='field-label'>Recipient</div><div class='field-value'>{name}</div></div>"
        f"<div class='field'><div class='field-label'>Email</div>"
        f"<div class='field-value' style='font-size:14px;color:#94a3b8'>{email}</div></div>"
        f"<div class='field'><div class='field-label'>Course / Event</div><div class='field-value'>{event}</div></div>"
        f"<div class='field'><div class='field-label'>Issued by</div><div class='field-value'>{issuer}</div></div>"
        f"<div class='field'><div class='field-label'>Date of Issue</div><div class='field-value'>{issued}</div></div>"
        f"<div class='cert-id'>Certificate ID: {cert_id}</div>"
        f"<p class='footer'>Scan verified on {now_str}</p>"
        "</div>"
        "</body>"
        "</html>"
    )


def _render_invalid(certificate_id: str) -> str:
    return (
        "<!DOCTYPE html>"
        "<html lang='en'>"
        "<head>"
        "<meta charset='UTF-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'/>"
        "<title>Certificate Not Found - KS Foundation</title>"
        "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap' rel='stylesheet'/>"
        "<style>"
        "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:Inter,sans-serif;min-height:100vh;"
        "background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 50%,#0f172a 100%);"
        "display:flex;align-items:center;justify-content:center;padding:24px}"
        ".card{background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);"
        "border:1px solid rgba(239,68,68,0.25);border-radius:24px;"
        "padding:48px 52px;max-width:480px;width:100%;text-align:center}"
        ".badge{width:72px;height:72px;background:linear-gradient(135deg,#ef4444,#dc2626);"
        "border-radius:50%;display:flex;align-items:center;justify-content:center;"
        "margin:0 auto 20px;font-size:32px;box-shadow:0 0 0 8px rgba(239,68,68,0.18)}"
        ".org{color:#f87171;font-size:12px;font-weight:700;letter-spacing:3px;text-transform:uppercase;margin-bottom:8px}"
        "h1{color:#fef2f2;font-size:26px;font-weight:800;margin-bottom:10px}"
        "p{color:#94a3b8;font-size:14px;line-height:1.6}"
        ".id{color:#64748b;font-size:11px;font-family:monospace;margin-top:20px}"
        "</style>"
        "</head>"
        "<body>"
        "<div class='card'>"
        "<div class='badge'>&#10005;</div>"
        "<div class='org'>KS Foundation</div>"
        "<h1>Certificate Not Found</h1>"
        "<p>We could not verify this certificate. It may be invalid, still processing, or does not exist in our records.</p>"
        f"<div class='id'>ID queried: {certificate_id}</div>"
        "</div>"
        "</body>"
        "</html>"
    )
