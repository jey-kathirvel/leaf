from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.routers.admin_products import pop_flash, require_admin, set_flash
from app.services.store_settings_service import get_store_settings

router = APIRouter(prefix="/admin/configuration", tags=["Admin Configuration"])
templates = Jinja2Templates(directory="app/templates")


def _money(value: str, field: str) -> Decimal:
    try:
        result = Decimal(value or "0").quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a valid amount.")
    if result < 0:
        raise ValueError(f"{field} cannot be negative.")
    return result


@router.get("", response_class=HTMLResponse)
def configuration_page(request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    settings = get_store_settings(db)
    return templates.TemplateResponse(
        request,
        "admin/configuration/index.html",
        {"request": request, "settings": settings, "flash": pop_flash(request)},
    )


@router.post("/shipping")
def update_shipping(
    request: Request,
    shipping_enabled: str | None = Form(None),
    flat_shipping_amount: str = Form("0"),
    free_shipping_threshold: str = Form("0"),
    delivery_eta_min_days: int = Form(3),
    delivery_eta_max_days: int = Form(7),
    db: Session = Depends(get_db),
):
    if redirect := require_admin(request):
        return redirect
    try:
        if delivery_eta_min_days < 0 or delivery_eta_max_days < delivery_eta_min_days:
            raise ValueError("Delivery ETA must have a valid minimum and maximum day range.")
        settings = get_store_settings(db)
        settings.shipping_enabled = shipping_enabled == "on"
        settings.flat_shipping_amount = _money(flat_shipping_amount, "Flat shipping")
        settings.free_shipping_threshold = _money(free_shipping_threshold, "Free shipping threshold")
        settings.delivery_eta_min_days = delivery_eta_min_days
        settings.delivery_eta_max_days = delivery_eta_max_days
        db.commit()
        set_flash(request, "Shipping configuration saved.")
    except ValueError as exc:
        db.rollback()
        set_flash(request, str(exc), "danger")
    return RedirectResponse("/admin/configuration#shipping", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tax")
def update_tax(
    request: Request,
    tax_enabled: str | None = Form(None),
    default_tax_percentage: str = Form("0"),
    prices_include_tax: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if redirect := require_admin(request):
        return redirect
    try:
        rate = _money(default_tax_percentage, "Default GST rate")
        if rate > Decimal("100.00"):
            raise ValueError("Default GST rate cannot exceed 100%.")
        settings = get_store_settings(db)
        settings.tax_enabled = tax_enabled == "on"
        settings.default_tax_percentage = rate
        settings.prices_include_tax = prices_include_tax == "on"
        db.commit()
        set_flash(request, "Tax configuration saved.")
    except ValueError as exc:
        db.rollback()
        set_flash(request, str(exc), "danger")
    return RedirectResponse("/admin/configuration#tax", status_code=status.HTTP_303_SEE_OTHER)
