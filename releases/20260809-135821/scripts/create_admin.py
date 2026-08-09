import argparse

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import AdminUser


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--name",
        required=True,
    )

    parser.add_argument(
        "--email",
        required=True,
    )

    parser.add_argument(
        "--password",
        required=True,
    )

    args = parser.parse_args()

    normalized_email = args.email.strip().lower()

    with SessionLocal() as db:
        existing = db.scalar(
            select(AdminUser).where(
                func.lower(AdminUser.email)
                == normalized_email
            )
        )

        if existing:
            existing.full_name = args.name.strip()
            existing.password_hash = hash_password(
                args.password
            )
            existing.is_active = True

            db.commit()

            print("ADMIN_UPDATED")
            return

        admin = AdminUser(
            full_name=args.name.strip(),
            email=normalized_email,
            password_hash=hash_password(
                args.password
            ),
            role="super_admin",
            is_active=True,
        )

        db.add(admin)
        db.commit()

        print("ADMIN_CREATED")


if __name__ == "__main__":
    main()
