"""add product COD eligibility

Revision ID: a31d9c7e5b42
Revises: f8b7d2a19c40
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a31d9c7e5b42"
down_revision: Union[str, Sequence[str], None] = "f8b7d2a19c40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("allow_cod", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("products", "allow_cod")
