"""
tests/test_failures.py

Tests for failure isolation and job status under partial failures.

Covers requirements:
  3. Individual invalid recipient handling while valid recipients still succeed.
  6. An injected failure for one recipient while other recipients succeed.
 12. Correct final status for all-success and partial-failure jobs.

Technique for injecting failures
──────────────────────────────────
We use unittest.mock.patch to temporarily replace `generate_certificate_pdf`
AS IMPORTED in job_processor (the call site), not in the generator module
itself.  This is critical: job_processor does

    from app.services.generator import generate_certificate_pdf

so it holds a direct reference.  Patching generator.generate_certificate_pdf
would replace the name in the generator module namespace, but job_processor's
local name would still point to the original.  We must patch
`app.services.job_processor.generate_certificate_pdf` to intercept calls
made from within job_processor.

The `with patch(...)` block also wraps `client.post(...)` entirely so the
patch is active when the synchronous BackgroundTask runs.
"""

from unittest.mock import patch

from app.services import generator as generator_module

PATCH_TARGET = "app.services.job_processor.generate_certificate_pdf"


def test_one_failure_does_not_stop_others(client):
    """
    When one recipient's PDF generation fails, others still succeed.
    The job ends with COMPLETED_WITH_ERRORS, not FAILED.
    """
    original_generate = generator_module.generate_certificate_pdf

    def failing_generate(**kwargs):
        if kwargs.get("recipient_name") == "Fail Me":
            raise RuntimeError("Simulated PDF generation error")
        return original_generate(**kwargs)

    # Patch at the call site (job_processor), not at the definition site.
    with patch(PATCH_TARGET, side_effect=failing_generate):
        resp = client.post(
            "/api/jobs/",
            json={
                "event_name": "Resilience Test",
                "issuer": "Test Org",
                "recipients": [
                    {"name": "Good Recipient", "email": "good@example.com"},
                    {"name": "Fail Me", "email": "failme@example.com"},
                    {"name": "Another Good", "email": "good2@example.com"},
                ],
            },
        )
        # NOTE: keep the patch active while client.post() runs background tasks.

    job_id = resp.json()["job_id"]
    status = client.get(f"/api/jobs/{job_id}").json()

    assert status["status"] == "COMPLETED_WITH_ERRORS"
    assert status["successful"] == 2
    assert status["failed"] == 1
    assert status["processed"] == 3


def test_all_failure_job_status_is_failed(client):
    """
    When every recipient's PDF generation fails, the job status is FAILED.
    """
    def always_fail(**kwargs):
        raise RuntimeError("Simulated total failure")

    with patch(PATCH_TARGET, side_effect=always_fail):
        resp = client.post(
            "/api/jobs/",
            json={
                "event_name": "All Fail Test",
                "issuer": "Test Org",
                "recipients": [
                    {"name": "Recipient A", "email": "a@example.com"},
                    {"name": "Recipient B", "email": "b@example.com"},
                ],
            },
        )

    job_id = resp.json()["job_id"]
    status = client.get(f"/api/jobs/{job_id}").json()

    assert status["status"] == "FAILED"
    assert status["successful"] == 0
    assert status["failed"] == 2


def test_failed_certificate_has_error_message(client):
    """A failed certificate record should contain a non-empty error message."""
    original_generate = generator_module.generate_certificate_pdf

    def fail_one(**kwargs):
        if kwargs.get("recipient_name") == "Error Person":
            raise ValueError("Something went wrong with the PDF")
        return original_generate(**kwargs)

    with patch(PATCH_TARGET, side_effect=fail_one):
        resp = client.post(
            "/api/jobs/",
            json={
                "event_name": "Error Test Event",
                "issuer": "Test Org",
                "recipients": [
                    {"name": "Error Person", "email": "error@example.com"},
                ],
            },
        )

    job_id = resp.json()["job_id"]
    certs_resp = client.get(f"/api/jobs/{job_id}/certificates").json()
    failed_certs = [c for c in certs_resp["certificates"] if c["status"] == "FAILED"]

    assert len(failed_certs) == 1
    assert failed_certs[0]["error_message"] is not None
    assert len(failed_certs[0]["error_message"]) > 0
