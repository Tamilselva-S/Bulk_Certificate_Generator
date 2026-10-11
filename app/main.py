"""
app/main.py

FastAPI application factory and startup logic.

This file:
  1. Creates the FastAPI application instance.
  2. Registers all routers.
  3. Adds a startup event handler that initialises the database.
  4. Provides the /health endpoint.

Design decision: The application instance is created at module level so
that it can be imported by tests without triggering side effects.
Database initialisation happens in the lifespan handler so it runs once
when the server starts.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.routes import certificates, jobs, verify
from app.schemas import HealthResponse

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)


# ── Lifespan handler ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code before `yield` runs at startup.
    Code after `yield` runs at shutdown.
    """
    # Ensure the output directory and database tables exist.
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    logging.getLogger(__name__).info(
        "Database initialised. Output directory: %s", settings.OUTPUT_DIR
    )
    yield
    # Nothing special needed at shutdown for this project.


# ── Application instance ──────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=(
        "Backend API for generating bulk PDF certificates. "
        "Submit a list of recipients, track progress, and download PDFs."
    ),
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allows the standalone HTML frontend (opened via file:// or any local dev
# server) to call the API without browser cross-origin errors.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten to specific origins in production.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(jobs.router)
app.include_router(certificates.router)
app.include_router(verify.router)


# ── Health check endpoint ─────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check() -> HealthResponse:
    """Simple liveness probe.  Returns 200 when the server is running."""
    return HealthResponse(status="ok", version=settings.APP_VERSION)
