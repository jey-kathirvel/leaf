"""add store shipping and tax settings

Revision ID: e2a4b6c8d010
Revises: d8f3a2c1e905
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e2a4b6c8d010"
down_revision: Union[str, Sequence[str], None] = "d8f3a2c1e905"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "store_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shipping_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("flat_shipping_amount", sa.Numeric(12, 2), server_default="0.00", nullable=False),
        sa.Column("free_shipping_threshold", sa.Numeric(12, 2), server_default="0.00", nullable=False),
        sa.Column("delivery_eta_min_days", sa.Integer(), server_default="3", nullable=False),
        sa.Column("delivery_eta_max_days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("tax_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("default_tax_percentage", sa.Numeric(5, 2), server_default="0.00", nullable=False),
        sa.Column("prices_include_tax", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("""
        INSERT INTO store_settings
            (id, shipping_enabled, flat_shipping_amount, free_shipping_threshold,
             delivery_eta_min_days, delivery_eta_max_days, tax_enabled,
             default_tax_percentage, prices_include_tax)
        VALUES (1, true, 0.00, 0.00, 3, 7, true, 0.00, true)
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("store_settings")
