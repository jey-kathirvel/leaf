import pytest

from app.models import Category, OrderStatus
from app.services.checkout_service import add_item, get_or_create_cart, place_cod_order
from app.services.order_service import OrderWorkflowError, update_fulfilment
from app.services.product_service import ProductService
from tests.test_product_service import database_session, payload


CUSTOMER = {
    "full_name": "Leaf Customer",
    "email": "orders@example.com",
    "mobile": "9876543210",
    "address_line1": "12 Green Street",
    "address_line2": "",
    "landmark": "",
    "city": "Chennai",
    "state": "Tamil Nadu",
    "pincode": "600001",
    "notes": "",
}


def seeded_order():
    db = database_session()
    db.add(Category(name="Tea", slug="tea"))
    db.commit()
    product = ProductService.create_product(db, payload(opening_stock=5))
    cart = get_or_create_cart(db, None)
    cart = add_item(db, cart, product.id)
    order = place_cod_order(db, cart, CUSTOMER)
    return db, product, order


def test_order_moves_through_fulfilment_with_tracking() -> None:
    db, _, order = seeded_order()
    try:
        update_fulfilment(db, order.id, "processing", internal_notes="Pack carefully")
        with pytest.raises(OrderWorkflowError, match="Courier name"):
            update_fulfilment(db, order.id, "shipped")
        shipped = update_fulfilment(db, order.id, "shipped", courier_name="BlueDart", tracking_number="TRACK123", status_note="Collected")
        delivered = update_fulfilment(db, order.id, "delivered", courier_name="BlueDart", tracking_number="TRACK123")
        assert shipped.shipped_at is not None
        assert delivered.status == OrderStatus.DELIVERED
        assert delivered.delivered_at is not None
        assert len(delivered.status_history) == 4
    finally:
        db.close()


def test_cancellation_restores_inventory_once() -> None:
    db, product, order = seeded_order()
    try:
        assert product.inventory.quantity == 4
        cancelled = update_fulfilment(db, order.id, "cancelled", status_note="Customer requested cancellation")
        assert cancelled.inventory_restored_at is not None
        assert product.inventory.quantity == 5
        with pytest.raises(OrderWorkflowError):
            update_fulfilment(db, order.id, "processing")
        assert product.inventory.quantity == 5
    finally:
        db.close()


def test_invalid_status_jump_is_rejected() -> None:
    db, _, order = seeded_order()
    try:
        with pytest.raises(OrderWorkflowError, match="cannot move"):
            update_fulfilment(db, order.id, "delivered")
    finally:
        db.close()


def test_cancellation_does_not_create_stock_for_untracked_product() -> None:
    db = database_session()
    try:
        db.add(Category(name="Tea", slug="tea"))
        db.commit()
        product = ProductService.create_product(db, payload(opening_stock=0, track_inventory=False))
        cart = get_or_create_cart(db, None)
        order = place_cod_order(db, add_item(db, cart, product.id), CUSTOMER)
        update_fulfilment(db, order.id, "cancelled")
        assert product.inventory.quantity == 0
    finally:
        db.close()
