import re
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.security import generate_csrf_token, hash_password, verify_password
from app.db.deps import get_db
from app.models import Customer, Order
from app.services.password_reset_service import (
    create_reset_token,
    get_valid_reset_token,
    mark_token_used,
    send_reset_email,
)


router = APIRouter(tags=["Customer Account"])
templates = Jinja2Templates(directory="app/templates")


def page_context(request: Request, **values):
    return {"request": request, "current_year": datetime.now().year, "cart_count": request.session.get("cart_count", 0), **values}


def current_customer(request: Request, db: Session) -> Customer | None:
    customer_id = request.session.get("customer_id")
    if not customer_id:
        return None
    return db.scalar(select(Customer).where(Customer.id == int(customer_id), Customer.is_active.is_(True)))


def login_redirect(request: Request) -> RedirectResponse:
    request.session["customer_next_url"] = request.url.path
    return RedirectResponse("/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = "", message: str = "", db: Session = Depends(get_db)):
    if current_customer(request, db):
        return RedirectResponse("/account", status_code=303)
    token = generate_csrf_token()
    request.session["customer_login_csrf"] = token
    return templates.TemplateResponse(
        request,
        "store/account/login.html",
        page_context(request, csrf_token=token, error=error, message=message),
    )


@router.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    expected = request.session.pop("customer_login_csrf", None)
    if not expected or csrf_token != expected:
        return RedirectResponse("/login?error=" + quote("Invalid or expired login request."), status_code=303)
    customer = db.scalar(select(Customer).where(func.lower(Customer.email) == email.strip().lower()))
    if not customer or not customer.is_active or not verify_password(password, customer.password_hash):
        return RedirectResponse("/login?error=" + quote("Invalid email or password."), status_code=303)
    customer.last_login_at = datetime.now(timezone.utc)
    db.commit()
    request.session["customer_id"] = customer.id
    next_url = request.session.pop("customer_next_url", "/account")
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/account"
    return RedirectResponse(next_url, status_code=303)


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request, message: str = "", error: str = "", db: Session = Depends(get_db)):
    if current_customer(request, db):
        return RedirectResponse("/account", status_code=303)
    token = generate_csrf_token()
    request.session["customer_forgot_csrf"] = token
    return templates.TemplateResponse(
        request,
        "store/account/forgot_password.html",
        page_context(request, csrf_token=token, message=message, error=error),
    )


@router.post("/forgot-password")
def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    expected = request.session.pop("customer_forgot_csrf", None)
    if not expected or csrf_token != expected:
        return RedirectResponse(
            "/forgot-password?error=" + quote("Invalid or expired password reset request."),
            status_code=303,
        )

    clean_email = email.strip().lower()
    customer = db.scalar(
        select(Customer).where(
            func.lower(Customer.email) == clean_email,
            Customer.is_active.is_(True),
        )
    )
    if customer:
        try:
            raw_token = create_reset_token(db, customer)
            send_reset_email(customer, raw_token)
        except Exception:
            # Keep the public response identical so account existence and
            # mail-provider failures are not exposed to anonymous users.
            pass

    message = "If a Leaf account exists for that email, a password reset link has been sent."
    return RedirectResponse("/forgot-password?message=" + quote(message), status_code=303)


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(
    request: Request,
    token: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    reset_record = get_valid_reset_token(db, token)
    if not reset_record:
        return RedirectResponse(
            "/forgot-password?error=" + quote("This password reset link is invalid or has expired."),
            status_code=303,
        )
    csrf = generate_csrf_token()
    request.session["customer_reset_csrf"] = csrf
    return templates.TemplateResponse(
        request,
        "store/account/reset_password.html",
        page_context(request, csrf_token=csrf, reset_token=token, error=error),
    )


@router.post("/reset-password")
def reset_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    expected = request.session.pop("customer_reset_csrf", None)
    if not expected or csrf_token != expected:
        return RedirectResponse(
            "/forgot-password?error=" + quote("Invalid or expired password reset request."),
            status_code=303,
        )

    reset_record = get_valid_reset_token(db, token)
    if not reset_record:
        return RedirectResponse(
            "/forgot-password?error=" + quote("This password reset link is invalid or has expired."),
            status_code=303,
        )
    if password != password_confirm:
        return RedirectResponse(
            "/reset-password?token=" + quote(token) + "&error=" + quote("Passwords do not match."),
            status_code=303,
        )
    if len(password) < 10:
        return RedirectResponse(
            "/reset-password?token=" + quote(token) + "&error=" + quote("Password must contain at least 10 characters."),
            status_code=303,
        )

    customer = db.get(Customer, reset_record.customer_id)
    if not customer or not customer.is_active:
        return RedirectResponse(
            "/forgot-password?error=" + quote("This password reset link is no longer valid."),
            status_code=303,
        )

    customer.password_hash = hash_password(password)
    mark_token_used(db, reset_record)
    request.session.pop("customer_id", None)
    return RedirectResponse(
        "/login?message=" + quote("Password updated successfully. You can sign in with your new password."),
        status_code=303,
    )


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, error: str = "", db: Session = Depends(get_db)):
    if current_customer(request, db):
        return RedirectResponse("/account", status_code=303)
    token = generate_csrf_token()
    request.session["customer_register_csrf"] = token
    return templates.TemplateResponse(request, "store/account/register.html", page_context(request, csrf_token=token, error=error))


@router.post("/register")
def register_submit(request: Request, first_name: str = Form(...), last_name: str = Form(""), email: str = Form(...), mobile: str = Form(...), password: str = Form(...), password_confirm: str = Form(...), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    expected = request.session.pop("customer_register_csrf", None)
    error = None
    clean_email = email.strip().lower()
    clean_mobile = re.sub(r"\D", "", mobile)
    if not expected or csrf_token != expected:
        error = "Invalid or expired registration request."
    elif len(first_name.strip()) < 2:
        error = "Please enter your name."
    elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", clean_email):
        error = "Please enter a valid email address."
    elif not re.fullmatch(r"[6-9]\d{9}", clean_mobile):
        error = "Please enter a valid 10-digit Indian mobile number."
    elif password != password_confirm:
        error = "Passwords do not match."
    elif len(password) < 10:
        error = "Password must contain at least 10 characters."
    if error:
        return RedirectResponse("/register?error=" + quote(error), status_code=303)

    customer = db.scalar(select(Customer).where(func.lower(Customer.email) == clean_email))
    if customer and not customer.password_hash.startswith("guest:"):
        return RedirectResponse("/register?error=" + quote("An account already exists for this email."), status_code=303)
    try:
        if customer:
            customer.first_name = first_name.strip()
            customer.last_name = last_name.strip() or None
            customer.mobile = clean_mobile
            customer.password_hash = hash_password(password)
            customer.is_active = True
        else:
            customer = Customer(first_name=first_name.strip(), last_name=last_name.strip() or None, email=clean_email, mobile=clean_mobile, password_hash=hash_password(password), is_active=True)
            db.add(customer)
        db.commit()
        db.refresh(customer)
    except IntegrityError:
        db.rollback()
        return RedirectResponse("/register?error=" + quote("That mobile number is already registered."), status_code=303)
    request.session["customer_id"] = customer.id
    return RedirectResponse("/account", status_code=303)


@router.post("/account/logout")
def logout(request: Request):
    request.session.pop("customer_id", None)
    request.session.pop("customer_next_url", None)
    return RedirectResponse("/", status_code=303)


@router.get("/account", response_class=HTMLResponse)
def account(request: Request, db: Session = Depends(get_db)):
    customer = current_customer(request, db)
    if not customer:
        return login_redirect(request)
    orders = db.scalars(select(Order).where(Order.customer_id == customer.id).order_by(Order.created_at.desc()).limit(5)).all()
    return templates.TemplateResponse(request, "store/account/dashboard.html", page_context(request, customer=customer, orders=orders))


@router.get("/account/orders", response_class=HTMLResponse)
def account_orders(request: Request, db: Session = Depends(get_db)):
    customer = current_customer(request, db)
    if not customer:
        return login_redirect(request)
    orders = db.scalars(select(Order).where(Order.customer_id == customer.id).order_by(Order.created_at.desc())).all()
    return templates.TemplateResponse(request, "store/account/orders.html", page_context(request, customer=customer, orders=orders))


@router.get("/account/orders/{order_number}", response_class=HTMLResponse)
def account_order_detail(order_number: str, request: Request, db: Session = Depends(get_db)):
    customer = current_customer(request, db)
    if not customer:
        return login_redirect(request)
    order = db.scalar(select(Order).options(selectinload(Order.items), selectinload(Order.shipping_address), selectinload(Order.status_history)).where(Order.order_number == order_number, Order.customer_id == customer.id))
    if not order:
        return RedirectResponse("/account/orders", status_code=303)
    return templates.TemplateResponse(request, "store/account/order_detail.html", page_context(request, customer=customer, order=order))
