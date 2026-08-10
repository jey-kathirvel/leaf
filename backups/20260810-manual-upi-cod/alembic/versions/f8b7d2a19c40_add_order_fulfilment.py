"""add order fulfilment workflow

Revision ID: f8b7d2a19c40
Revises: c5a31e8f8c21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f8b7d2a19c40"
down_revision: Union[str, Sequence[str], None] = "c5a31e8f8c21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("courier_name", sa.String(100), nullable=True))
    op.add_column("orders", sa.Column("tracking_number", sa.String(150), nullable=True))
    op.add_column("orders", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("inventory_restored_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_orders_tracking_number", "orders", ["tracking_number"], unique=False)

    order_status = postgresql.ENUM(
        "PENDING", "CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED",
        name="order_status_enum", create_type=False,
    )
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("from_status", order_status, nullable=True),
        sa.Column("to_status", order_status, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_status_history_id", "order_status_history", ["id"], unique=False)
    op.create_index("ix_order_status_history_order_id", "order_status_history", ["order_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_order_status_history_order_id", table_name="order_status_history")
    op.drop_index("ix_order_status_history_id", table_name="order_status_history")
    op.drop_table("order_status_history")
    op.drop_index("ix_orders_tracking_number", table_name="orders")
    for column in ("inventory_restored_at", "returned_at", "cancelled_at", "delivered_at", "shipped_at", "status_changed_at", "tracking_number", "courier_name"):
        op.drop_column("orders", column)
