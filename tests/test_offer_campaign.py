from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.main import app
from app.models import CouponDiscountType, HomepageOfferCampaign
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
        assert "homepageOfferTimer" in response.text
        assert "Closes in" in response.text
        assert "/static/images/sarees/silk-classics.jpg" in response.text
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


def test_homepage_uses_higher_priority_campaign() -> None:
    client, db = storefront_client()
    try:
        db.add_all(
            [
                HomepageOfferCampaign(
                    title="Low priority",
                    iframe_url="https://example.com/low",
                    is_active=True,
                    priority=1,
                ),
                HomepageOfferCampaign(
                    title="High priority",
                    iframe_url="https://example.com/high",
                    is_active=True,
                    priority=10,
                ),
            ]
        )
        db.commit()

        campaign = get_active_homepage_campaign(db)
        assert campaign is not None
        assert campaign.iframe_url == "https://example.com/high"
    finally:
        close_storefront_client(db)


def test_admin_offer_campaign_dashboard_and_create() -> None:
    client, db = authenticated_admin_client()
    try:
        page = client.get("/admin/offer-campaigns")
        assert page.status_code == 200
        assert "Offer campaigns" in page.text

        saved = client.post(
            "/admin/offer-campaigns",
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
                "priority": 5,
                "discount_type": "percent",
                "discount_value": "10",
                "min_order_amount": "",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303

        campaign = db.scalar(select(HomepageOfferCampaign).limit(1))
        assert campaign is not None
        assert campaign.title == "Launch Offer"
        assert campaign.coupon_code == "LAUNCH10"
        assert campaign.discount_type == CouponDiscountType.PERCENT
        assert campaign.discount_value == Decimal("10")

        updated = client.post(
            f"/admin/offer-campaigns/{campaign.id}",
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
                "priority": 5,
                "discount_type": "fixed",
                "discount_value": "25",
                "min_order_amount": "100",
            },
            follow_redirects=False,
        )
        assert updated.status_code == 303
        db.refresh(campaign)
        assert campaign.discount_type == CouponDiscountType.FIXED
        assert campaign.discount_value == Decimal("25")
        assert campaign.min_order_amount == Decimal("100")
    finally:
        app.dependency_overrides.clear()
        db.close()
