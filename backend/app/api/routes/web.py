"""Frontend web routes rendering Jinja2 dashboard and document detail views."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.repositories.document_repository import DocumentRepository

settings = get_settings()
templates = Jinja2Templates(directory=str(settings.templates_dir))

web_router = APIRouter(include_in_schema=False)


@web_router.get("/", response_class=HTMLResponse)
def get_dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    """Render main dashboard with upload form and documents history table."""
    repo = DocumentRepository(db)
    docs = repo.list_documents(skip=0, limit=50)
    total_count = repo.count_documents()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "active_page": "dashboard",
            "documents": [d.to_dict() for d in docs],
            "total_count": total_count,
        },
    )


@web_router.get("/documents/{document_name}", response_class=HTMLResponse)
def get_document_detail(
    document_name: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Render detailed view of a single processed document."""
    repo = DocumentRepository(db)
    record = repo.get_latest_by_name(document_name)
    if not record:
        # Redirect back to dashboard if document not found
        return RedirectResponse(url="/?not_found=1", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "document_detail.html",
        {
            "request": request,
            "active_page": "dashboard",
            "doc": record.to_dict(),
        },
    )
