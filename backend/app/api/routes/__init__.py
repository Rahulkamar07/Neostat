"""API routes export."""

from app.api.routes.documents import router as documents_router
from app.api.routes.web import web_router

__all__ = ["documents_router", "web_router"]
