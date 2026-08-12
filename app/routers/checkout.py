import re
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.services.checkout_service import (
    CartError,
    add_item,
    cart_totals,
    cart_allows_cod,
    get_or_create_cart,
    load_cart,
    place_order,
    remove_item,
    update_item,
)
from app.services.coupon_service import resolve_coupon
from app.services.upi_service import payment_details, upi_is_available


router = APIRouter(tags=["Checkout"])
templates = Jinja2Templates(directory="app/templates")


def applied_coupon_code(request: Request) -> str | None:
    code = request.session.get("coupon_code")
    if code and isinstance(code, str):
        clean = code.strip().upper()
        return clean or None
    return None


def context(request: Request, cart=None, db: Session | None = None, **values):
    coupon_code = applied_coupon_code(request)
    totals = cart_totals(cart, coupon_code=coupon_code, db=db)
    return {
        "request": request,
        "current_year": datetime.now().year,
        "cart": cart,
        "totals": totals,
        "cart_count": totals["count"],
        "cod_available": cart_allows_cod(cart),
        "upi_available": upi_is_available(),
        "applied_coupon": totals["coupon_code"],
        **values,
    }


def session_cart(request: Request, db: Session, create: bool = False):
    token = request.session.get("cart_token")
    cart = get_or_create_cart(db, token) if create else load_cart(db, token)
    if cart and cart.session_token != token:
        request.session["cart_token"] = cart.session_token
    return cart


@router.get("/cart", response_class=HTMLResponse)
def cart_page(request: Request, db: Session = Depends(get_db)):
    cart = session_cart(request, db)
    request.session["cart_count"] = cart_totals(cart, db=db)["count"]
    return templates.TemplateResponse(request, "store/cart.html", context(request, cart, db=db))


@router.post("/cart/items/{product_id}")
def cart_add(product_id: int, request: Request, db: Session = Depends(get_db)):
    cart = session_cart(request, db, create=True)
    try:
        cart = add_item(db, cart, product_id)
        totals = cart_totals(cart, coupon_code=applied_coupon_code(request), db=db)
        request.session["cart_count"] = totals["count"]
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JSONResponse({"ok": True, "count": totals["count"], "message": "Added to cart"})
        return RedirectResponse("/cart", status_code=303)
    except CartError as exc:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)
        request.session["cart_error"] = str(exc)
        return RedirectResponse("/cart", status_code=303)


@router.post("/cart/items/{item_id}/update")
def cart_update(item_id: int, request: Request, quantity: int = Form(...), db: Session = Depends(get_db)):
    cart = session_cart(request, db)
    if cart:
        try:
            cart = update_item(db, cart, item_id, quantity)
            request.session["cart_count"] = cart_totals(cart, db=db)["count"]
        except CartError as exc:
            request.session["cart_error"] = str(exc)
    return RedirectResponse("/cart", status_code=303)


@router.post("/cart/items/{item_id}/remove")
def cart_remove(item_id: int, request: Request, db: Session = Depends(get_db)):
    cart = session_cart(request, db)
    if cart:
        cart = remove_item(db, cart, item_id)
        request.session["cart_count"] = cart_totals(cart, db=db)["count"]
    return RedirectResponse("/cart", status_code=303)


@router.post("/checkout/coupon")
def checkout_apply_coupon(
    request: Request,
    coupon_code: str = Form(...),
    db: Session = Depends(get_db),
):
    cart = session_cart(request, db)
    if not cart or not cart.items:
        return RedirectResponse("/cart", status_code=303)

    code = coupon_code.strip().upper()
    subtotal = cart_totals(cart, db=db)["subtotal"]
    try:
        resolve_coupon(db, code, subtotal)
        request.session["coupon_code"] = code
        request.session.pop("coupon_error", None)
        request.session["coupon_message"] = f"Coupon {code} applied."
    except ValueError as exc:
        request.session.pop("coupon_code", None)
        request.session["coupon_error"] = str(exc)

    redirect_to = request.headers.get("referer") or "/checkout"
    if not redirect_to.endswith("/checkout") and not redirect_to.endswith("/cart"):
        redirect_to = "/checkout"
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/checkout/coupon/remove")
def checkout_remove_coupon(request: Request, db: Session = Depends(get_db)):
    request.session.pop("coupon_code", None)
    request.session.pop("coupon_error", None)
    request.session.pop("coupon_message", None)
    redirect_to = request.headers.get("referer") or "/checkout"
    return RedirectResponse(redirect_to, status_code=303)


@router.get("/checkout", response_class=HTMLResponse)
def checkout_page(request: Request, db: Session = Depends(get_db)):
    cart = session_cart(request, db)
    if not cart or not cart.items:
        return RedirectResponse("/cart", status_code=303)
    coupon_error = request.session.pop("coupon_error", None)
    coupon_message = request.session.pop("coupon_message", None)
    return templates.TemplateResponse(
        request,
        "store/checkout.html",
        context(
            request,
            cart,
            db=db,
            error=None,
            form={},
            coupon_error=coupon_error,
            coupon_message=coupon_message,
        ),
    )


@router.post("/checkout", response_class=HTMLResponse)
def checkout_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    mobile: str = Form(...),
    address_line1: str = Form(...),
    address_line2: str = Form(""),
    landmark: str = Form(""),
    city: str = Form(...),
    state: str = Form(...),
    pincode: str = Form(...),
    notes: str = Form(""),
    payment_method: str = Form("cash_on_delivery"),
    db: Session = Depends(get_db),
):
    cart = session_cart(request, db)
    if not cart or not cart.items:
        return RedirectResponse("/cart", status_code=303)
    form = {"full_name": full_name, "email": email, "mobile": mobile, "address_line1": address_line1, "address_line2": address_line2, "landmark": landmark, "city": city, "state": state, "pincode": pincode, "notes": notes}
    error = None
    coupon_code = applied_coupon_code(request)
    if len(full_name.strip()) < 2:
        error = "Please enter the recipient's full name."
    elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
        error = "Please enter a valid email address."
    elif not re.fullmatch(r"[6-9]\d{9}", re.sub(r"\D", "", mobile)):
        error = "Please enter a valid 10-digit Indian mobile number."
    elif not re.fullmatch(r"\d{6}", pincode.strip()):
        error = "Please enter a valid 6-digit pincode."
    elif not all(value.strip() for value in (address_line1, city, state)):
        error = "Please complete the delivery address."
    elif payment_method == "cash_on_delivery" and not cart_allows_cod(cart):
        error = "Cash on Delivery is not available for one or more items in your cart. Please pay with UPI."
    elif payment_method == "upi" and not upi_is_available():
        error = "UPI payment is temporarily unavailable."
    elif payment_method not in {"cash_on_delivery", "upi"}:
        error = "Please choose an available payment method."
    elif coupon_code:
        try:
            resolve_coupon(db, coupon_code, cart_totals(cart, db=db)["subtotal"])
        except ValueError as exc:
            error = str(exc)

    if not error:
        try:
            form["mobile"] = re.sub(r"\D", "", mobile)
            order = place_order(db, cart, form, payment_method, coupon_code=coupon_code)
            request.session.pop("cart_token", None)
            request.session.pop("coupon_code", None)
            request.session["cart_count"] = 0
            request.session["last_order_number"] = order.order_number
            return RedirectResponse(f"/order/{order.order_number}/confirmation", status_code=303)
        except CartError as exc:
            db.rollback()
            error = str(exc)

    return templates.TemplateResponse(
        request,
        "store/checkout.html",
        context(request, cart, db=db, error=error, form=form),
        status_code=422,
    )


@router.get("/order/{order_number}/confirmation", response_class=HTMLResponse)
def order_confirmation(order_number: str, request: Request, db: Session = Depends(get_db)):
    if request.session.get("last_order_number") != order_number:
        return RedirectResponse("/", status_code=303)
    from app.models import Order
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    order = db.scalar(select(Order).options(selectinload(Order.items), selectinload(Order.shipping_address)).where(Order.order_number == order_number))
    if not order:
        return RedirectResponse("/", status_code=303)
    upi = payment_details(order) if order.payment_method == "upi" and upi_is_available() else None
    return templates.TemplateResponse(request, "store/order_confirmation.html", context(request, None, db=db, order=order, upi=upi))
