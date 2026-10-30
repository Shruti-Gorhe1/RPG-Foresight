"""FastAPI application entry point — RPG Foresight API.

Accelerator baseline: environment-scoped CORS, structured logging, Phoenix
tracing, and session-oriented routers. Data ingestion, connectors, rules,
and notification endpoints are registered here.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import data_ingestion, delivery_status, example, health, recipients, rules, signal_history, tender_operations, pursuit_copilot
from observability.tracing import init_tracing, instrument_fastapi
from shared.config import get_settings
from shared.logger import get_logger, setup_logging

log = get_logger("api.main")
settings = get_settings()

APP_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_tracing()
    # Schema is managed by Alembic — run `alembic upgrade head` before starting.
    log.info("api.startup", env=settings.app_env, version=APP_VERSION)
    # Schema is managed by Alembic — run `alembic upgrade head` before starting.
    # In development, create tables + seed demo data automatically.
    if settings.app_env == "development":
        from db.base import create_all_tables

        await create_all_tables()
    yield
    log.info("api.shutdown")


app = FastAPI(
    title="RPG Foresight API",
    description="CRM-free tender signal ingestion and evaluation platform",
    version=APP_VERSION,
    lifespan=lifespan,
)
instrument_fastapi(app)

# ── CORS ───────────────────────────────────────────────────────────────────────
if settings.app_env == "development":
    _cors_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]
else:
    _cors_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    if not _cors_origins:
        raise RuntimeError(
            f"CORS_ALLOWED_ORIGINS must be set in app_env={settings.app_env!r}. "
            "Example: https://__APP_NAME__-fe.bravesky-d9f9eeb7.eastus2.azurecontainerapps.io"
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, tags=["Health"])
app.include_router(health.router, prefix="/api/v1", tags=["Health"], include_in_schema=False)
app.include_router(example.router, prefix="/api/v1/example", tags=["Example"])
app.include_router(
    data_ingestion.router,
    prefix="/api/v1/data-ingestion",
    tags=["Data Ingestion"],
)
app.include_router(rules.router, prefix="/api/v1/rules", tags=["Rules"])
app.include_router(recipients.router, prefix="/api/v1/recipients", tags=["Recipients"])
app.include_router(signal_history.router, prefix="/api/v1/signal-history", tags=["Signal History"])
app.include_router(delivery_status.router, prefix="/api/v1/delivery-status", tags=["Delivery Status"])
app.include_router(tender_operations.router, prefix="/api/v1/tenders", tags=["Tender Operations"])
app.include_router(pursuit_copilot.router, prefix="/api/v1/pursuit", tags=["Tender Pursuit Copilot"])