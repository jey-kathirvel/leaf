import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.deps import get_db
from app.models import Category, Customer, Inventory, Order, Product
from app.routers.admin_products import pop_flash, require_admin, set_flash


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
