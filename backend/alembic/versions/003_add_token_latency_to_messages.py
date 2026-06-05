"""add token and latency columns to pdf_agent_messages

Revision ID: 003_add_token_latency
Revises: 002_conv_document_id
Create Date: 2026-06-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_add_token_latency"
down_revision: Union[str, None] = "002_conv_document_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pdf_agent_messages", sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pdf_agent_messages", sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pdf_agent_messages", sa.Column("router_input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pdf_agent_messages", sa.Column("router_output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pdf_agent_messages", sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pdf_agent_messages", sa.Column("model_name", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in ["model_name", "latency_ms", "router_output_tokens",
                "router_input_tokens", "output_tokens", "input_tokens"]:
        op.drop_column("pdf_agent_messages", col)
