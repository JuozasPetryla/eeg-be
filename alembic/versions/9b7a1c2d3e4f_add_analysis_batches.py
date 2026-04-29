"""add analysis batches

Revision ID: 9b7a1c2d3e4f
Revises: 4f2c8a1b9d10
Create Date: 2026-04-29 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "9b7a1c2d3e4f"
down_revision = "4f2c8a1b9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("uploaded_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "analysis_type",
            sa.String(length=20),
            nullable=False,
            server_default="day",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_analysis_batches_uploaded_by_user_id_users",
        ),
    )

    op.add_column(
        "analysis_jobs",
        sa.Column("batch_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_analysis_jobs_batch_id_analysis_batches",
        "analysis_jobs",
        "analysis_batches",
        ["batch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_analysis_jobs_batch_id",
        "analysis_jobs",
        ["batch_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_jobs_batch_id", table_name="analysis_jobs")
    op.drop_constraint(
        "fk_analysis_jobs_batch_id_analysis_batches",
        "analysis_jobs",
        type_="foreignkey",
    )
    op.drop_column("analysis_jobs", "batch_id")
    op.drop_table("analysis_batches")
