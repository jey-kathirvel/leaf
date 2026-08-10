from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.commerce import Category
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.product_service import ProductService


def database_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def payload(**changes) -> ProductCreate:
    values = {
        "product_name": "Organic Green Tea",
        "slug": "organic-green-tea",
        "sku": "TEA-001",
        "barcode": "8901234567895",
        "category_id": 1,
        "mrp": Decimal("250.00"),
        "selling_price": Decimal("199.00"),
        "cost_price": Decimal("110.00"),
        "gst_percentage": Decimal("5.00"),
        "track_inventory": True,
        "opening_stock": 25,
        "min_stock": 5,
        "max_stock": 100,
    }
    values.update(changes)
    return ProductCreate.model_validate(values)


def test_create_and_update_product_with_inventory() -> None:
    db = database_session()
    db.add(Category(name="Tea", slug="tea"))
    db.commit()

    product = ProductService.create_product(db, payload())

    assert product.name == "Organic Green Tea"
    assert product.product_name == "Organic Green Tea"
    assert product.price == Decimal("199.00")
    assert product.opening_stock == 25
    assert product.min_stock == 5
    assert product.max_stock == 100

    update_values = payload(
        product_name="Organic Green Tea Premium",
        opening_stock=40,
        min_stock=8,
        max_stock=120,
    ).model_dump()
    updated = ProductService.update_product(
        db,
        product.id,
        ProductUpdate.model_validate(update_values),
    )

    assert updated.name == "Organic Green Tea Premium"
    assert updated.inventory.quantity == 40
    assert updated.inventory.low_stock_threshold == 8
    assert updated.inventory.max_quantity == 120


def test_product_listing_searches_canonical_name() -> None:
    db = database_session()
    db.add(Category(name="Tea", slug="tea"))
    db.commit()
    ProductService.create_product(db, payload())

    result = ProductService.list_products(db, search="green")

    assert result.total == 1
    assert result.items[0].product_name == "Organic Green Tea"
