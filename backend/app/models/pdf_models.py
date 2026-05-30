"""SQLAlchemy ORM models for PDF 問答功能（pdf_conversations、pdf_agent_messages、pdf_documents）。"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database_pdf import PdfBase


class PdfConversation(PdfBase):
    __tablename__ = "pdf_conversations"

    id = Column(Integer, primary_key=True)
    thread_id = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(String, nullable=True, index=True)
    document_id = Column(Integer, nullable=True, index=True)
    model = Column(String, nullable=True)
    title = Column(String, nullable=True)
    message_count = Column(Integer, default=0)
    context_summary = Column(Text, nullable=True)
    last_agent_name = Column(String, nullable=True)
    stream_started_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PdfDocument(PdfBase):
    __tablename__ = "pdf_documents"

    id = Column(Integer, primary_key=True)
    filename = Column(Text, nullable=False)
    abstract_text = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="ready")


class PdfAgentMessage(PdfBase):
    __tablename__ = "pdf_agent_messages"

    id = Column(Integer, primary_key=True)
    message_id = Column(String(36), unique=True, nullable=False, index=True)
    thread_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=True, index=True)
    agent_name = Column(String, nullable=False)
    user_question = Column(Text, nullable=True)
    agent_answer = Column(Text, nullable=True)
    sources = Column(JSONB, nullable=True)
    trace_summary = Column(JSONB, nullable=True)
    observation_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
