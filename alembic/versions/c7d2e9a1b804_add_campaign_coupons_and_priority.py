"""add campaign coupons priority and order coupon code

Revision ID: c7d2e9a1b804
Revises: b4e8f1c2d903
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d2e9a1b804"
down_revision: Union[str, Sequence[str], None] = "b4e8f1c2d903"
branch_labels = None
depends_on = None

coupon_discount_type_enum = sa.Enum("percent", "fixed", name="coupon_discount_type_enum")


def upgrade() -> None:
    coupon_discount_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "homepage_offer_campaigns",
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "homepage_offer_campaigns",
        sa.Column("discount_type", coupon_discount_type_enum, nullable=True),
    )
    op.add_column(
        "homepage_offer_campaigns",
        sa.Column("discount_value", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "homepage_offer_campaigns",
        sa.Column("min_order_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column("orders", sa.Column("coupon_code", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "coupon_code")
    op.drop_column("homepage_offer_campaigns", "min_order_amount")
    op.drop_column("homepage_offer_campaigns", "discount_value")
    op.drop_column("homepage_offer_campaigns", "discount_type")
    op.drop_column("homepage_offer_campaigns", "priority")
    coupon_discount_type_enum.drop(op.get_bind(), checkfirst=True)
