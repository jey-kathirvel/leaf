from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CouponDiscountType, HomepageOfferCampaign
from app.services.offer_campaign_service import _as_utc, utc_now

MONEY = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def campaign_has_discount(campaign: HomepageOfferCampaign) -> bool:
    if campaign.discount_type is None or campaign.discount_value is None:
        return False
    if campaign.discount_value <= Decimal("0"):
        return False
    if campaign.discount_type == CouponDiscountType.PERCENT and campaign.discount_value > Decimal("100"):
        return False
    return True


def campaign_within_schedule(campaign: HomepageOfferCampaign) -> bool:
    now = utc_now()
    starts_at = _as_utc(campaign.starts_at)
    ends_at = _as_utc(campaign.ends_at)
    if starts_at is not None and now < starts_at:
        return False
    if ends_at is not None and now > ends_at:
        return False
    return True


def find_coupon_campaign(db: Session, code: str) -> HomepageOfferCampaign | None:
    clean = code.strip().upper()
    if not clean:
        return None
    campaigns = db.scalars(
        select(HomepageOfferCampaign)
        .where(func.upper(HomepageOfferCampaign.coupon_code) == clean)
        .order_by(HomepageOfferCampaign.priority.desc(), HomepageOfferCampaign.updated_at.desc())
    ).all()
    for campaign in campaigns:
        if not campaign_has_discount(campaign):
            continue
        if not campaign_within_schedule(campaign):
            continue
        return campaign
    return None


def compute_discount_amount(campaign: HomepageOfferCampaign, subtotal: Decimal) -> Decimal:
    if not campaign_has_discount(campaign):
        return Decimal("0.00")
    if campaign.min_order_amount is not None and subtotal < campaign.min_order_amount:
        return Decimal("0.00")

    if campaign.discount_type == CouponDiscountType.PERCENT:
        raw = subtotal * campaign.discount_value / Decimal("100")
    else:
        raw = campaign.discount_value

    return money(min(raw, subtotal))


def resolve_coupon(db: Session, code: str, subtotal: Decimal) -> tuple[HomepageOfferCampaign, Decimal]:
    campaign = find_coupon_campaign(db, code)
    if campaign is None:
        raise ValueError("That coupon code is not valid or has expired.")
    discount = compute_discount_amount(campaign, subtotal)
    if discount <= Decimal("0"):
        if campaign.min_order_amount is not None and subtotal < campaign.min_order_amount:
            raise ValueError(
                f"This coupon requires a minimum order of ₹{campaign.min_order_amount:.2f}."
            )
        raise ValueError("This coupon cannot be applied to your order.")
    return campaign, discount
