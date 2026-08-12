import re

from fastapi import APIRouter, Depends, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.deps import get_db
from decimal import Decimal, InvalidOperation

from app.models import Category, CouponDiscountType, Customer, HomepageOfferCampaign, Inventory, Order, Product
from app.services.homepage_image_service import HomepageImageError, HomepageImageService
from app.services.offer_campaign_service import (
    format_campaign_schedule_for_input,
    get_campaign,
    is_valid_iframe_url,
    list_campaigns,
    parse_campaign_schedule_input,
    parse_discount_type,
    campaign_within_schedule,
)
from app.routers.admin_products import pop_flash, require_admin, set_flash, optional_text


router = APIRouter(prefix="/admin", tags=["Admin Operations"])
templates = Jinja2Templates(directory="app/templates")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


@router.get("/categories", response_class=HTMLResponse)
def categories(request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    items = db.execute(
        select(Category, func.count(Product.id).label("product_count"))
        .outerjoin(Product)
        .group_by(Category.id)
        .order_by(Category.sort_order, Category.name)
    ).all()
    return templates.TemplateResponse(request, "admin/categories/list.html", {"request": request, "items": items, "flash": pop_flash(request)})


@router.post("/categories")
def category_create(request: Request, name: str = Form(...), slug: str = Form(""), description: str = Form(""), sort_order: int = Form(0), db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    clean_name = name.strip()
    clean_slug = slugify(slug or clean_name)
    if len(clean_name) < 2 or not clean_slug:
        set_flash(request, "Enter a valid category name.", "danger")
    else:
        try:
            db.add(Category(name=clean_name, slug=clean_slug, description=description.strip() or None, sort_order=max(sort_order, 0), is_active=True))
            db.commit()
            set_flash(request, "Category created.")
        except IntegrityError:
            db.rollback()
            set_flash(request, "A category with that name or slug already exists.", "danger")
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/categories/{category_id:int}/update")
def category_update(category_id: int, request: Request, name: str = Form(...), slug: str = Form(...), description: str = Form(""), sort_order: int = Form(0), db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    category = db.get(Category, category_id)
    if not category:
        set_flash(request, "Category was not found.", "danger")
    else:
        try:
            category.name = name.strip()
            category.slug = slugify(slug)
            category.description = description.strip() or None
            category.sort_order = max(sort_order, 0)
            db.commit()
            set_flash(request, "Category updated.")
        except IntegrityError:
            db.rollback()
            set_flash(request, "Category name and slug must be unique.", "danger")
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/categories/{category_id:int}/toggle")
def category_toggle(category_id: int, request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    category = db.get(Category, category_id)
    if category:
        category.is_active = not category.is_active
        db.commit()
        set_flash(request, f"Category {'activated' if category.is_active else 'hidden'}.")
    return RedirectResponse("/admin/categories", status_code=303)


@router.get("/inventory", response_class=HTMLResponse)
def inventory(request: Request, q: str = "", stock: str = "", db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    filters = [Product.deleted_at.is_(None)]
    if q.strip():
        term = f"%{q.strip()}%"
        filters.append(or_(Product.name.ilike(term), Product.sku.ilike(term)))
    if stock == "out":
        filters.append(Inventory.quantity <= 0)
    elif stock == "low":
        filters.append(Inventory.quantity > 0, Inventory.quantity <= Inventory.low_stock_threshold)
    elif stock == "available":
        filters.append(Inventory.quantity > Inventory.low_stock_threshold)
    rows = db.execute(
        select(Product, Inventory).join(Inventory, Inventory.product_id == Product.id).where(*filters).order_by(Product.name)
    ).all()
    return templates.TemplateResponse(request, "admin/inventory/list.html", {"request": request, "rows": rows, "filters": {"q": q, "stock": stock}, "flash": pop_flash(request)})


@router.post("/inventory/{inventory_id:int}/update")
def inventory_update(inventory_id: int, request: Request, quantity: int = Form(...), low_stock_threshold: int = Form(...), max_quantity: int = Form(0), db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    item = db.scalar(select(Inventory).where(Inventory.id == inventory_id).with_for_update())
    if not item:
        set_flash(request, "Inventory record was not found.", "danger")
    elif quantity < 0 or low_stock_threshold < 0 or max_quantity < 0 or (max_quantity and max_quantity < low_stock_threshold):
        set_flash(request, "Stock values are invalid. Maximum must be zero or at least the low-stock threshold.", "danger")
    else:
        item.quantity = quantity
        item.low_stock_threshold = low_stock_threshold
        item.max_quantity = max_quantity
        db.commit()
        set_flash(request, "Inventory updated.")
    return RedirectResponse("/admin/inventory", status_code=303)


@router.get("/customers", response_class=HTMLResponse)
def customers(request: Request, q: str = "", status: str = "", db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    filters = []
    if q.strip():
        term = f"%{q.strip()}%"
        filters.append(or_(Customer.first_name.ilike(term), Customer.last_name.ilike(term), Customer.email.ilike(term), Customer.mobile.ilike(term)))
    if status == "active":
        filters.append(Customer.is_active.is_(True))
    elif status == "inactive":
        filters.append(Customer.is_active.is_(False))
    rows = db.execute(
        select(Customer, func.count(Order.id).label("order_count"), func.coalesce(func.sum(Order.grand_total), 0).label("total_spent"))
        .outerjoin(Order).where(*filters).group_by(Customer.id).order_by(Customer.created_at.desc())
    ).all()
    return templates.TemplateResponse(request, "admin/customers/list.html", {"request": request, "rows": rows, "filters": {"q": q, "status": status}, "flash": pop_flash(request)})


@router.get("/customers/{customer_id:int}", response_class=HTMLResponse)
def customer_detail(customer_id: int, request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    customer = db.scalar(select(Customer).options(selectinload(Customer.addresses), selectinload(Customer.orders)).where(Customer.id == customer_id))
    if not customer:
        return RedirectResponse("/admin/customers", status_code=303)
    return templates.TemplateResponse(request, "admin/customers/view.html", {"request": request, "customer": customer, "flash": pop_flash(request)})


@router.post("/customers/{customer_id:int}/toggle")
def customer_toggle(customer_id: int, request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    customer = db.get(Customer, customer_id)
    if customer:
        customer.is_active = not customer.is_active
        db.commit()
        set_flash(request, f"Customer {'activated' if customer.is_active else 'deactivated'}.")
    return RedirectResponse(f"/admin/customers/{customer_id}", status_code=303)


@router.get("/offer-campaign", response_class=HTMLResponse)
def offer_campaign_legacy_redirect(request: Request):
    if redirect := require_admin(request):
        return redirect
    return RedirectResponse("/admin/offer-campaigns", status_code=303)


@router.get("/offer-campaigns", response_class=HTMLResponse)
def offer_campaigns_list(request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    campaigns = list_campaigns(db)
    campaign_rows = [(campaign, campaign_within_schedule(campaign)) for campaign in campaigns]
    return templates.TemplateResponse(
        request,
        "admin/offer_campaign/list.html",
        {
            "request": request,
            "campaign_rows": campaign_rows,
            "flash": pop_flash(request),
        },
    )


@router.get("/offer-campaigns/new", response_class=HTMLResponse)
def offer_campaign_new_page(request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    campaign = HomepageOfferCampaign(iframe_url="", is_active=False, delay_seconds=5, auto_close_seconds=15)
    return templates.TemplateResponse(
        request,
        "admin/offer_campaign/edit.html",
        {
            "request": request,
            "campaign": campaign,
            "is_new": True,
            "starts_at_local": "",
            "ends_at_local": "",
            "flash": pop_flash(request),
        },
    )


@router.post("/offer-campaigns")
def offer_campaign_create(
    request: Request,
    title: str = Form(""),
    message: str = Form(""),
    coupon_code: str = Form(""),
    iframe_url: str = Form(""),
    is_active: str = Form(""),
    delay_seconds: int = Form(5),
    auto_close_seconds: int = Form(15),
    starts_at: str = Form(""),
    ends_at: str = Form(""),
    priority: int = Form(0),
    discount_type: str = Form(""),
    discount_value: str = Form(""),
    min_order_amount: str = Form(""),
    db: Session = Depends(get_db),
):
    if redirect := require_admin(request):
        return redirect

    campaign = HomepageOfferCampaign(iframe_url="", is_active=False, delay_seconds=5, auto_close_seconds=15)
    error = _apply_campaign_form(
        campaign,
        title,
        message,
        coupon_code,
        iframe_url,
        is_active,
        delay_seconds,
        auto_close_seconds,
        starts_at,
        ends_at,
        priority,
        discount_type,
        discount_value,
        min_order_amount,
    )
    if error:
        set_flash(request, error, "danger")
        return RedirectResponse("/admin/offer-campaigns/new", status_code=303)

    db.add(campaign)
    db.commit()
    set_flash(request, "Offer campaign created.")
    return RedirectResponse("/admin/offer-campaigns", status_code=303)


@router.get("/offer-campaigns/{campaign_id:int}", response_class=HTMLResponse)
def offer_campaign_edit_page(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    campaign = get_campaign(db, campaign_id)
    if campaign is None:
        set_flash(request, "Campaign not found.", "danger")
        return RedirectResponse("/admin/offer-campaigns", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin/offer_campaign/edit.html",
        {
            "request": request,
            "campaign": campaign,
            "is_new": False,
            "starts_at_local": format_campaign_schedule_for_input(campaign.starts_at),
            "ends_at_local": format_campaign_schedule_for_input(campaign.ends_at),
            "flash": pop_flash(request),
        },
    )


def _parse_money_field(value: str) -> Decimal | None:
    clean = value.strip()
    if not clean:
        return None
    try:
        return Decimal(clean)
    except InvalidOperation:
        return None


def _apply_campaign_form(
    campaign: HomepageOfferCampaign,
    title: str,
    message: str,
    coupon_code: str,
    iframe_url: str,
    is_active: str,
    delay_seconds: int,
    auto_close_seconds: int,
    starts_at: str,
    ends_at: str,
    priority: int,
    discount_type: str,
    discount_value: str,
    min_order_amount: str,
) -> str | None:
    clean_url = iframe_url.strip()
    clean_code = coupon_code.strip().upper()
    active = is_active == "on"
    parsed_discount_type = parse_discount_type(discount_type)
    parsed_discount_value = _parse_money_field(discount_value)
    parsed_min_order = _parse_money_field(min_order_amount)

    if active and not clean_url:
        return "Enter an iframe URL before activating the homepage popup."
    if clean_url and not is_valid_iframe_url(clean_url):
        return "Iframe URL must be a valid http or https address."
    if delay_seconds < 0 or auto_close_seconds < 1:
        return "Delay must be zero or more and auto-close must be at least 1 second."
    if parsed_discount_type and parsed_discount_value is None:
        return "Enter a discount value when a discount type is selected."
    if parsed_discount_type == "percent" and parsed_discount_value is not None:
        if parsed_discount_value <= 0 or parsed_discount_value > Decimal("100"):
            return "Percent discount must be between 1 and 100."
    if parsed_discount_type == "fixed" and parsed_discount_value is not None:
        if parsed_discount_value <= 0:
            return "Fixed discount must be greater than zero."
    if parsed_min_order is not None and parsed_min_order < 0:
        return "Minimum order amount cannot be negative."

    campaign.title = title.strip() or None
    campaign.message = message.strip() or None
    campaign.coupon_code = clean_code or None
    campaign.iframe_url = clean_url
    campaign.is_active = active
    campaign.delay_seconds = delay_seconds
    campaign.auto_close_seconds = auto_close_seconds
    campaign.starts_at = parse_campaign_schedule_input(starts_at)
    campaign.ends_at = parse_campaign_schedule_input(ends_at)
    campaign.priority = priority
    campaign.discount_type = CouponDiscountType(parsed_discount_type) if parsed_discount_type else None
    campaign.discount_value = parsed_discount_value
    campaign.min_order_amount = parsed_min_order
    return None


@router.post("/offer-campaigns/{campaign_id:int}")
def offer_campaign_update(
    campaign_id: int,
    request: Request,
    title: str = Form(""),
    message: str = Form(""),
    coupon_code: str = Form(""),
    iframe_url: str = Form(""),
    is_active: str = Form(""),
    delay_seconds: int = Form(5),
    auto_close_seconds: int = Form(15),
    starts_at: str = Form(""),
    ends_at: str = Form(""),
    priority: int = Form(0),
    discount_type: str = Form(""),
    discount_value: str = Form(""),
    min_order_amount: str = Form(""),
    db: Session = Depends(get_db),
):
    if redirect := require_admin(request):
        return redirect

    campaign = get_campaign(db, campaign_id)
    if campaign is None:
        set_flash(request, "Campaign not found.", "danger")
        return RedirectResponse("/admin/offer-campaigns", status_code=303)

    error = _apply_campaign_form(
        campaign,
        title,
        message,
        coupon_code,
        iframe_url,
        is_active,
        delay_seconds,
        auto_close_seconds,
        starts_at,
        ends_at,
        priority,
        discount_type,
        discount_value,
        min_order_amount,
    )
    if error:
        set_flash(request, error, "danger")
        return RedirectResponse(f"/admin/offer-campaigns/{campaign_id}", status_code=303)

    db.commit()
    set_flash(request, "Offer campaign saved.")
    return RedirectResponse(f"/admin/offer-campaigns/{campaign_id}", status_code=303)


@router.post("/offer-campaigns/{campaign_id:int}/delete")
def offer_campaign_delete(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    campaign = get_campaign(db, campaign_id)
    if campaign is None:
        set_flash(request, "Campaign not found.", "danger")
    else:
        db.delete(campaign)
        db.commit()
        set_flash(request, "Offer campaign deleted.")
    return RedirectResponse("/admin/offer-campaigns", status_code=303)


@router.get("/homepage-images", response_class=HTMLResponse)
def homepage_images_page(request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    slots = HomepageImageService.list_admin_slots(db)
    sections: dict[str, list] = {}
    for slot in slots:
        sections.setdefault(slot.section, []).append(slot)
    return templates.TemplateResponse(
        request,
        "admin/homepage_images/edit.html",
        {
            "request": request,
            "sections": sections,
            "flash": pop_flash(request),
        },
    )


@router.post("/homepage-images/{slot_key}")
async def homepage_image_upload(slot_key: str, request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    if slot_key not in HomepageImageService.slot_keys():
        set_flash(request, "Unknown homepage image slot.", "danger")
        return RedirectResponse("/admin/homepage-images", status_code=303)

    form = await request.form()
    image = form.get("image")
    if not isinstance(image, UploadFile):
        set_flash(request, "Select an image to upload.", "danger")
        return RedirectResponse("/admin/homepage-images", status_code=303)

    alt_text = optional_text(form.get("alt_text"))
    try:
        await HomepageImageService.upload(db, slot_key, image, alt_text=alt_text)
        set_flash(request, "Homepage image updated.")
    except HomepageImageError as exc:
        set_flash(request, str(exc), "danger")
    finally:
        await image.close()

    return RedirectResponse(
        f"/admin/homepage-images#{slot_key}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/homepage-images/{slot_key}/remove")
def homepage_image_remove(slot_key: str, request: Request, db: Session = Depends(get_db)):
    if redirect := require_admin(request):
        return redirect
    if slot_key not in HomepageImageService.slot_keys():
        set_flash(request, "Unknown homepage image slot.", "danger")
    else:
        try:
            HomepageImageService.remove(db, slot_key)
            set_flash(request, "Custom image removed. Default placeholder is shown again.")
        except HomepageImageError as exc:
            set_flash(request, str(exc), "danger")
    return RedirectResponse("/admin/homepage-images", status_code=303)
