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

    product_count = db.scalar(
        select(func.count(Product.id)).where(Product.category_id == category_id)
    ) or 0

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

    product_count = db.scalar(
        select(func.count(Product.id)).where(Product.category_id == category_id)
    ) or 0

    if product_count:
        set_flash(
            request,
            f"Cannot delete '{category.name}' because {product_count} product(s) are assigned to it. Reassign or delete those products first.",
            "danger",
        )
        return RedirectResponse(
            "/admin/categories",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    category_name = category.name
    try:
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
