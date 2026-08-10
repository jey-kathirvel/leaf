import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.deps import get_db
from app.main import app
from app.models import Category, Customer
from app.services.checkout_service import add_item, get_or_create_cart, place_cod_order
from app.services.product_service import ProductService
from tests.test_product_service import database_session, payload


def account_client():
    db = database_session()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app, base_url="https://testserver"), db


def csrf_from(html: str) -> str:
    return re.search(r'name="csrf_token"\s+value="([^"]+)"', html).group(1)


def test_account_requires_customer_login() -> None:
    client, db = account_client()
    try:
        response = client.get("/account", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        assert client.get("/login").status_code == 200
        assert client.get("/register").status_code == 200
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_registration_claims_guest_orders_and_login_works() -> None:
    client, db = account_client()
    try:
        db.add(Category(name="Tea", slug="tea"))
        db.commit()
        product = ProductService.create_product(db, payload())
        cart = add_item(db, get_or_create_cart(db, None), product.id)
        order = place_cod_order(db, cart, {"full_name": "Leaf Customer", "email": "customer@example.com", "mobile": "9876543210", "address_line1": "12 Green Street", "address_line2": "", "landmark": "", "city": "Chennai", "state": "Tamil Nadu", "pincode": "600001", "notes": ""})

        register = client.get("/register")
        response = client.post("/register", data={"first_name": "Leaf", "last_name": "Customer", "email": "customer@example.com", "mobile": "9876543210", "password": "strong-password", "password_confirm": "strong-password", "csrf_token": csrf_from(register.text)}, follow_redirects=False)
        assert response.headers["location"] == "/account"
        account = client.get("/account")
        assert order.order_number in account.text
        assert client.get(f"/account/orders/{order.order_number}").status_code == 200

        client.post("/account/logout")
        login = client.get("/login")
        signed_in = client.post("/login", data={"email": "customer@example.com", "password": "strong-password", "csrf_token": csrf_from(login.text)}, follow_redirects=False)
        assert signed_in.headers["location"] == "/account"
        customer = db.scalar(select(Customer).where(Customer.email == "customer@example.com"))
        assert not customer.password_hash.startswith("guest:")
    finally:
        app.dependency_overrides.clear()
        db.close()
