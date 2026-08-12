from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HomepageOfferCampaign


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_valid_iframe_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False
    return bool(parsed.netloc)


def get_active_homepage_campaign(db: Session) -> HomepageOfferCampaign | None:
    campaign = db.scalar(
        select(HomepageOfferCampaign)
        .where(HomepageOfferCampaign.is_active.is_(True))
        .order_by(HomepageOfferCampaign.updated_at.desc())
        .limit(1)
    )
    if campaign is None or not campaign.iframe_url.strip():
        return None
    if not is_valid_iframe_url(campaign.iframe_url):
        return None

    now = utc_now()
    starts_at = _as_utc(campaign.starts_at)
    ends_at = _as_utc(campaign.ends_at)
    if starts_at is not None and now < starts_at:
        return None
    if ends_at is not None and now > ends_at:
        return None
    return campaign


def get_or_create_campaign_settings(db: Session) -> HomepageOfferCampaign:
    campaign = db.scalar(
        select(HomepageOfferCampaign).order_by(HomepageOfferCampaign.id.asc()).limit(1)
    )
    if campaign is None:
        campaign = HomepageOfferCampaign(
            iframe_url="",
            is_active=False,
            delay_seconds=5,
            auto_close_seconds=15,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
    return campaign
