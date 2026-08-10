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
def login_page(request: Request, error: str = "", db: Session = Depends(get_db)):
    if current_customer(request, db):
        return RedirectResponse("/account", status_code=303)
    token = generate_csrf_token()
    request.session["customer_login_csrf"] = token
    return templates.TemplateResponse(request, "store/account/login.html", page_context(request, csrf_token=token, error=error))


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
