"""add account profile fields and user sessions

Revision ID: 4f2c8a1b9d10
Revises: 1d2f6e7a8b9c
Create Date: 2026-04-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "4f2c8a1b9d10"
down_revision = "1d2f6e7a8b9c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("organization", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=50), nullable=False, server_default="doctor"),
    )
    op.add_column("users", sa.Column("default_age_group", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.TIMESTAMP(timezone=True), nullable=True))

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_sessions_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "default_age_group")
    op.drop_column("users", "role")
    op.drop_column("users", "organization")
