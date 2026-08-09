import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.db.deps import get_db
from app.main import app
from app.models import AdminUser, Category, Customer, Inventory
from app.services.product_service import ProductService
from tests.test_product_service import database_session, payload


def authenticated_admin_client():
    db = database_session()
    db.add(AdminUser(full_name="Leaf Admin", email="admin@test.local", password_hash=hash_password("strong-password"), role="super_admin", is_active=True))
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app, base_url="https://testserver")
    login = client.get("/admin/login")
    csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', login.text).group(1)
    response = client.post("/admin/login", data={"email": "admin@test.local", "password": "strong-password", "csrf_token": csrf}, follow_redirects=False)
    assert response.status_code == 303
    return client, db


def test_missing_admin_modules_render_and_update_data() -> None:
    client, db = authenticated_admin_client()
    try:
        assert client.get("/admin/categories").status_code == 200
        created = client.post("/admin/categories", data={"name": "Wellness", "slug": "", "description": "Healthy products", "sort_order": 1}, follow_redirects=False)
        assert created.status_code == 303
        category = db.scalar(select(Category).where(Category.slug == "wellness"))
        product = ProductService.create_product(db, payload(category_id=category.id, opening_stock=8))

        inventory_page = client.get("/admin/inventory")
        assert inventory_page.status_code == 200
        assert product.name in inventory_page.text
        inventory = db.scalar(select(Inventory).where(Inventory.product_id == product.id))
        client.post(f"/admin/inventory/{inventory.id}/update", data={"quantity": 12, "low_stock_threshold": 3, "max_quantity": 50})
        db.refresh(inventory)
        assert inventory.quantity == 12

        customer = Customer(first_name="Guest", email="guest@example.com", password_hash="guest:test", is_active=True)
        db.add(customer)
        db.commit()
        assert client.get("/admin/customers").status_code == 200
        assert client.get(f"/admin/customers/{customer.id}").status_code == 200
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_admin_operations_require_login() -> None:
    client = TestClient(app, base_url="https://testserver")
    for path in ("/admin/categories", "/admin/inventory", "/admin/customers"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
