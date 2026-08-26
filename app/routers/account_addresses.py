import re
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import exists, or_, select, update
from sqlalchemy.orm import Session

from app.core.security import generate_csrf_token
from app.db.deps import get_db
from app.models import Address, AddressType, Customer, Order

router = APIRouter(tags=["Customer Addresses"])
templates = Jinja2Templates(directory="app/templates")


def page_context(request: Request, **values):
    return {
        "request": request,
        "current_year": datetime.now().year,
        "cart_count": request.session.get("cart_count", 0),
        **values,
    }


def current_customer(request: Request, db: Session) -> Customer | None:
    customer_id = request.session.get("customer_id")
    if not customer_id:
        return None
    return db.scalar(
        select(Customer).where(
            Customer.id == int(customer_id),
            Customer.is_active.is_(True),
        )
    )


def saved_address_filter(customer_id: int):
    order_reference = exists(
        select(Order.id).where(
            or_(
                Order.shipping_address_id == Address.id,
                Order.billing_address_id == Address.id,
            )
        )
    )
    return Address.customer_id == customer_id, ~order_reference


def saved_addresses(db: Session, customer_id: int):
    return db.scalars(
        select(Address)
        .where(*saved_address_filter(customer_id))
        .order_by(Address.is_default.desc(), Address.updated_at.desc(), Address.id.desc())
    ).all()


def clean_address_form(
    full_name: str,
    mobile: str,
    address_line1: str,
    address_line2: str,
    landmark: str,
    city: str,
    state: str,
    pincode: str,
):
    return {
        "full_name": full_name.strip(),
        "mobile": re.sub(r"\D", "", mobile),
        "address_line1": address_line1.strip(),
        "address_line2": address_line2.strip() or None,
        "landmark": landmark.strip() or None,
        "city": city.strip(),
        "state": state.strip(),
        "country": "India",
        "pincode": pincode.strip(),
    }


def validate_address(data: dict) -> str | None:
    if len(data["full_name"]) < 2:
        return "Please enter the recipient's full name."
    if not re.fullmatch(r"[6-9]\d{9}", data["mobile"]):
        return "Please enter a valid 10-digit Indian mobile number."
    if not data["address_line1"] or not data["city"] or not data["state"]:
        return "Please complete the delivery address."
    if not re.fullmatch(r"\d{6}", data["pincode"]):
        return "Please enter a valid 6-digit pincode."
    return None


@router.get("/account/addresses", response_class=HTMLResponse)
def addresses_page(
    request: Request,
    message: str = "",
    error: str = "",
    edit: int | None = None,
    db: Session = Depends(get_db),
):
    customer = current_customer(request, db)
    if not customer:
        request.session["customer_next_url"] = "/account/addresses"
        return RedirectResponse("/login", status_code=303)

    csrf = generate_csrf_token()
    request.session["customer_address_csrf"] = csrf
    addresses = saved_addresses(db, customer.id)
    edit_address = None
    if edit:
        edit_address = db.scalar(
            select(Address).where(
                Address.id == edit,
                *saved_address_filter(customer.id),
            )
        )

    return templates.TemplateResponse(
        request,
        "store/account/addresses.html",
        page_context(
            request,
            customer=customer,
            addresses=addresses,
            edit_address=edit_address,
            csrf_token=csrf,
            message=message,
            error=error,
        ),
    )


@router.post("/account/addresses/save")
def save_address(
    request: Request,
    address_id: int | None = Form(None),
    full_name: str = Form(...),
    mobile: str = Form(...),
    address_line1: str = Form(...),
    address_line2: str = Form(""),
    landmark: str = Form(""),
    city: str = Form(...),
    state: str = Form(...),
    pincode: str = Form(...),
    set_default: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    customer = current_customer(request, db)
    if not customer:
        return RedirectResponse("/login", status_code=303)
    if csrf_token != request.session.get("customer_address_csrf"):
        return RedirectResponse(
            "/account/addresses?error=" + quote("Invalid or expired address request."),
            status_code=303,
        )

    data = clean_address_form(full_name, mobile, address_line1, address_line2, landmark, city, state, pincode)
    error = validate_address(data)
    if error:
        return RedirectResponse("/account/addresses?error=" + quote(error), status_code=303)

    address = None
    if address_id:
        address = db.scalar(
            select(Address).where(
                Address.id == address_id,
                *saved_address_filter(customer.id),
            )
        )
        if not address:
            return RedirectResponse(
                "/account/addresses?error=" + quote("Address not found."),
                status_code=303,
            )

    existing_default = db.scalar(
        select(Address).where(
            Address.customer_id == customer.id,
            Address.is_default.is_(True),
        )
    )
    make_default = set_default == "1" or existing_default is None

    if make_default:
        db.execute(
            update(Address)
            .where(Address.customer_id == customer.id, Address.is_default.is_(True))
            .values(is_default=False)
        )

    if address is None:
        address = Address(
            customer_id=customer.id,
            address_type=AddressType.SHIPPING,
            is_default=make_default,
            **data,
        )
        db.add(address)
    else:
        for key, value in data.items():
            setattr(address, key, value)
        if make_default:
            address.is_default = True

    db.commit()
    return RedirectResponse(
        "/account/addresses?message=" + quote("Address saved successfully."),
        status_code=303,
    )


@router.post("/account/addresses/{address_id}/default")
def set_default_address(
    address_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    customer = current_customer(request, db)
    if not customer:
        return RedirectResponse("/login", status_code=303)
    if csrf_token != request.session.get("customer_address_csrf"):
        return RedirectResponse("/account/addresses?error=" + quote("Invalid request."), status_code=303)

    address = db.scalar(
        select(Address).where(Address.id == address_id, *saved_address_filter(customer.id))
    )
    if not address:
        return RedirectResponse("/account/addresses?error=" + quote("Address not found."), status_code=303)

    db.execute(update(Address).where(Address.customer_id == customer.id).values(is_default=False))
    address.is_default = True
    db.commit()
    return RedirectResponse("/account/addresses?message=" + quote("Default address updated."), status_code=303)


@router.post("/account/addresses/{address_id}/delete")
def delete_address(
    address_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    customer = current_customer(request, db)
    if not customer:
        return RedirectResponse("/login", status_code=303)
    if csrf_token != request.session.get("customer_address_csrf"):
        return RedirectResponse("/account/addresses?error=" + quote("Invalid request."), status_code=303)

    address = db.scalar(
        select(Address).where(Address.id == address_id, *saved_address_filter(customer.id))
    )
    if not address:
        return RedirectResponse("/account/addresses?error=" + quote("Address not found."), status_code=303)

    was_default = address.is_default
    db.delete(address)
    db.flush()
    if was_default:
        replacement = db.scalar(
            select(Address)
            .where(*saved_address_filter(customer.id))
            .order_by(Address.updated_at.desc(), Address.id.desc())
        )
        if replacement:
            replacement.is_default = True
    db.commit()
    return RedirectResponse("/account/addresses?message=" + quote("Address removed."), status_code=303)
