"""
tests/conftest.py

Shared pytest fixtures used by all test modules.

Key design decisions
─────────────────────
1. Isolated test database
   Each test session gets a fresh SQLite database in a temporary
   directory.  Production data is never touched.

2. Isolated output directory
   Generated PDFs are written to a temporary directory that is
   cleaned up after the test session.

3. Overriding settings AND SessionLocal
   We monkey-patch both `settings.OUTPUT_DIR` and the `SessionLocal`
   factory used by background tasks so that all DB writes go to the
   test database.

4. Synchronous background task execution
   FastAPI BackgroundTasks run *after* the response is returned.
   In tests using TestClient (which is synchronous), background tasks
   execute *within* the same client call — so by the time
   `client.post(...)` returns, the background task has already run.
   This means we do NOT need sleeps or polling in tests.

   Reference: https://fastapi.tiangolo.com/tutorial/background-tasks/
   TestClient docs confirm tasks run synchronously during the call.
"""

import sys
from pathlib import Path

# Ensure project root is prioritized in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import get_db


@pytest.fixture(scope="session")
def tmp_output_dir(tmp_path_factory):
    """Create a temporary directory for PDF output, shared for the session."""
    d = tmp_path_factory.mktemp("certs")
    return d


@pytest.fixture(scope="session")
def test_engine(tmp_path_factory):
    """
    Create a fresh SQLite engine pointing at a temp file for the test session.

    IMPORTANT: We import app.models here so that all ORM model classes are
    registered with Base.metadata before calling create_all().  Without this
    import, SQLAlchemy does not know about the table definitions and
    create_all() is a no-op — causing 'no such table' errors at runtime.
    """
    import app.models  # noqa: F401 — registers models with Base.metadata
    from app.database import Base

    db_path = tmp_path_factory.mktemp("db") / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def TestSessionLocal(test_engine):
    """Session factory bound to the test engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session")
def client(test_engine, TestSessionLocal, tmp_output_dir):
    """
    FastAPI TestClient with:
    - Database dependency overridden to use the test engine.
    - settings.OUTPUT_DIR pointed at the temporary directory.
    - SessionLocal in database.py and job_processor.py both patched
      so background tasks also write to the test database.
    """
    # Override OUTPUT_DIR so generator writes to the temp dir.
    settings.OUTPUT_DIR = tmp_output_dir

    # Patch SessionLocal in both places that use it so that background
    # task calls to SessionLocal() produce test-DB sessions.
    import app.database as db_module
    import app.services.job_processor as jp_module

    original_db_sl = db_module.SessionLocal
    original_jp_sl = jp_module.SessionLocal

    TestSL = TestSessionLocal
    db_module.SessionLocal = TestSL  # type: ignore[assignment]
    jp_module.SessionLocal = TestSL  # type: ignore[assignment]

    def override_get_db():
        """Dependency override: yield a test-DB session for each request."""
        db = TestSL()
        try:
            yield db
        finally:
            db.close()

    from app.main import app

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    # Restore originals after the session finishes.
    db_module.SessionLocal = original_db_sl
    jp_module.SessionLocal = original_jp_sl
    app.dependency_overrides.clear()
