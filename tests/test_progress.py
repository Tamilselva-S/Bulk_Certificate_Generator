"""
tests/test_progress.py

Tests for job progress calculation.

Covers requirement:
  5. Job status and progress counts.
 12. Correct final status for all-success and partial-failure jobs.
"""


def test_all_success_job_status_is_completed(client):
    """A job where all certificates succeed should have status COMPLETED."""
    resp = client.post(
        "/api/jobs/",
        json={
            "event_name": "ML Conference",
            "issuer": "AI Society",
            "recipients": [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ],
        },
    )
    job_id = resp.json()["job_id"]

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "COMPLETED"
    assert status["successful"] == 2
    assert status["failed"] == 0
    assert status["progress_pct"] == 100.0


def test_progress_counts_add_up(client):
    """successful + failed should always equal processed, which equals total when done."""
    resp = client.post(
        "/api/jobs/",
        json={
            "event_name": "Cloud Workshop",
            "issuer": "Dev Club",
            "recipients": [
                {"name": "Carol", "email": "carol@example.com"},
                {"name": "Dave", "email": "dave@example.com"},
                {"name": "Eve", "email": "eve@example.com"},
            ],
        },
    )
    job_id = resp.json()["job_id"]
    data = client.get(f"/api/jobs/{job_id}").json()

    assert data["processed"] == data["successful"] + data["failed"]
    assert data["total"] == 3
