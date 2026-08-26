from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AdminUser(Base, TimestampMixin):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="super_admin", server_default="super_admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class StoreSettings(Base, TimestampMixin):
    """Singleton store-wide checkout configuration (row id=1)."""

    __tablename__ = "store_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    shipping_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    flat_shipping_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    free_shipping_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    delivery_eta_min_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    delivery_eta_max_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7, server_default="7")

    tax_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    default_tax_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    prices_include_tax: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
