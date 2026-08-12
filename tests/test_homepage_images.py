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
            "silk-classics",
            upload_file(b"\xff\xd8\xffsilk-saree"),
            "Custom silk saree model",
        )
    )
    assert row.image_path.startswith("/uploads/homepage/silk-classics/")
    assert row.alt_text == "Custom silk saree model"

    media = HomepageImageService.media_map(db)
    assert media["silk-classics"].is_custom is True
    assert media["silk-classics"].url.startswith("/uploads/homepage/silk-classics/")
    assert "Custom silk saree model" in media["silk-classics"].alt

    HomepageImageService.remove(db, "silk-classics")
    media_after = HomepageImageService.media_map(db)
    assert media_after["silk-classics"].is_custom is False
    assert media_after["silk-classics"].url.endswith("silk-classics.jpg")
    assert db.scalar(
        __import__("sqlalchemy").select(HomepageImage).where(HomepageImage.slot_key == "silk-classics")
    ).image_path is None


def test_homepage_images_admin_page(monkeypatch) -> None:
    from tests.test_admin_operations import authenticated_admin_client

    client, db = authenticated_admin_client()
    try:
        page = client.get("/admin/homepage-images")
        assert page.status_code == 200
        assert "Homepage images" in page.text
        assert "Silk classics card" in page.text
        assert "hero-saree" in page.text
    finally:
        app.dependency_overrides.clear()
        db.close()


from app.main import app
