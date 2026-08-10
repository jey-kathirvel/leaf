"""stabilize product inventory

Revision ID: c5a31e8f8c21
Revises: 7b3fe58d1bf4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5a31e8f8c21"
down_revision: Union[str, Sequence[str], None] = "7b3fe58d1bf4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "track_inventory",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "inventory",
        sa.Column(
            "max_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    # Preserve thresholds entered through the earlier product form before
    # removing the duplicate columns from products.
    op.execute(
        """
        UPDATE inventory AS i
        SET low_stock_threshold = p.min_stock,
            max_quantity = p.max_stock
        FROM products AS p
        WHERE i.product_id = p.id
        """
    )

    # The obsolete duplicate columns are intentionally retained in this
    # stabilization release. The application no longer maps or writes them,
    # and a later maintenance migration can remove them after production data
    # has been reviewed. This makes the production upgrade non-destructive.


def downgrade() -> None:
    op.drop_column("inventory", "max_quantity")
    op.drop_column("products", "track_inventory")
