from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.deps import get_db
from app.main import app
from app.core.config import settings
from app.models import Category, Cart, Inventory, Order, PaymentStatus, Product
from app.services.product_service import ProductService
from tests.test_product_service import database_session, payload


def checkout_client():
    db = database_session()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app, base_url="https://testserver"), db


def test_cart_add_update_and_remove() -> None:
    client, db = checkout_client()
    try:
        db.add(Category(name="Tea", slug="tea"))
        db.commit()
        product = ProductService.create_product(db, payload(opening_stock=3))

        added = client.post(f"/cart/items/{product.id}", headers={"X-Requested-With": "XMLHttpRequest"})
        assert added.status_code == 200
        assert added.json()["count"] == 1
        assert product.name in client.get("/cart").text

        cart = db.scalar(select(Cart))
        item = cart.items[0]
        client.post(f"/cart/items/{item.id}/update", data={"quantity": 2})
        assert "₹398.00" in client.get("/cart").text

        client.post(f"/cart/items/{item.id}/remove")
        assert "Your cart is empty" in client.get("/cart").text
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_cod_checkout_creates_order_and_deducts_inventory() -> None:
    client, db = checkout_client()
    try:
        db.add(Category(name="Tea", slug="tea"))
        db.commit()
        product = ProductService.create_product(db, payload(opening_stock=5))
        client.post(f"/cart/items/{product.id}")

        response = client.post(
            "/checkout",
            data={
                "full_name": "Leaf Customer",
                "email": "customer@example.com",
                "mobile": "9876543210",
                "address_line1": "12 Green Street",
                "address_line2": "",
                "landmark": "",
                "city": "Chennai",
                "state": "Tamil Nadu",
                "pincode": "600001",
                "notes": "Call before delivery",
                "payment_method": "cash_on_delivery",
            },
            follow_redirects=True,
        )

        order = db.scalar(select(Order))
        inventory = db.scalar(select(Inventory).where(Inventory.product_id == product.id))
        assert response.status_code == 200
        assert "Thank you for your order" in response.text
        assert order.payment_method == "cash_on_delivery"
        assert order.grand_total == product.price
        assert inventory.quantity == 4
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_checkout_rejects_invalid_delivery_details() -> None:
    client, db = checkout_client()
    try:
        db.add(Category(name="Tea", slug="tea"))
        db.commit()
        product = ProductService.create_product(db, payload())
        client.post(f"/cart/items/{product.id}")
        response = client.post(
            "/checkout",
            data={"full_name": "A", "email": "bad", "mobile": "123", "address_line1": "", "city": "", "state": "", "pincode": "1", "payment_method": "cash_on_delivery"},
        )
        assert response.status_code == 422
        assert "full name" in response.text
        assert db.scalar(select(Order)) is None
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_product_can_disable_cod_for_the_entire_cart() -> None:
    client, db = checkout_client()
    try:
        db.add(Category(name="Prepaid", slug="prepaid"))
        db.commit()
        product = ProductService.create_product(db, payload(allow_cod=False))
        client.post(f"/cart/items/{product.id}")

        checkout = client.get("/checkout")
        assert "Cash on Delivery unavailable" in checkout.text

        response = client.post(
            "/checkout",
            data={
                "full_name": "Leaf Customer", "email": "prepaid@example.com",
                "mobile": "9876543210", "address_line1": "12 Green Street",
                "city": "Chennai", "state": "Tamil Nadu", "pincode": "600001",
                "payment_method": "cash_on_delivery",
            },
        )
        assert response.status_code == 422
        assert "not available for one or more items" in response.text
        assert db.scalar(select(Order)) is None
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_manual_upi_checkout_stays_payment_pending() -> None:
    client, db = checkout_client()
    original_enabled, original_vpa, original_name = settings.UPI_ENABLED, settings.UPI_VPA, settings.UPI_PAYEE_NAME
    settings.UPI_ENABLED, settings.UPI_VPA, settings.UPI_PAYEE_NAME = True, "leaf@upi", "Leaf Test Store"
    try:
        db.add(Category(name="UPI", slug="upi"))
        db.commit()
        product = ProductService.create_product(db, payload(allow_cod=False, opening_stock=2))
        client.post(f"/cart/items/{product.id}")
        response = client.post(
            "/checkout",
            data={
                "full_name": "UPI Customer", "email": "upi@example.com",
                "mobile": "9876543210", "address_line1": "12 Green Street",
                "city": "Chennai", "state": "Tamil Nadu", "pincode": "600001",
                "payment_method": "upi",
            },
            follow_redirects=True,
        )
        order = db.scalar(select(Order))
        assert response.status_code == 200
        assert "Payment pending" in response.text
        assert "Open UPI app" in response.text
        assert "leaf%40upi" in response.text
        assert order.payment_method == "upi"
        assert order.payment_status == PaymentStatus.PENDING
    finally:
        settings.UPI_ENABLED, settings.UPI_VPA, settings.UPI_PAYEE_NAME = original_enabled, original_vpa, original_name
        app.dependency_overrides.clear()
        db.close()
