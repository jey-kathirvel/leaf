from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, update
from sqlalchemy.orm import Session
from starlette import status

from app.db.deps import get_db
from app.models import Product


router = APIRouter(prefix="/admin/products", tags=["Admin Products"])


def _require_admin(request: Request) -> RedirectResponse | None:
    if request.session.get("admin_user_id"):
        return None
    request.session["next_url"] = str(request.url.path)
    return RedirectResponse(
        url="/admin/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _set_flash(request: Request, message: str, category: str = "success") -> None:
    request.session["flash"] = {
        "message": message,
        "category": category,
    }


@router.post("/{product_id:int}/delete")
def delete_product(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = _require_admin(request)
    if auth_redirect:
        return auth_redirect

    product = db.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        _set_flash(request, "Product not found or already deleted.", "danger")
        return RedirectResponse(
            url="/admin/products",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    product_name = product.product_name

    try:
        result = db.execute(
            update(Product)
            .where(
                Product.id == product_id,
                Product.deleted_at.is_(None),
            )
            .values(
                deleted_at=func.now(),
                is_active=False,
            )
        )
        if result.rowcount != 1:
            db.rollback()
            _set_flash(request, "Product could not be deleted.", "danger")
        else:
            db.commit()
            _set_flash(
                request,
                f"Product '{product_name}' deleted successfully.",
            )
    except Exception:
        db.rollback()
        _set_flash(
            request,
            "Unable to delete the product because the database update failed. Please try again.",
            "danger",
        )

    return RedirectResponse(
        url="/admin/products",
        status_code=status.HTTP_303_SEE_OTHER,
    )
