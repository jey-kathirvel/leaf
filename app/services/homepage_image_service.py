from dataclasses import dataclass
from datetime import datetime

import secrets
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.commerce import HomepageImage


class HomepageImageError(Exception):
    pass


class HomepageImageValidationError(HomepageImageError):
    pass


class HomepageImageNotFoundError(HomepageImageError):
    pass


@dataclass(frozen=True)
class HomepageImageSlot:
    key: str
    label: str
    section: str
    default_path: str
    default_alt: str


HOMEPAGE_IMAGE_SLOTS: tuple[HomepageImageSlot, ...] = (
    HomepageImageSlot(
        "hero-saree",
        "Hero background",
        "Hero",
        "/static/images/sarees/hero-saree.jpg",
        "Indian woman in traditional saree",
    ),
    HomepageImageSlot(
        "silk-classics",
        "Silk classics card",
        "Hero collections",
        "/static/images/sarees/silk-classics.jpg",
        "Indian woman in silk saree",
    ),
    HomepageImageSlot(
        "cotton-comfort",
        "Cotton comfort card",
        "Hero collections",
        "/static/images/sarees/cotton-comfort.jpg",
        "Indian woman in cotton saree",
    ),
    HomepageImageSlot(
        "festive-edit",
        "Festive edit card",
        "Hero collections",
        "/static/images/sarees/festive-edit.jpg",
        "Indian woman in festive saree",
    ),
    HomepageImageSlot(
        "wedding-picks",
        "Wedding picks card",
        "Hero collections",
        "/static/images/sarees/wedding-picks.jpg",
        "Indian woman in wedding saree",
    ),
    HomepageImageSlot(
        "spotlight",
        "Saree spotlight",
        "Marketing",
        "/static/images/sarees/spotlight.jpg",
        "Indian woman in elegant saree",
    ),
    HomepageImageSlot(
        "occasion-wedding",
        "Occasion — wedding",
        "Shop by occasion",
        "/static/images/sarees/occasion-wedding.jpg",
        "Indian bride in wedding saree",
    ),
    HomepageImageSlot(
        "occasion-festive",
        "Occasion — festive",
        "Shop by occasion",
        "/static/images/sarees/occasion-festive.jpg",
        "Indian woman in festive saree",
    ),
    HomepageImageSlot(
        "occasion-everyday",
        "Occasion — everyday",
        "Shop by occasion",
        "/static/images/sarees/occasion-everyday.jpg",
        "Indian woman in everyday cotton saree",
    ),
    HomepageImageSlot(
        "occasion-gift",
        "Occasion — gifting",
        "Shop by occasion",
        "/static/images/sarees/occasion-gift.jpg",
        "Indian woman in saree — gift collection",
    ),
)

SLOT_BY_KEY = {slot.key: slot for slot in HOMEPAGE_IMAGE_SLOTS}


@dataclass
class HomepageMediaView:
    key: str
    label: str
    section: str
    url: str
    alt: str
    is_custom: bool
    updated_at: datetime | None


class HomepageImageService:
    ALLOWED_TYPES = {
        "image/jpeg": (".jpg", b"\xff\xd8\xff"),
        "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
        "image/webp": (".webp", b"RIFF"),
    }

    @classmethod
    def slot_keys(cls) -> set[str]:
        return set(SLOT_BY_KEY.keys())

    @classmethod
    def get_slot(cls, slot_key: str) -> HomepageImageSlot:
        slot = SLOT_BY_KEY.get(slot_key)
        if slot is None:
            raise HomepageImageNotFoundError("Unknown homepage image slot.")
        return slot

    @classmethod
    def list_admin_slots(cls, db: Session) -> list[HomepageMediaView]:
        stored = {
            row.slot_key: row
            for row in db.scalars(select(HomepageImage)).all()
        }
        views: list[HomepageMediaView] = []
        for slot in HOMEPAGE_IMAGE_SLOTS:
            views.append(cls._build_view(slot, stored.get(slot.key)))
        return views

    @classmethod
    def media_map(cls, db: Session) -> dict[str, HomepageMediaView]:
        return {view.key: view for view in cls.list_admin_slots(db)}

    @classmethod
    def _build_view(
        cls,
        slot: HomepageImageSlot,
        row: HomepageImage | None,
    ) -> HomepageMediaView:
        if row and row.image_path:
            version = int(row.updated_at.timestamp()) if row.updated_at else 0
            url = f"{row.image_path}?v={version}"
            alt = (row.alt_text or "").strip() or slot.default_alt
            return HomepageMediaView(
                key=slot.key,
                label=slot.label,
                section=slot.section,
                url=url,
                alt=alt,
                is_custom=True,
                updated_at=row.updated_at,
            )
        return HomepageMediaView(
            key=slot.key,
            label=slot.label,
            section=slot.section,
            url=slot.default_path,
            alt=slot.default_alt,
            is_custom=False,
            updated_at=None,
        )

    @classmethod
    async def upload(
        cls,
        db: Session,
        slot_key: str,
        upload: UploadFile,
        alt_text: str | None = None,
    ) -> HomepageImage:
        slot = cls.get_slot(slot_key)
        content_type = (upload.content_type or "").lower()
        if content_type not in cls.ALLOWED_TYPES:
            raise HomepageImageValidationError("Only JPEG, PNG and WebP images are allowed.")

        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        content = await upload.read(max_bytes + 1)
        if not content:
            raise HomepageImageValidationError("The uploaded image is empty.")
        if len(content) > max_bytes:
            raise HomepageImageValidationError(
                f"Images cannot exceed {settings.MAX_UPLOAD_SIZE_MB} MB."
            )

        suffix, signature = cls.ALLOWED_TYPES[content_type]
        if not content.startswith(signature):
            raise HomepageImageValidationError(
                "The uploaded file content does not match its image type."
            )
        if content_type == "image/webp" and content[8:12] != b"WEBP":
            raise HomepageImageValidationError("The uploaded WebP image is invalid.")

        row = db.scalar(select(HomepageImage).where(HomepageImage.slot_key == slot_key))
        if row is None:
            row = HomepageImage(slot_key=slot_key)
            db.add(row)

        old_path = row.image_path
        slot_dir = settings.UPLOAD_DIR / "homepage" / slot_key
        slot_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{secrets.token_hex(16)}{suffix}"
        destination = slot_dir / filename
        destination.write_bytes(content)

        row.image_path = f"/uploads/homepage/{slot_key}/{filename}"
        row.alt_text = (alt_text or "").strip()[:250] or slot.default_alt

        try:
            db.commit()
            db.refresh(row)
        except Exception:
            db.rollback()
            destination.unlink(missing_ok=True)
            raise

        if old_path and old_path.startswith("/uploads/"):
            cls.disk_path(old_path).unlink(missing_ok=True)
        return row

    @classmethod
    def remove(cls, db: Session, slot_key: str) -> None:
        slot = cls.get_slot(slot_key)
        row = db.scalar(select(HomepageImage).where(HomepageImage.slot_key == slot_key))
        if row is None or not row.image_path:
            return
        path = cls.disk_path(row.image_path)
        row.image_path = None
        row.alt_text = None
        db.commit()
        path.unlink(missing_ok=True)

    @staticmethod
    def disk_path(image_path: str) -> Path:
        relative = image_path.removeprefix("/uploads/")
        candidate = (settings.UPLOAD_DIR / relative).resolve()
        root = settings.UPLOAD_DIR.resolve()
        if root not in candidate.parents and candidate != root:
            raise HomepageImageValidationError("Invalid stored image path.")
        return candidate
