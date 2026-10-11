"""
tests/test_generator.py

Unit tests for the PDF generation function.

These tests exercise `generate_certificate_pdf` directly — no HTTP
layer, no database.  This tests the function in true isolation.

Covers requirement:
  4. PDF generation and verification that the file is valid and non-empty.
"""

import os
from datetime import date
from pathlib import Path

import pytest

from app.services.generator import _safe_filename, _truncate_text, generate_certificate_pdf


def test_generates_non_empty_pdf(tmp_path):
    """A successful call creates a non-empty PDF file."""
    cert_id = "test-cert-id-0001"
    out_path = generate_certificate_pdf(
        certificate_id=cert_id,
        recipient_name="Arun Kumar",
        event_name="Python Workshop 2026",
        issuer="Agni College of Technology",
        issue_date=date(2026, 10, 9),
        output_dir=tmp_path,
    )

    assert out_path.exists(), "PDF file should exist after generation."
    assert out_path.stat().st_size > 0, "PDF file should not be empty."


def test_pdf_has_correct_filename(tmp_path):
    """The output filename is derived from the certificate ID."""
    cert_id = "abc-123-def"
    out_path = generate_certificate_pdf(
        certificate_id=cert_id,
        recipient_name="Priya Sharma",
        event_name="AI Summit",
        issuer="Innovation Hub",
        issue_date=date(2026, 1, 15),
        output_dir=tmp_path,
    )
    assert out_path.name == f"{cert_id}.pdf"


def test_pdf_starts_with_pdf_magic_bytes(tmp_path):
    """Generated file should begin with '%PDF' — the PDF magic bytes."""
    cert_id = "magic-bytes-test"
    out_path = generate_certificate_pdf(
        certificate_id=cert_id,
        recipient_name="Test Recipient",
        event_name="Test Event",
        issuer="Test Org",
        issue_date=date(2026, 6, 1),
        output_dir=tmp_path,
    )
    with open(out_path, "rb") as f:
        header = f.read(4)
    assert header == b"%PDF", f"File does not start with PDF magic bytes: {header!r}"


def test_different_recipients_get_different_files(tmp_path):
    """Two certificates with different IDs produce two separate files."""
    id1 = "cert-id-aaa"
    id2 = "cert-id-bbb"

    path1 = generate_certificate_pdf(
        certificate_id=id1,
        recipient_name="Alice",
        event_name="Event",
        issuer="Org",
        issue_date=date.today(),
        output_dir=tmp_path,
    )
    path2 = generate_certificate_pdf(
        certificate_id=id2,
        recipient_name="Bob",
        event_name="Event",
        issuer="Org",
        issue_date=date.today(),
        output_dir=tmp_path,
    )

    assert path1 != path2
    assert path1.exists()
    assert path2.exists()


def test_safe_filename_strips_special_chars():
    """_safe_filename removes characters that are not alphanumeric or hyphen."""
    # Alphanumeric and hyphens are preserved.
    assert _safe_filename("abc-123") == "abc-123"
    # Slashes and dots are replaced with underscores.
    result = _safe_filename("abc/../../etc")
    assert "/" not in result
    assert ".." not in result
    assert "abc" in result
    assert "etc" in result
    # Forward slash must never appear in the output.
    assert "/" not in _safe_filename("a/b/c")


def test_truncate_text_no_truncation_needed():
    """Short text is returned unchanged."""
    assert _truncate_text("Hello", 10) == "Hello"


def test_truncate_text_truncates_long_text():
    """Text longer than max_chars is truncated with an ellipsis."""
    result = _truncate_text("A" * 100, 20)
    assert len(result) == 20
    assert result.endswith("…")


def test_output_directory_created_if_missing(tmp_path):
    """generate_certificate_pdf creates OUTPUT_DIR if it does not exist."""
    new_dir = tmp_path / "does_not_exist_yet"
    assert not new_dir.exists()

    generate_certificate_pdf(
        certificate_id="new-dir-test",
        recipient_name="Dir Test",
        event_name="Dir Event",
        issuer="Dir Org",
        issue_date=date.today(),
        output_dir=new_dir,
    )

    assert new_dir.exists()


def test_generator_handles_long_recipient_name(tmp_path):
    """Generator handles long recipient names without errors or clipping."""
    out_path = generate_certificate_pdf(
        certificate_id="long-name-test",
        recipient_name="Dr. Bartholomew Montgomery-Wellington III Esq.",
        event_name="Quantum Computing Seminar",
        issuer="KS Foundation",
        issue_date=date(2026, 10, 11),
        output_dir=tmp_path,
    )
    assert out_path.exists()
    assert out_path.stat().st_size > 5000  # Substantial PDF with rich vectors


def test_generator_handles_long_course_title(tmp_path):
    """Generator handles long course names without errors or clipping."""
    out_path = generate_certificate_pdf(
        certificate_id="long-course-test",
        recipient_name="Tamilselva S",
        event_name="Advanced Distributed Cloud Architecture and Microservices Engineering Professional Program",
        issuer="KS Foundation",
        issue_date=date(2026, 10, 11),
        output_dir=tmp_path,
    )
    assert out_path.exists()
    assert out_path.stat().st_size > 5000


def test_generator_embeds_certificate_content(tmp_path):
    """Verify that generated PDF contains all required textual content."""
    import pymupdf

    cert_id = "text-content-verification-001"
    name = "Tamilselva S"
    course = "Python Programming Workshop"
    issuer = "KS Foundation"
    dt = date(2026, 10, 11)

    out_path = generate_certificate_pdf(
        certificate_id=cert_id,
        recipient_name=name,
        event_name=course,
        issuer=issuer,
        issue_date=dt,
        output_dir=tmp_path,
    )

    doc = pymupdf.open(out_path)
    text = doc[0].get_text()

    assert "KS" in text
    assert "FOUNDATION" in text
    assert "Excellence in Education" in text
    assert "SCAN TO VERIFY" in text
    assert "Certificate" in text
    assert "of Completion" in text
    assert name in text
    assert course in text
    assert "For successfully completing the" in text
    assert "We appreciate your dedication" in text
    assert "Issued on 11 October 2026" in text
    assert "Director" in text
    assert issuer in text
    assert cert_id in text

