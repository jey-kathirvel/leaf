"""add homepage marketing images

Revision ID: d8f3a2c1e905
Revises: c7d2e9a1b804
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8f3a2c1e905"
down_revision: Union[str, Sequence[str], None] = "c7d2e9a1b804"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "homepage_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slot_key", sa.String(length=80), nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=True),
        sa.Column("alt_text", sa.String(length=250), nullable=True),
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
        sa.UniqueConstraint("slot_key"),
    )
    op.create_index(op.f("ix_homepage_images_id"), "homepage_images", ["id"], unique=False)
    op.create_index(op.f("ix_homepage_images_slot_key"), "homepage_images", ["slot_key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_homepage_images_slot_key"), table_name="homepage_images")
    op.drop_index(op.f("ix_homepage_images_id"), table_name="homepage_images")
    op.drop_table("homepage_images")
