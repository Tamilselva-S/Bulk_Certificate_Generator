"""
app/database.py

SQLAlchemy engine and session management.

Design decisions
────────────────
1. SQLite with check_same_thread=False
   SQLite allows only one thread to use a connection by default.
   Setting check_same_thread=False lets FastAPI's background tasks
   (which run in the same process but potentially a different thread)
   reuse the engine safely.  We compensate by using scoped sessions
   that are *created fresh* inside each request or background task —
   never shared.

2. SessionLocal factory
   Each caller creates its own Session via SessionLocal().  Closing it
   (via context manager or explicit .close()) returns the connection to
   the pool.  This prevents connection leaks.

3. get_db dependency
   The generator-based dependency ensures the session is always closed
   even if the route raises an exception (the finally block runs).

4. init_db
   Creates all tables on first run.  For a production app you would
   use Alembic migrations instead, but for an assessment SQLite +
   create_all is simpler and does not require extra tooling.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    # Required for SQLite when used across threads.
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    # echo=True  # Uncomment to log every SQL statement (helpful for debugging).
)

# ── Session factory ───────────────────────────────────────────────────────────
# autocommit=False → we control transactions explicitly.
# autoflush=False  → we flush manually or on commit.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Base class for all ORM models ─────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Table creation ────────────────────────────────────────────────────────────
def init_db() -> None:
    """Create all tables in the database if they do not already exist."""
    # Import models here so their class definitions register with Base.metadata
    # before create_all is called.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


# ── FastAPI dependency ────────────────────────────────────────────────────────
def get_db():
    """
    Yield a database session for the duration of a single request.
    The session is always closed in the finally block.

    Usage in a route:
        def my_route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
