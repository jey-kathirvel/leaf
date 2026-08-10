from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Inventory, Order, OrderStatus, OrderStatusHistory, Product


class OrderWorkflowError(ValueError):
    pass


ALLOWED_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: {OrderStatus.RETURNED},
    OrderStatus.CANCELLED: set(),
    OrderStatus.RETURNED: set(),
}


def allowed_next_statuses(status: OrderStatus) -> list[OrderStatus]:
    return sorted(ALLOWED_TRANSITIONS.get(status, set()), key=lambda value: value.value)


def update_fulfilment(
    db: Session,
    order_id: int,
    target_status: str,
    courier_name: str = "",
    tracking_number: str = "",
    internal_notes: str = "",
    status_note: str = "",
) -> Order:
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
        .with_for_update()
    )
    if not order:
        raise OrderWorkflowError("Order was not found.")
    try:
        new_status = OrderStatus(target_status)
    except ValueError as exc:
        raise OrderWorkflowError("Invalid order status.") from exc

    old_status = order.status
    if new_status != old_status and new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
        raise OrderWorkflowError(f"An order cannot move from {old_status.value} to {new_status.value}.")
    if new_status == OrderStatus.SHIPPED and (not courier_name.strip() or not tracking_number.strip()):
        raise OrderWorkflowError("Courier name and tracking number are required before shipping.")

    order.courier_name = courier_name.strip() or order.courier_name
    order.tracking_number = tracking_number.strip() or order.tracking_number
    order.internal_notes = internal_notes.strip() or None

    if new_status != old_status:
        now = datetime.now(timezone.utc)
        order.status = new_status
        order.status_changed_at = now
        if new_status == OrderStatus.SHIPPED:
            order.shipped_at = now
        elif new_status == OrderStatus.DELIVERED:
            order.delivered_at = now
        elif new_status == OrderStatus.CANCELLED:
            order.cancelled_at = now
        elif new_status == OrderStatus.RETURNED:
            order.returned_at = now

        db.add(OrderStatusHistory(order_id=order.id, from_status=old_status, to_status=new_status, note=status_note.strip() or None))

        if new_status in {OrderStatus.CANCELLED, OrderStatus.RETURNED} and order.inventory_restored_at is None:
            for item in order.items:
                if not item.product_id:
                    continue
                tracks_inventory = db.scalar(select(Product.track_inventory).where(Product.id == item.product_id))
                if not tracks_inventory:
                    continue
                inventory = db.scalar(select(Inventory).where(Inventory.product_id == item.product_id).with_for_update())
                if inventory:
                    inventory.quantity += item.quantity
            order.inventory_restored_at = now

    db.commit()
    db.refresh(order)
    return order
