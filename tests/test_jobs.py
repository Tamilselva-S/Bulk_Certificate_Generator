"""
tests/test_jobs.py

Tests for job creation and status retrieval.

Covers requirements:
  1. Creating a job with multiple recipients.
  5. Job status and progress counts.
  9. Unknown job returns 404.
"""


def test_create_job_multiple_recipients(client):
    """A valid request creates a job and returns 202 with a job_id."""
    response = client.post(
        "/api/jobs/",
        json={
            "event_name": "Python Workshop 2026",
            "issuer": "Agni College of Technology",
            "recipients": [
                {"name": "Arun Kumar", "email": "arun@example.com"},
                {"name": "Priya Sharma", "email": "priya@example.com"},
            ],
        },
    )
    assert response.status_code == 202, response.text
    data = response.json()
    assert "job_id" in data
    assert data["total"] == 2
    assert data["status"] == "QUEUED"
    assert data["message"] == "Certificate generation job created"


def test_job_status_returns_correct_fields(client):
    """GET /api/jobs/{id} returns all expected fields."""
    # Create a job first.
    create_resp = client.post(
        "/api/jobs/",
        json={
            "event_name": "Data Science Bootcamp",
            "issuer": "Tech Academy",
            "recipients": [{"name": "Meera Nair", "email": "meera@example.com"}],
        },
    )
    job_id = create_resp.json()["job_id"]

    status_resp = client.get(f"/api/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()

    assert data["job_id"] == job_id
    assert data["event_name"] == "Data Science Bootcamp"
    assert data["issuer"] == "Tech Academy"
    assert data["total"] == 1
    assert "processed" in data
    assert "successful" in data
    assert "failed" in data
    assert "progress_pct" in data
    assert "created_at" in data


def test_job_status_progress_completes(client):
    """After background processing, progress should reach 100%."""
    create_resp = client.post(
        "/api/jobs/",
        json={
            "event_name": "AI Summit",
            "issuer": "Innovation Hub",
            "recipients": [
                {"name": "Ravi Patel", "email": "ravi@example.com"},
                {"name": "Sneha Roy", "email": "sneha@example.com"},
            ],
        },
    )
    job_id = create_resp.json()["job_id"]

    status_resp = client.get(f"/api/jobs/{job_id}")
    data = status_resp.json()

    # Background tasks run synchronously in TestClient, so processing is done.
    assert data["processed"] == 2
    assert data["progress_pct"] == 100.0


def test_unknown_job_returns_404(client):
    """Requesting a non-existent job ID returns 404."""
    response = client.get("/api/jobs/non-existent-job-id-xyz")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
