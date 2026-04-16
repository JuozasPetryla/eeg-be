"""add password hash to users

Revision ID: 1d2f6e7a8b9c
Revises: 7c8f8f5e0b1a
Create Date: 2026-04-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "1d2f6e7a8b9c"
down_revision = "7c8f8f5e0b1a"
branch_labels = None
depends_on = None

DEFAULT_PASSWORD_HASH = (
    "pbkdf2_sha256$100000$tnT9YDUhoWOl0HEwR55/fA==$"
    "vIiO4IDoZagURQa+G3yddUfRPmxJf6P0ys3D1+hb/vU="
)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=512), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE users SET password_hash = :password_hash WHERE password_hash IS NULL"
        ).bindparams(password_hash=DEFAULT_PASSWORD_HASH)
    )
    op.alter_column("users", "password_hash", nullable=False)


def downgrade() -> None:
    op.drop_column("users", "password_hash")
