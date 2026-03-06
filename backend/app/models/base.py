from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import get_settings

Base = declarative_base()
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        # Fail fast if PostgreSQL is unreachable instead of hanging
        connect_timeout_url = f"{url}&connect_timeout=5" if "?" in url else f"{url}?connect_timeout=5"
        _engine = create_engine(
            connect_timeout_url,
            pool_size=5,
            max_overflow=0,
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def get_db() -> Session:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models import document, extraction, comparison, validation, audit, page_validation, a2i  # noqa: F401
    Base.metadata.create_all(bind=get_engine())
