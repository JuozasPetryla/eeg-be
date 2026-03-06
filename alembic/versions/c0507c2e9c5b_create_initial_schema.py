"""create initial schema

Revision ID: c0507c2e9c5b_create_initial_schema
Revises:
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c0507c2e9c5b"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "patients",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("external_patient_id", sa.String(length=100), nullable=False),
        sa.Column("age_years", sa.Integer(), nullable=True),
        sa.Column("sex", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "external_patient_id",
            name="uq_patients_external_patient_id",
        ),
    )

    op.create_table(
        "eeg_files",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("uploaded_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("patient_id", sa.BigInteger(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_storage_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_eeg_files_uploaded_by_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name="fk_eeg_files_patient_id_patients",
        ),
        sa.UniqueConstraint(
            "object_storage_key",
            name="uq_eeg_files_object_storage_key",
        ),
        sa.CheckConstraint(
            "file_type IN ('edf', 'csv')",
            name="ck_eeg_files_file_type",
        ),
    )

    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("eeg_file_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "queued_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["eeg_file_id"],
            ["eeg_files.id"],
            name="fk_analysis_jobs_eeg_file_id_eeg_files",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "analysis_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("analysis_job_id", sa.BigInteger(), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name="fk_analysis_results_analysis_job_id_analysis_jobs",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "analysis_job_id",
            name="uq_analysis_results_analysis_job_id",
        ),
    )

    op.create_index(
        "ix_eeg_files_uploaded_by_user_id",
        "eeg_files",
        ["uploaded_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_eeg_files_patient_id",
        "eeg_files",
        ["patient_id"],
        unique=False,
    )
    op.create_index(
        "ix_analysis_jobs_eeg_file_id",
        "analysis_jobs",
        ["eeg_file_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_jobs_eeg_file_id", table_name="analysis_jobs")
    op.drop_index("ix_eeg_files_patient_id", table_name="eeg_files")
    op.drop_index("ix_eeg_files_uploaded_by_user_id", table_name="eeg_files")

    op.drop_table("analysis_results")
    op.drop_table("analysis_jobs")
    op.drop_table("eeg_files")
    op.drop_table("patients")
    op.drop_table("users")
