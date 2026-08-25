from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models import Category, Product
from app.routers.admin_products import pop_flash, require_admin, set_flash


router = APIRouter(prefix="/admin/categories", tags=["Admin Category Actions"])
templates = Jinja2Templates(directory="app/templates")


def active_product_count(db: Session, category_id: int) -> int:
    """Count only products that still exist in the active catalogue."""
    return (
        db.scalar(
            select(func.count(Product.id)).where(
                Product.category_id == category_id,
                Product.deleted_at.is_(None),
            )
        )
        or 0
    )


@router.get("", response_class=HTMLResponse)
def category_list_page(
    request: Request,
    db: Session = Depends(get_db),
):
    """Category list with counts that exclude soft-deleted products."""
    if redirect := require_admin(request):
        return redirect

    items = db.execute(
        select(Category, func.count(Product.id).label("product_count"))
        .outerjoin(
            Product,
            (Product.category_id == Category.id)
            & Product.deleted_at.is_(None),
        )
        .group_by(Category.id)
        .order_by(Category.sort_order, Category.name)
    ).all()

    return templates.TemplateResponse(
        request,
        "admin/categories/list.html",
        {
            "request": request,
            "items": items,
            "flash": pop_flash(request),
        },
    )


@router.get("/{category_id:int}/edit", response_class=HTMLResponse)
def category_edit_page(
    category_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if redirect := require_admin(request):
        return redirect

    category = db.get(Category, category_id)
    if category is None:
        set_flash(request, "Category was not found.", "danger")
        return RedirectResponse(
            "/admin/categories",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    product_count = active_product_count(db, category_id)

    return templates.TemplateResponse(
        request,
        "admin/categories/edit.html",
        {
            "request": request,
            "category": category,
            "product_count": product_count,
            "flash": pop_flash(request),
        },
    )


@router.post("/{category_id:int}/delete")
def category_delete(
    category_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if redirect := require_admin(request):
        return redirect

    category = db.get(Category, category_id)
    if category is None:
        set_flash(request, "Category was not found.", "danger")
        return RedirectResponse(
            "/admin/categories",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    product_count = active_product_count(db, category_id)

    if product_count:
        set_flash(
            request,
            f"Cannot delete '{category.name}' because {product_count} active product(s) are assigned to it. Reassign or delete those products first.",
            "danger",
        )
        return RedirectResponse(
            "/admin/categories",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    category_name = category.name

    try:
        # Product deletion in Leaf is normally a soft delete, so historical
        # product rows can still hold the category FK even though they are no
        # longer part of the catalogue. Once a category has zero active
        # products, permanently remove only those already-soft-deleted product
        # rows before deleting the category. OrderItem.product_id uses SET NULL
        # and order-item snapshot fields keep the historical order details.
        deleted_products = db.scalars(
            select(Product).where(
                Product.category_id == category_id,
                Product.deleted_at.is_not(None),
            )
        ).all()
        for product in deleted_products:
            db.delete(product)

        db.flush()
        db.delete(category)
        db.commit()
        set_flash(request, f"Category '{category_name}' deleted.")
    except IntegrityError:
        db.rollback()
        set_flash(
            request,
            f"Category '{category_name}' cannot be deleted because it is still referenced by store data.",
            "danger",
        )

    return RedirectResponse(
        "/admin/categories",
        status_code=status.HTTP_303_SEE_OTHER,
    )
