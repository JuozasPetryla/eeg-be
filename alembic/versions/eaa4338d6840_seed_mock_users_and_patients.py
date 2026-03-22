"""seed mock users and patients

Revision ID: eaa4338d6840
Revises: c0507c2e9c5b
Create Date: 2026-03-22 11:58:37.614468

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eaa4338d6840'
down_revision: Union[str, Sequence[str], None] = 'c0507c2e9c5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.bulk_insert(
        sa.table("users", sa.column("email", sa.String(255)), sa.column("full_name", sa.String(255))),
        [
            {"email": "john.doe@example.com", "full_name": "John Doe"},
            {"email": "jane.smith@example.com", "full_name": "Jane Smith"},
            {"email": "alice.brown@example.com", "full_name": "Alice Brown"},
        ],
    )
    op.bulk_insert(
        sa.table("patients", sa.column("external_patient_id", sa.String(100)), sa.column("age_years", sa.Integer()), sa.column("sex", sa.String(20))),
        [
            {"external_patient_id": "PAT-0001", "age_years": 29, "sex": "female"},
            {"external_patient_id": "PAT-0002", "age_years": 41, "sex": "male"},
            {"external_patient_id": "PAT-0003", "age_years": 35, "sex": "female"},
            {"external_patient_id": "PAT-0004", "age_years": 52, "sex": "male"},
            {"external_patient_id": "PAT-0005", "age_years": 23, "sex": "female"},
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM patients WHERE external_patient_id IN ('PAT-0001', 'PAT-0002', 'PAT-0003', 'PAT-0004', 'PAT-0005')"))
    op.execute(sa.text("DELETE FROM users WHERE email IN ('john.doe@example.com', 'jane.smith@example.com', 'alice.brown@example.com')"))
