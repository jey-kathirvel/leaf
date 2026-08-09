import secrets
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.commerce import ProductImage
from app.services.product_service import ProductNotFoundError, ProductService


class ProductImageError(Exception):
    pass


class ProductImageNotFoundError(ProductImageError):
    pass


class ProductImageValidationError(ProductImageError):
    pass


class ProductImageService:
    MAX_IMAGES_PER_PRODUCT = 10
    ALLOWED_TYPES = {
        "image/jpeg": (".jpg", b"\xff\xd8\xff"),
        "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
        "image/webp": (".webp", b"RIFF"),
    }

    @classmethod
    async def upload(
        cls,
        db: Session,
        product_id: int,
        upload: UploadFile,
        alt_text: str | None = None,
    ) -> ProductImage:
        ProductService.get_by_id(db, product_id)

        image_count = int(
            db.scalar(
                select(func.count(ProductImage.id)).where(
                    ProductImage.product_id == product_id
                )
            )
            or 0
        )
        if image_count >= cls.MAX_IMAGES_PER_PRODUCT:
            raise ProductImageValidationError(
                f"A product can have at most {cls.MAX_IMAGES_PER_PRODUCT} images."
            )

        content_type = (upload.content_type or "").lower()
        if content_type not in cls.ALLOWED_TYPES:
            raise ProductImageValidationError(
                "Only JPEG, PNG and WebP images are allowed."
            )

        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        content = await upload.read(max_bytes + 1)
        if not content:
            raise ProductImageValidationError("The uploaded image is empty.")
        if len(content) > max_bytes:
            raise ProductImageValidationError(
                f"Images cannot exceed {settings.MAX_UPLOAD_SIZE_MB} MB."
            )

        suffix, signature = cls.ALLOWED_TYPES[content_type]
        if not content.startswith(signature):
            raise ProductImageValidationError(
                "The uploaded file content does not match its image type."
            )
        if content_type == "image/webp" and content[8:12] != b"WEBP":
            raise ProductImageValidationError("The uploaded WebP image is invalid.")

        product_dir = settings.UPLOAD_DIR / "products" / str(product_id)
        product_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{secrets.token_hex(16)}{suffix}"
        destination = product_dir / filename
        destination.write_bytes(content)

        max_sort = db.scalar(
            select(func.max(ProductImage.sort_order)).where(
                ProductImage.product_id == product_id
            )
        )
        image = ProductImage(
            product_id=product_id,
            image_path=f"/uploads/products/{product_id}/{filename}",
            alt_text=(alt_text or "").strip()[:250] or None,
            sort_order=int(max_sort or 0) + 1,
            is_primary=image_count == 0,
        )
        try:
            db.add(image)
            db.commit()
            db.refresh(image)
            return image
        except Exception:
            db.rollback()
            destination.unlink(missing_ok=True)
            raise

    @staticmethod
    def get_image(db: Session, product_id: int, image_id: int) -> ProductImage:
        image = db.scalar(
            select(ProductImage).where(
                ProductImage.id == image_id,
                ProductImage.product_id == product_id,
            )
        )
        if image is None:
            raise ProductImageNotFoundError("Product image was not found.")
        return image

    @classmethod
    def set_primary(cls, db: Session, product_id: int, image_id: int) -> None:
        image = cls.get_image(db, product_id, image_id)
        for item in db.scalars(
            select(ProductImage).where(ProductImage.product_id == product_id)
        ):
            item.is_primary = item.id == image.id
        db.commit()

    @classmethod
    def move(cls, db: Session, product_id: int, image_id: int, direction: str) -> None:
        image = cls.get_image(db, product_id, image_id)
        images = list(
            db.scalars(
                select(ProductImage)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.sort_order, ProductImage.id)
            ).all()
        )
        index = images.index(image)
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(images):
            images[index], images[target] = images[target], images[index]
            for position, item in enumerate(images, start=1):
                item.sort_order = position
            db.commit()

    @classmethod
    def delete(cls, db: Session, product_id: int, image_id: int) -> None:
        image = cls.get_image(db, product_id, image_id)
        was_primary = image.is_primary
        path = cls.disk_path(image.image_path)
        db.delete(image)
        db.flush()

        remaining = list(
            db.scalars(
                select(ProductImage)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.sort_order, ProductImage.id)
            ).all()
        )
        for position, item in enumerate(remaining, start=1):
            item.sort_order = position
        if was_primary and remaining:
            remaining[0].is_primary = True
        db.commit()
        path.unlink(missing_ok=True)

    @staticmethod
    def disk_path(image_path: str) -> Path:
        relative = image_path.removeprefix("/uploads/")
        candidate = (settings.UPLOAD_DIR / relative).resolve()
        root = settings.UPLOAD_DIR.resolve()
        if root not in candidate.parents:
            raise ProductImageValidationError("Invalid stored image path.")
        return candidate
