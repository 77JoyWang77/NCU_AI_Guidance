"""SQLAlchemy engine/session 供 PDF 問答表格使用（不影響現有 psycopg 課程助手）。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.pdf_config import pdf_settings


def _make_url(raw: str) -> str:
    """確保使用 psycopg3 driver（psycopg2 未安裝）。"""
    if raw.startswith("postgresql://") or raw.startswith("postgres://"):
        return raw.replace("postgresql://", "postgresql+psycopg://", 1).replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    return raw


_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        url = _make_url(pdf_settings.database_url)
        if not url:
            raise RuntimeError(
                "DATABASE_URL is not configured. "
                "Set DATABASE_URL in the .env file at the project root."
            )
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def PdfSessionLocal():
    """Return a new SQLAlchemy session. Use as a context manager: `with PdfSessionLocal() as db:`"""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=_get_engine(), autocommit=False, autoflush=False)
    return _session_factory()


class PdfBase(DeclarativeBase):
    pass


def dispose_pdf_engine() -> None:
    """Dispose the SQLAlchemy connection pool. Call during application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
        _engine = None
    _session_factory = None
