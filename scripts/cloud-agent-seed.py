"""Seed minimal storefront data for Cloud Agent development."""

from decimal import Decimal

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import AdminUser, Category, Product
from app.models.commerce import Inventory


def main() -> None:
    with SessionLocal() as db:
        admin_email = "admin@leaf.local"
        existing_admin = db.scalar(
            select(AdminUser).where(
                func.lower(AdminUser.email) == admin_email.lower()
            )
        )
        if existing_admin is None:
            db.add(
                AdminUser(
                    full_name="Leaf Admin",
                    email=admin_email,
                    password_hash=hash_password("admin12345"),
                    role="super_admin",
                    is_active=True,
                )
            )

        category = db.scalar(
            select(Category).where(Category.slug == "sample-teas")
        )
        if category is None:
            category = Category(
                name="Sample Teas",
                slug="sample-teas",
                description="Demo category for local development.",
                is_active=True,
                sort_order=1,
            )
            db.add(category)
            db.flush()

        product = db.scalar(
            select(Product).where(Product.slug == "organic-green-tea")
        )
        if product is None:
            product = Product(
                name="Organic Green Tea",
                slug="organic-green-tea",
                sku="TEA-001",
                barcode="8901234567895",
                category_id=category.id,
                compare_at_price=Decimal("250.00"),
                price=Decimal("199.00"),
                cost_price=Decimal("110.00"),
                tax_percentage=Decimal("5.00"),
                track_inventory=True,
                is_active=True,
                is_featured=True,
                allow_cod=True,
            )
            db.add(product)
            db.flush()
            db.add(
                Inventory(
                    product_id=product.id,
                    quantity=25,
                    reserved_quantity=0,
                    low_stock_threshold=5,
                    max_quantity=100,
                )
            )

        db.commit()


if __name__ == "__main__":
    main()
