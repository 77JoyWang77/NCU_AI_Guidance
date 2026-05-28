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


engine = create_engine(_make_url(pdf_settings.database_url), pool_pre_ping=True)
PdfSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class PdfBase(DeclarativeBase):
    pass
