"""add document_id to pdf_conversations

Revision ID: 002_add_document_id_to_conversations
Revises: 001_add_pdf_chat
Create Date: 2026-05-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_add_document_id_to_conversations"
down_revision: Union[str, None] = "001_add_pdf_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pdf_conversations",
        sa.Column("document_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_pdf_conversations_document_id",
        "pdf_conversations",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pdf_conversations_document_id", table_name="pdf_conversations")
    op.drop_column("pdf_conversations", "document_id")
