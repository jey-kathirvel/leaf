from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.main import app
from app.models import HomepageOfferCampaign
from app.services.offer_campaign_service import get_active_homepage_campaign
from tests.test_admin_operations import authenticated_admin_client
from tests.test_storefront import close_storefront_client, storefront_client


def test_homepage_shows_active_offer_campaign() -> None:
    client, db = storefront_client()
    try:
        db.add(
            HomepageOfferCampaign(
                title="Weekend Deal",
                message="Save on your order today.",
                coupon_code="LEAF15",
                iframe_url="https://example.com/offer",
                is_active=True,
                delay_seconds=5,
                auto_close_seconds=15,
            )
        )
        db.commit()

        response = client.get("/")
        assert response.status_code == 200
        assert "homepageOfferModal" in response.text
        assert "https://example.com/offer" in response.text
        assert "LEAF15" in response.text
        assert "homepage-offer.js" in response.text
    finally:
        close_storefront_client(db)


def test_inactive_offer_campaign_not_shown() -> None:
    client, db = storefront_client()
    try:
        db.add(
            HomepageOfferCampaign(
                iframe_url="https://example.com/offer",
                is_active=False,
            )
        )
        db.commit()

        response = client.get("/")
        assert response.status_code == 200
        assert "homepageOfferModal" not in response.text
    finally:
        close_storefront_client(db)


def test_offer_campaign_hidden_outside_schedule() -> None:
    client, db = storefront_client()
    try:
        now = datetime.now(timezone.utc)
        db.add(
            HomepageOfferCampaign(
                iframe_url="https://example.com/offer",
                is_active=True,
                ends_at=now - timedelta(minutes=5),
            )
        )
        db.commit()

        campaign = get_active_homepage_campaign(db)
        assert campaign is None
    finally:
        close_storefront_client(db)


def test_admin_offer_campaign_page_and_update() -> None:
    client, db = authenticated_admin_client()
    try:
        page = client.get("/admin/offer-campaign")
        assert page.status_code == 200
        assert "Homepage offer campaign" in page.text

        saved = client.post(
            "/admin/offer-campaign",
            data={
                "title": "Launch Offer",
                "message": "Limited time savings.",
                "coupon_code": "launch10",
                "iframe_url": "https://example.com/embed",
                "is_active": "on",
                "delay_seconds": 5,
                "auto_close_seconds": 15,
                "starts_at": "",
                "ends_at": "",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303

        campaign = db.scalar(select(HomepageOfferCampaign).limit(1))
        assert campaign is not None
        assert campaign.title == "Launch Offer"
        assert campaign.coupon_code == "LAUNCH10"
        assert campaign.iframe_url == "https://example.com/embed"
        assert campaign.is_active is True
    finally:
        app.dependency_overrides.clear()
        db.close()

