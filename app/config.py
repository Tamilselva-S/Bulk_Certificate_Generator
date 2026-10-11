"""
app/config.py

Central configuration loaded from environment variables (or a .env file).

Design decision: Using pydantic-settings / plain os.getenv keeps all
tuneable knobs in one place.  Any module that needs a setting imports
`settings` from here instead of reading os.environ directly.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if it exists. In production you would inject real env vars.
load_dotenv()


class Settings:
    """Application-wide settings resolved from environment variables."""

    APP_TITLE: str = os.getenv("APP_TITLE", "Bulk Certificate Generator")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")

    # Base URL used for public verification links and QR codes.
    BASE_URL: str = os.getenv("BASE_URL", "http://127.0.0.1:8000")

    # Folder where generated PDFs are stored.
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "generated_certificates"))

    # SQLAlchemy connection string.
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./certificates.db"
    )

    # Maximum recipients accepted in a single POST /api/jobs/ request.
    MAX_RECIPIENTS_PER_JOB: int = int(
        os.getenv("MAX_RECIPIENTS_PER_JOB", "500")
    )


# Single shared instance used throughout the application.
settings = Settings()
