import asyncio
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from starlette.datastructures import Headers, UploadFile

from app.core.config import settings
from app.models.commerce import Category, ProductImage
from app.services.product_image_service import (
    ProductImageService,
    ProductImageValidationError,
)
from app.services.product_service import ProductService
from tests.test_product_service import database_session, payload


def upload_file(content: bytes, content_type: str = "image/jpeg") -> UploadFile:
    return UploadFile(
        BytesIO(content),
        filename="product.jpg",
        headers=Headers({"content-type": content_type}),
    )


def isolated_upload_dir() -> Path:
    return Path("test-uploads") / uuid4().hex


def test_upload_primary_order_and_delete(monkeypatch) -> None:
    upload_dir = isolated_upload_dir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", upload_dir)
    db = database_session()
    db.add(Category(name="Tea", slug="tea"))
    db.commit()
    product = ProductService.create_product(db, payload())

    first = asyncio.run(
        ProductImageService.upload(
            db,
            product.id,
            upload_file(b"\xff\xd8\xfffirst-image"),
            "Front of tea box",
        )
    )
    second = asyncio.run(
        ProductImageService.upload(
            db,
            product.id,
            upload_file(b"\xff\xd8\xffsecond-image"),
            "Back of tea box",
        )
    )

    assert first.is_primary is True
    assert second.is_primary is False
    assert (upload_dir / first.image_path.removeprefix("/uploads/")).exists()

    ProductImageService.set_primary(db, product.id, second.id)
    db.refresh(first)
    db.refresh(second)
    assert second.is_primary is True
    assert first.is_primary is False

    ProductImageService.move(db, product.id, second.id, "up")
    ordered = db.query(ProductImage).order_by(ProductImage.sort_order).all()
    assert [item.id for item in ordered] == [second.id, first.id]

    ProductImageService.delete(db, product.id, second.id)
    db.refresh(first)
    assert first.is_primary is True
    assert db.get(ProductImage, second.id) is None


def test_upload_rejects_content_type_spoofing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIR", isolated_upload_dir())
    db = database_session()
    db.add(Category(name="Tea", slug="tea"))
    db.commit()
    product = ProductService.create_product(db, payload())

    with pytest.raises(ProductImageValidationError):
        asyncio.run(
            ProductImageService.upload(
                db,
                product.id,
                upload_file(b"this-is-not-a-jpeg"),
            )
        )
