"""FastAPI application entrypoint.

Wires up database initialization, global domain exception handlers,
and API routes for document processing and validation.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes.documents import router as documents_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


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
        "Provides end-to-end OCR, schema-guided LLM extraction, and deterministic "
        "financial calculation verification. OpenAPI docs are served at /docs."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# Global Exception Handler for domain AppError subclasses
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.warning("Handled AppError on %s: %s (code=%s)", request.url.path, exc.message, exc.code)
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_error_body(),
    )


# Exception handler for FastAPI request validation errors
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    logger.warning("Request validation error on %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "REQUEST_VALIDATION_ERROR",
                "message": "Invalid request parameters or payload.",
                "details": {"errors": exc.errors()},
            }
        },
    )


# Exception handler for unhandled exceptions
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected internal error occurred.",
            }
        },
    )


# Register API routes
app.include_router(documents_router)
