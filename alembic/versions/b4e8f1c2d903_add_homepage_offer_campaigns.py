"""add homepage offer campaigns

Revision ID: b4e8f1c2d903
Revises: a31d9c7e5b42
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4e8f1c2d903"
down_revision: Union[str, Sequence[str], None] = "a31d9c7e5b42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "homepage_offer_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("coupon_code", sa.String(length=80), nullable=True),
        sa.Column("iframe_url", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("delay_seconds", sa.Integer(), server_default="5", nullable=False),
        sa.Column("auto_close_seconds", sa.Integer(), server_default="15", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_homepage_offer_campaigns_id"),
        "homepage_offer_campaigns",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_homepage_offer_campaigns_id"),
        table_name="homepage_offer_campaigns",
    )
    op.drop_table("homepage_offer_campaigns")
