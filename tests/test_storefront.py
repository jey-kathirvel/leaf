from fastapi.testclient import TestClient

from app.db.deps import get_db
from app.main import app
from app.models.commerce import Category
from app.services.product_service import ProductService
from tests.test_product_service import database_session, payload


def storefront_client():
    db = database_session()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), db


def close_storefront_client(db) -> None:
    app.dependency_overrides.clear()
    db.close()


def test_storefront_empty_catalogue_pages_render() -> None:
    client, db = storefront_client()
    try:
        assert client.get("/").status_code == 200
        assert client.get("/shop").status_code == 200
        assert client.get("/categories").status_code == 200
        assert client.get("/contact").status_code == 200
        assert client.get("/offers", follow_redirects=False).headers["location"] == "/shop?featured=true"
        assert client.get("/product/missing").status_code == 404
    finally:
        close_storefront_client(db)


def test_catalogue_search_category_and_product_detail() -> None:
    client, db = storefront_client()
    try:
        db.add(Category(name="Tea", slug="tea"))
        db.commit()
        ProductService.create_product(
            db,
            payload(is_featured=True, short_description="A clean everyday brew"),
        )

        home = client.get("/")
        search = client.get("/shop?q=green")
        category = client.get("/shop?category=tea")
        detail = client.get("/product/organic-green-tea")
        categories = client.get("/categories")

        assert "Organic Green Tea" in home.text
        assert "Organic Green Tea" in search.text
        assert "Organic Green Tea" in category.text
        assert detail.status_code == 200
        assert "A clean everyday brew" in detail.text
        assert "Tea" in categories.text
    finally:
        close_storefront_client(db)
