from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.deps import get_db
from app.models import Brand, Category, Product
from app.services.offer_campaign_service import get_active_homepage_campaign
from app.services.homepage_image_service import HomepageImageService


BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
router = APIRouter(tags=["Storefront"])


def product_options():
    return (
        selectinload(Product.category),
        selectinload(Product.brand),
        selectinload(Product.images),
        selectinload(Product.inventory),
    )


def base_context(request: Request) -> dict:
    return {"request": request, "current_year": datetime.now().year}


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    products = list(
        db.scalars(
            select(Product)
            .options(*product_options())
            .where(Product.is_active.is_(True), Product.deleted_at.is_(None))
            .order_by(Product.is_featured.desc(), Product.created_at.desc())
            .limit(8)
        ).all()
    )
    categories = list(
        db.scalars(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
            .limit(6)
        ).all()
    )
    organic_products = list(
        db.scalars(
            select(Product)
            .options(*product_options())
            .where(Product.is_active.is_(True), Product.deleted_at.is_(None))
            .order_by(Product.is_featured.desc(), Product.created_at.desc())
            .limit(4)
        ).all()
    )
    organic_shop_href = "/shop"
    for category in categories:
        label = f"{category.name} {category.slug}".lower()
        if "organic" in label:
            organic_shop_href = f"/shop?category={category.slug}"
            break

    return templates.TemplateResponse(
        request,
        "store/home.html",
        {
            **base_context(request),
            "featured_products": products,
            "categories": categories[:4],
            "organic_products": organic_products,
            "organic_shop_href": organic_shop_href,
            "homepage_media": HomepageImageService.media_map(db),
            "offer_campaign": get_active_homepage_campaign(db),
        },
    )


@router.get("/shop", response_class=HTMLResponse)
@router.get("/search", response_class=HTMLResponse)
def shop(
    request: Request,
    q: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    featured: bool = False,
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
):
    page_size = 12
    filters = [Product.is_active.is_(True), Product.deleted_at.is_(None)]
    if q and q.strip():
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                Product.name.ilike(term),
                Product.short_description.ilike(term),
                Product.sku.ilike(term),
            )
        )
    if category:
        filters.append(Product.category.has(Category.slug == category))
    if brand:
        filters.append(Product.brand.has(Brand.slug == brand))
    if featured:
        filters.append(Product.is_featured.is_(True))

    total = int(db.scalar(select(func.count(Product.id)).where(*filters)) or 0)
    products = list(
        db.scalars(
            select(Product)
            .options(*product_options())
            .where(*filters)
            .order_by(Product.is_featured.desc(), Product.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    categories = list(db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.name)).all())
    brands = list(db.scalars(select(Brand).where(Brand.is_active.is_(True)).order_by(Brand.name)).all())
    total_pages = (total + page_size - 1) // page_size if total else 0
    return templates.TemplateResponse(
        request,
        "store/shop.html",
        {
            **base_context(request),
            "products": products,
            "categories": categories,
            "brands": brands,
            "filters": {"q": q or "", "category": category or "", "brand": brand or "", "featured": featured},
            "page": page,
            "total": total,
            "total_pages": total_pages,
        },
    )


@router.get("/offers")
def offers() -> RedirectResponse:
    return RedirectResponse("/shop?featured=true", status_code=302)


@router.get("/categories", response_class=HTMLResponse)
def categories(request: Request, db: Session = Depends(get_db)):
    items = list(
        db.scalars(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
        ).all()
    )
    counts = dict(
        db.execute(
            select(Product.category_id, func.count(Product.id))
            .where(Product.is_active.is_(True), Product.deleted_at.is_(None))
            .group_by(Product.category_id)
        ).all()
    )
    return templates.TemplateResponse(
        request,
        "store/categories.html",
        {**base_context(request), "categories": items, "product_counts": counts},
    )


@router.get("/product/{slug}", response_class=HTMLResponse)
def product_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    product = db.scalar(
        select(Product)
        .options(*product_options())
        .where(Product.slug == slug, Product.is_active.is_(True), Product.deleted_at.is_(None))
    )
    if product is None:
        return templates.TemplateResponse(
            request,
            "store/not_found.html",
            base_context(request),
            status_code=404,
        )
    related = list(
        db.scalars(
            select(Product)
            .options(*product_options())
            .where(
                Product.category_id == product.category_id,
                Product.id != product.id,
                Product.is_active.is_(True),
                Product.deleted_at.is_(None),
            )
            .limit(4)
        ).all()
    )
    return templates.TemplateResponse(
        request,
        "store/product_detail.html",
        {**base_context(request), "product": product, "related_products": related},
    )


@router.get("/contact", response_class=HTMLResponse)
def contact(request: Request):
    return templates.TemplateResponse(request, "store/contact.html", base_context(request))


@router.get("/shipping", response_class=HTMLResponse)
def shipping(request: Request):
    return templates.TemplateResponse(request, "store/shipping.html", base_context(request))


@router.get("/returns", response_class=HTMLResponse)
def returns(request: Request):
    return templates.TemplateResponse(request, "store/returns.html", base_context(request))
