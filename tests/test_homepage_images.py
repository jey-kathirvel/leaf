import asyncio
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from starlette.datastructures import Headers, UploadFile

from app.core.config import settings
from app.models.commerce import HomepageImage
from app.services.homepage_image_service import HomepageImageService
from tests.test_product_service import database_session


def upload_file(content: bytes, content_type: str = "image/jpeg") -> UploadFile:
    return UploadFile(
        BytesIO(content),
        filename="homepage.jpg",
        headers=Headers({"content-type": content_type}),
    )


def isolated_upload_dir() -> Path:
    return Path("test-uploads") / uuid4().hex


def test_homepage_image_upload_and_remove(monkeypatch) -> None:
    upload_dir = isolated_upload_dir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", upload_dir)
    db = database_session()

    row = asyncio.run(
        HomepageImageService.upload(
            db,
            "pantry-essentials",
            upload_file(b"\xff\xd8\xffpantry-organic"),
            "Custom organic pantry display",
        )
    )
    assert row.image_path.startswith("/uploads/homepage/pantry-essentials/")
    assert row.alt_text == "Custom organic pantry display"

    media = HomepageImageService.media_map(db)
    assert media["pantry-essentials"].is_custom is True
    assert media["pantry-essentials"].url.startswith("/uploads/homepage/pantry-essentials/")
    assert "Custom organic pantry display" in media["pantry-essentials"].alt

    HomepageImageService.remove(db, "pantry-essentials")
    media_after = HomepageImageService.media_map(db)
    assert media_after["pantry-essentials"].is_custom is False
    assert media_after["pantry-essentials"].url.endswith("pantry-essentials.jpg")
    assert db.scalar(
        __import__("sqlalchemy").select(HomepageImage).where(HomepageImage.slot_key == "pantry-essentials")
    ).image_path is None


def test_homepage_images_admin_page(monkeypatch) -> None:
    from tests.test_admin_operations import authenticated_admin_client

    client, db = authenticated_admin_client()
    try:
        page = client.get("/admin/homepage-images")
        assert page.status_code == 200
        assert "Homepage images" in page.text
        assert "Pantry classics card" in page.text
        assert "hero-organic" in page.text
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_homepage_image_admin_upload(monkeypatch) -> None:
    from io import BytesIO

    from tests.test_admin_operations import authenticated_admin_client

    upload_dir = isolated_upload_dir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", upload_dir)
    client, db = authenticated_admin_client()
    try:
        response = client.post(
            "/admin/homepage-images/hero-organic",
            files={"image": ("hero.jpg", BytesIO(b"\xff\xd8\xffhero"), "image/jpeg")},
            data={"alt_text": "Uploaded hero organic"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/homepage-images#hero-organic"

        page = client.get("/admin/homepage-images")
        assert "Your image" in page.text
        assert "Uploaded hero organic" in page.text

        media = HomepageImageService.media_map(db)
        assert media["hero-organic"].is_custom is True
        assert media["hero-organic"].url.startswith("/uploads/homepage/hero-organic/")
    finally:
        app.dependency_overrides.clear()
        db.close()


from app.main import app
