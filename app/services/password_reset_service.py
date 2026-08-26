from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import secrets
import smtplib

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import PasswordResetToken
from app.models.commerce import Customer


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_reset_token(db: Session, customer: Customer) -> str:
    now = datetime.now(timezone.utc)
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.customer_id == customer.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw_token = secrets.token_urlsafe(40)
    db.add(
        PasswordResetToken(
            customer_id=customer.id,
            token_hash=_token_hash(raw_token),
            expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_MINUTES),
        )
    )
    db.commit()
    return raw_token


def get_valid_reset_token(db: Session, raw_token: str) -> PasswordResetToken | None:
    if not raw_token:
        return None
    now = datetime.now(timezone.utc)
    return db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == _token_hash(raw_token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
    )


def mark_token_used(db: Session, token: PasswordResetToken) -> None:
    token.used_at = datetime.now(timezone.utc)
    db.commit()


def send_reset_email(customer: Customer, raw_token: str) -> bool:
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        return False

    reset_url = f"{settings.BASE_URL.rstrip('/')}/reset-password?token={raw_token}"
    message = EmailMessage()
    message["Subject"] = "Reset your Leaf password"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = customer.email
    message.set_content(
        f"Hello {customer.first_name},\n\n"
        "We received a request to reset your Leaf password.\n\n"
        f"Open this link to choose a new password:\n{reset_url}\n\n"
        f"This link expires in {settings.PASSWORD_RESET_MINUTES} minutes and can be used only once.\n\n"
        "If you did not request this, you can ignore this email.\n\n"
        "Leaf Organic Store"
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)
    return True
