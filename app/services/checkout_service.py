from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from secrets import token_urlsafe

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Address,
    AddressType,
    Cart,
    CartItem,
    CartStatus,
    Customer,
    Inventory,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    PaymentStatus,
    Product,
)
from app.services.coupon_service import compute_discount_amount, find_coupon_campaign


MONEY = Decimal("0.01")


class CartError(ValueError):
    pass


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def load_cart(db: Session, token: str | None) -> Cart | None:
    if not token:
        return None
    return db.scalar(
        select(Cart)
        .options(
            selectinload(Cart.items).selectinload(CartItem.product).selectinload(Product.images),
            selectinload(Cart.items).selectinload(CartItem.product).selectinload(Product.inventory),
        )
        .where(Cart.session_token == token, Cart.status == CartStatus.ACTIVE)
    )


def get_or_create_cart(db: Session, token: str | None) -> Cart:
    cart = load_cart(db, token)
    if cart:
        return cart
    cart = Cart(
        session_token=token_urlsafe(32),
        status=CartStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(cart)
    db.commit()
    db.refresh(cart)
    return cart


def available_quantity(product: Product) -> int | None:
    if not product.track_inventory:
        return None
    if not product.inventory:
        return 0
    return max(product.inventory.quantity - product.inventory.reserved_quantity, 0)


def add_item(db: Session, cart: Cart, product_id: int, quantity: int = 1) -> Cart:
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.inventory))
        .where(Product.id == product_id, Product.is_active.is_(True), Product.deleted_at.is_(None))
    )
    if not product:
        raise CartError("This product is no longer available.")
    item = db.scalar(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == product.id))
    requested = (item.quantity if item else 0) + max(quantity, 1)
    available = available_quantity(product)
    if available is not None and requested > available:
        raise CartError(f"Only {available} item(s) are available.")
    if item:
        item.quantity = requested
        item.unit_price = product.price
    else:
        db.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=requested, unit_price=product.price))
    db.commit()
    return load_cart(db, cart.session_token)


def update_item(db: Session, cart: Cart, item_id: int, quantity: int) -> Cart:
    item = db.scalar(
        select(CartItem)
        .options(selectinload(CartItem.product).selectinload(Product.inventory))
        .where(CartItem.id == item_id, CartItem.cart_id == cart.id)
    )
    if not item:
        raise CartError("Cart item was not found.")
    if quantity <= 0:
        db.delete(item)
    else:
        available = available_quantity(item.product)
        if available is not None and quantity > available:
            raise CartError(f"Only {available} item(s) are available.")
        item.quantity = min(quantity, 99)
        item.unit_price = item.product.price
    db.commit()
    return load_cart(db, cart.session_token)


def remove_item(db: Session, cart: Cart, item_id: int) -> Cart:
    item = db.scalar(select(CartItem).where(CartItem.id == item_id, CartItem.cart_id == cart.id))
    if item:
        db.delete(item)
        db.commit()
    return load_cart(db, cart.session_token)


def cart_totals(cart: Cart | None, coupon_code: str | None = None, db: Session | None = None) -> dict[str, Decimal | int | str | None]:
    items = cart.items if cart else []
    subtotal = money(sum((item.unit_price * item.quantity for item in items), Decimal("0")))
    tax = money(
        sum(
            (
                item.unit_price * item.quantity * item.product.tax_percentage
                / (Decimal("100") + item.product.tax_percentage)
                if item.product.tax_percentage
                else Decimal("0")
                for item in items
            ),
            Decimal("0"),
        )
    )
    discount = Decimal("0.00")
    applied_code: str | None = None
    if coupon_code and db is not None and subtotal > Decimal("0"):
        campaign = find_coupon_campaign(db, coupon_code)
        if campaign is not None:
            discount = compute_discount_amount(campaign, subtotal)
            if discount > Decimal("0"):
                applied_code = campaign.coupon_code

    grand_total = money(max(subtotal - discount, Decimal("0")))
    return {
        "subtotal": subtotal,
        "tax": tax,
        "shipping": Decimal("0.00"),
        "discount": discount,
        "grand_total": grand_total,
        "count": sum(item.quantity for item in items),
        "coupon_code": applied_code,
    }


def cart_allows_cod(cart: Cart | None) -> bool:
    return bool(cart and cart.items) and all(item.product.allow_cod for item in cart.items)


def place_order(
    db: Session,
    cart: Cart,
    customer_data: dict[str, str],
    payment_method: str,
    coupon_code: str | None = None,
) -> Order:
    if not cart.items:
        raise CartError("Your cart is empty.")
    if payment_method not in {"cash_on_delivery", "upi"}:
        raise CartError("Choose a supported payment method.")
    if payment_method == "cash_on_delivery" and not cart_allows_cod(cart):
        raise CartError("Cash on Delivery is not available for one or more items in your cart.")

    locked_products: dict[int, Product] = {}
    for item in cart.items:
        product = db.scalar(
            select(Product)
            .options(selectinload(Product.inventory))
            .where(Product.id == item.product_id, Product.is_active.is_(True), Product.deleted_at.is_(None))
            .with_for_update()
        )
        if not product:
            raise CartError(f"{item.product.name} is no longer available.")
        available = available_quantity(product)
        if available is not None and item.quantity > available:
            raise CartError(f"Only {available} item(s) of {product.name} remain.")
        locked_products[product.id] = product

    email = customer_data["email"].strip().lower()
    customer = db.scalar(select(Customer).where(Customer.email == email))
    if not customer:
        customer = Customer(
            first_name=customer_data["full_name"].strip().split()[0],
            last_name=" ".join(customer_data["full_name"].strip().split()[1:]) or None,
            email=email,
            mobile=None,
            password_hash=f"guest:{token_urlsafe(24)}",
            is_active=True,
        )
        db.add(customer)
        db.flush()

    address = Address(
        customer_id=customer.id,
        address_type=AddressType.SHIPPING,
        full_name=customer_data["full_name"].strip(),
        mobile=customer_data["mobile"].strip(),
        address_line1=customer_data["address_line1"].strip(),
        address_line2=customer_data.get("address_line2", "").strip() or None,
        landmark=customer_data.get("landmark", "").strip() or None,
        city=customer_data["city"].strip(),
        state=customer_data["state"].strip(),
        country="India",
        pincode=customer_data["pincode"].strip(),
    )
    db.add(address)
    db.flush()

    totals = cart_totals(cart, coupon_code=coupon_code, db=db)
    order = Order(
        order_number=f"LF{datetime.now(timezone.utc):%y%m%d}{token_urlsafe(5).replace('-', '').replace('_', '').upper()[:7]}",
        customer_id=customer.id,
        shipping_address_id=address.id,
        billing_address_id=address.id,
        status=OrderStatus.CONFIRMED,
        payment_status=PaymentStatus.PENDING,
        payment_method=payment_method,
        subtotal=totals["subtotal"],
        tax_amount=totals["tax"],
        shipping_amount=totals["shipping"],
        discount_amount=totals["discount"],
        coupon_code=totals["coupon_code"],
        grand_total=totals["grand_total"],
        customer_notes=customer_data.get("notes", "").strip() or None,
    )
    db.add(order)
    db.flush()
    payment_note = "Cash on Delivery" if payment_method == "cash_on_delivery" else "UPI payment pending external confirmation"
    db.add(OrderStatusHistory(order_id=order.id, from_status=None, to_status=OrderStatus.CONFIRMED, note=f"Order placed by customer · {payment_note}"))

    for item in cart.items:
        product = locked_products[item.product_id]
        line_total = money(product.price * item.quantity)
        line_tax = money(
            line_total * product.tax_percentage / (Decimal("100") + product.tax_percentage)
            if product.tax_percentage else Decimal("0")
        )
        db.add(OrderItem(order_id=order.id, product_id=product.id, product_name=product.name, sku=product.sku, quantity=item.quantity, unit_price=product.price, tax_amount=line_tax, total_amount=line_total))
        if product.track_inventory:
            product.inventory.quantity -= item.quantity

    cart.status = CartStatus.CONVERTED
    cart.customer_id = customer.id
    db.commit()
    db.refresh(order)
    return order


def place_cod_order(db: Session, cart: Cart, customer_data: dict[str, str], coupon_code: str | None = None) -> Order:
    return place_order(db, cart, customer_data, "cash_on_delivery", coupon_code=coupon_code)
