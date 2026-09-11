"""Database engine, session factory, and base model for SQLAlchemy."""

from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import get_settings

settings = get_settings()

# For SQLite, ensure directory exists and use absolute path
connect_args = {}
db_url = settings.database_url
if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    if db_url.startswith("sqlite:///"):
        abs_sqlite_file = settings.sqlite_path()
        # Convert to absolute sqlite URL with forward slashes
        db_url = f"sqlite:///{abs_sqlite_file.as_posix()}"

engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all database tables if they do not already exist."""
    # Ensure parent directory exists for SQLite
    if settings.database_url.startswith("sqlite:///"):
        settings.sqlite_path()
    Base.metadata.create_all(bind=engine)
