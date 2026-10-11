"""
tests/test_downloads.py

Tests for certificate listing and download.

Covers requirements:
  7. Listing certificate results.
  8. Downloading a successful PDF.
  9. Unknown certificate returns 404.
 10. Download before success returns the documented error (409).
"""


def _create_job_and_wait(client, recipients=None):
    """Helper: create a job and return its job_id."""
    if recipients is None:
        recipients = [{"name": "Download User", "email": "dl@example.com"}]
    resp = client.post(
        "/api/jobs/",
        json={
            "event_name": "Download Test Event",
            "issuer": "Test Academy",
            "recipients": recipients,
        },
    )
    assert resp.status_code == 202
    return resp.json()["job_id"]


def test_list_certificates_returns_correct_structure(client):
    """GET /api/jobs/{id}/certificates returns the expected shape."""
    job_id = _create_job_and_wait(
        client,
        recipients=[
            {"name": "List User 1", "email": "list1@example.com"},
            {"name": "List User 2", "email": "list2@example.com"},
        ],
    )
    resp = client.get(f"/api/jobs/{job_id}/certificates")
    assert resp.status_code == 200
    data = resp.json()

    assert data["job_id"] == job_id
    assert data["total"] == 2
    assert len(data["certificates"]) == 2

    # Each entry should have required fields.
    for cert in data["certificates"]:
        assert "certificate_id" in cert
        assert "recipient_name" in cert
        assert "recipient_email" in cert
        assert "status" in cert


def test_successful_certificate_has_download_url(client):
    """A successful certificate should include a download_url in the list."""
    job_id = _create_job_and_wait(client)
    data = client.get(f"/api/jobs/{job_id}/certificates").json()

    successful = [c for c in data["certificates"] if c["status"] == "SUCCESS"]
    assert len(successful) >= 1
    assert successful[0]["download_url"] is not None
    assert "/api/certificates/" in successful[0]["download_url"]
    assert "/download" in successful[0]["download_url"]


def test_download_successful_certificate(client):
    """Downloading a successful certificate returns a PDF response."""
    job_id = _create_job_and_wait(client)
    certs = client.get(f"/api/jobs/{job_id}/certificates").json()["certificates"]
    successful = [c for c in certs if c["status"] == "SUCCESS"]
    assert len(successful) >= 1

    cert_id = successful[0]["certificate_id"]
    dl_resp = client.get(f"/api/certificates/{cert_id}/download")

    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/pdf"
    # PDF magic bytes
    assert dl_resp.content[:4] == b"%PDF"


def test_download_unknown_certificate_returns_404(client):
    """Requesting a download for an unknown certificate ID returns 404."""
    resp = client.get("/api/certificates/completely-unknown-id-xyz/download")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_unknown_job_certificates_returns_404(client):
    """GET /api/jobs/{bad_id}/certificates returns 404."""
    resp = client.get("/api/jobs/bad-job-id-999/certificates")
    assert resp.status_code == 404


def test_download_before_success_returns_409(client, TestSessionLocal):
    """
    Downloading a certificate that is still PENDING returns 409 Conflict.

    We directly insert a PENDING certificate into the test DB to
    simulate this state without a race condition.
    """
    from app.models import Certificate, CertificateStatus, GenerationJob, JobStatus

    db = TestSessionLocal()
    try:
        job = GenerationJob(
            event_name="Pending Test Event",
            issuer="Test Org",
            status=JobStatus.QUEUED,
        )
        db.add(job)
        db.flush()

        cert = Certificate(
            job_id=job.id,
            recipient_name="Pending Person",
            recipient_email="pending@example.com",
            status=CertificateStatus.PENDING,  # Not yet processed
        )
        db.add(cert)
        db.commit()
        cert_id = cert.id
    finally:
        db.close()

    resp = client.get(f"/api/certificates/{cert_id}/download")
    assert resp.status_code == 409
    assert "PENDING" in resp.json()["detail"]
