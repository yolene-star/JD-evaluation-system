"""add run id and usage to llm call logs

Revision ID: 20260912_llm_usage
Revises:
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_llm_usage"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_call_logs", sa.Column("run_id", sa.String(length=80), nullable=True))
    op.add_column(
        "llm_call_logs",
        sa.Column("usage_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_llm_call_logs_run_id", "llm_call_logs", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_call_logs_run_id", table_name="llm_call_logs")
    op.drop_column("llm_call_logs", "usage_json")
    op.drop_column("llm_call_logs", "run_id")
