"""add analysis_type to analysis_jobs

Revision ID: 7c8f8f5e0b1a
Revises: eaa4338d6840
Create Date: 2026-03-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "7c8f8f5e0b1a"
down_revision = "eaa4338d6840"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs",
        sa.Column(
            "analysis_type",
            sa.String(length=20),
            nullable=False,
            server_default="day",
        ),
    )


def downgrade() -> None:
    op.drop_column("analysis_jobs", "analysis_type")
