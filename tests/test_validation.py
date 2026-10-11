"""
tests/test_validation.py

Tests for request validation.

Covers requirements:
  2. Invalid overall request validation.
 11. Empty recipient list and maximum batch-size validation.
"""


def test_missing_event_name_returns_422(client):
    """event_name is required; omitting it returns 422."""
    response = client.post(
        "/api/jobs/",
        json={
            "issuer": "Some Org",
            "recipients": [{"name": "Test User", "email": "test@example.com"}],
        },
    )
    assert response.status_code == 422


def test_missing_issuer_returns_422(client):
    """issuer is required; omitting it returns 422."""
    response = client.post(
        "/api/jobs/",
        json={
            "event_name": "Workshop",
            "recipients": [{"name": "Test User", "email": "test@example.com"}],
        },
    )
    assert response.status_code == 422


def test_empty_recipients_list_returns_422(client):
    """An empty recipients list returns 422."""
    response = client.post(
        "/api/jobs/",
        json={
            "event_name": "Workshop",
            "issuer": "Org",
            "recipients": [],
        },
    )
    assert response.status_code == 422


def test_invalid_email_in_recipient_returns_422(client):
    """A recipient with an invalid email address returns 422."""
    response = client.post(
        "/api/jobs/",
        json={
            "event_name": "Workshop",
            "issuer": "Org",
            "recipients": [{"name": "Bad Email", "email": "not-an-email"}],
        },
    )
    assert response.status_code == 422


def test_blank_recipient_name_returns_422(client):
    """A recipient with a blank/whitespace name returns 422."""
    response = client.post(
        "/api/jobs/",
        json={
            "event_name": "Workshop",
            "issuer": "Org",
            "recipients": [{"name": "   ", "email": "valid@example.com"}],
        },
    )
    assert response.status_code == 422


def test_blank_event_name_returns_422(client):
    """A whitespace-only event_name returns 422."""
    response = client.post(
        "/api/jobs/",
        json={
            "event_name": "   ",
            "issuer": "Org",
            "recipients": [{"name": "Valid Name", "email": "valid@example.com"}],
        },
    )
    assert response.status_code == 422


def test_too_many_recipients_returns_422(client):
    """Exceeding MAX_RECIPIENTS_PER_JOB returns 422."""
    from app.config import settings

    # Build a list one over the limit.
    too_many = [
        {"name": f"User {i}", "email": f"user{i}@example.com"}
        for i in range(settings.MAX_RECIPIENTS_PER_JOB + 1)
    ]
    response = client.post(
        "/api/jobs/",
        json={"event_name": "Mega Event", "issuer": "Big Org", "recipients": too_many},
    )
    assert response.status_code == 422
    assert "Maximum allowed" in response.json()["detail"]
