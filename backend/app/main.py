"""FastAPI application entrypoint.

Routes, exception handlers, and DB wiring are added in later phases.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


from app.core.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "Starting %s (env=%s, llm_provider=%s, model=%s)",
        settings.app_name,
        settings.app_env,
        settings.llm_provider,
        settings.active_llm_model(),
    )
    init_db()
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Document Intelligence Extraction, Validation & API Platform. "
        "OpenAPI docs are served at /docs."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
