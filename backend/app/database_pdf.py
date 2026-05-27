"""SQLAlchemy engine/session 供 PDF 問答表格使用（不影響現有 psycopg 課程助手）。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.pdf_config import pdf_settings


engine = create_engine(pdf_settings.database_url, pool_pre_ping=True)
PdfSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class PdfBase(DeclarativeBase):
    pass
