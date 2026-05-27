"""add pdf chat tables

Revision ID: 001_add_pdf_chat
Revises:
Create Date: 2026-05-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "001_add_pdf_chat"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pdf_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(36), unique=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("message_count", sa.Integer(), default=0),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("last_agent_name", sa.String(), nullable=True),
        sa.Column("stream_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_pdf_conversations_thread_id", "pdf_conversations", ["thread_id"])
    op.create_index("ix_pdf_conversations_user_id", "pdf_conversations", ["user_id"])

    op.create_table(
        "pdf_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("abstract_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="ready"),
    )

    op.create_table(
        "pdf_agent_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.String(36), unique=True, nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("user_question", sa.Text(), nullable=True),
        sa.Column("agent_answer", sa.Text(), nullable=True),
        sa.Column("sources", postgresql.JSONB(), nullable=True),
        sa.Column("trace_summary", postgresql.JSONB(), nullable=True),
        sa.Column("observation_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_pdf_agent_messages_message_id", "pdf_agent_messages", ["message_id"])
    op.create_index("ix_pdf_agent_messages_thread_id", "pdf_agent_messages", ["thread_id"])
    op.create_index("ix_pdf_agent_messages_user_id", "pdf_agent_messages", ["user_id"])
    op.create_index("ix_pdf_agent_messages_observation_id", "pdf_agent_messages", ["observation_id"])
    op.create_index("ix_pdf_agent_messages_created_at", "pdf_agent_messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("pdf_agent_messages")
    op.drop_table("pdf_documents")
    op.drop_table("pdf_conversations")
