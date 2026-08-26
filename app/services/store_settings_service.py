from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import StoreSettings


def get_store_settings(db: Session) -> StoreSettings:
    settings = db.get(StoreSettings, 1)
    if settings is None:
        settings = StoreSettings(id=1)
        db.add(settings)
        db.flush()
    return settings


def effective_tax_rate(settings: StoreSettings, product_rate: Decimal | None) -> Decimal:
    if not settings.tax_enabled:
        return Decimal("0.00")
    rate = product_rate or Decimal("0.00")
    if rate <= 0:
        rate = settings.default_tax_percentage or Decimal("0.00")
    return max(Decimal("0.00"), rate)
