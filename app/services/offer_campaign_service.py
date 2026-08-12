from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HomepageOfferCampaign

CAMPAIGN_SCHEDULE_TZ = ZoneInfo("Asia/Kolkata")


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


def campaign_within_schedule(campaign: HomepageOfferCampaign) -> bool:
    now = utc_now()
    starts_at = _as_utc(campaign.starts_at)
    ends_at = _as_utc(campaign.ends_at)
    if starts_at is not None and now < starts_at:
        return False
    if ends_at is not None and now > ends_at:
        return False
    return True


def get_active_homepage_campaign(db: Session) -> HomepageOfferCampaign | None:
    campaigns = db.scalars(
        select(HomepageOfferCampaign)
        .where(HomepageOfferCampaign.is_active.is_(True))
        .order_by(HomepageOfferCampaign.priority.desc(), HomepageOfferCampaign.updated_at.desc())
    ).all()
    for campaign in campaigns:
        if not campaign.iframe_url.strip():
            continue
        if not is_valid_iframe_url(campaign.iframe_url):
            continue
        if not campaign_within_schedule(campaign):
            continue
        return campaign
    return None


def list_campaigns(db: Session) -> list[HomepageOfferCampaign]:
    return list(
        db.scalars(
            select(HomepageOfferCampaign)
            .order_by(HomepageOfferCampaign.priority.desc(), HomepageOfferCampaign.id.desc())
        ).all()
    )


def get_campaign(db: Session, campaign_id: int) -> HomepageOfferCampaign | None:
    return db.get(HomepageOfferCampaign, campaign_id)


def parse_campaign_schedule_input(value: str) -> datetime | None:
    clean = value.strip()
    if not clean:
        return None
    try:
        parsed = datetime.fromisoformat(clean)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CAMPAIGN_SCHEDULE_TZ)
    return parsed.astimezone(timezone.utc)


def format_campaign_schedule_for_input(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(CAMPAIGN_SCHEDULE_TZ).strftime("%Y-%m-%dT%H:%M")


def parse_discount_type(value: str) -> str | None:
    clean = value.strip().lower()
    if clean in {"", "none"}:
        return None
    if clean in {"percent", "fixed"}:
        return clean
    return None
