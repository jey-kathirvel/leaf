from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette import status
from starlette.datastructures import UploadFile
from starlette.templating import Jinja2Templates

try:
    from app.db.session import get_db
except ImportError:
    from app.db.database import get_db

from app.models.commerce import Brand, Category
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.product_service import (
    ProductConflictError,
    ProductNotFoundError,
    ProductService,
    ProductValidationError,
)
from app.services.product_image_service import (
    ProductImageError,
    ProductImageService,
)


router = APIRouter(
    prefix="/admin/products",
    tags=["Admin Products"],
)

templates = Jinja2Templates(directory="app/templates")


def require_admin(request: Request) -> RedirectResponse | None:
    admin_user_id = request.session.get("admin_user_id")

    if not admin_user_id:
        request.session["next_url"] = str(request.url.path)
        return RedirectResponse(
            url="/admin/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return None


def set_flash(
    request: Request,
    message: str,
    category: str = "success",
) -> None:
    request.session["flash"] = {
        "message": message,
        "category": category,
    }


def pop_flash(request: Request) -> dict[str, str] | None:
    return request.session.pop("flash", None)


def optional_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def parse_int(
    value: Any,
    *,
    default: int | None = None,
) -> int | None:
    text = optional_text(value)

    if text is None:
        return default

    try:
        return int(text)
    except (TypeError, ValueError) as exc:
        raise ProductValidationError(
            f"Invalid integer value: {text}"
        ) from exc


def parse_decimal(
    value: Any,
    *,
    default: str = "0",
) -> Decimal:
    text = optional_text(value) or default

    try:
        return Decimal(text)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProductValidationError(
            f"Invalid decimal value: {text}"
        ) from exc


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def build_product_payload(
    request: Request,
    db: Session,
    *,
    product_id: int | None = None,
) -> dict[str, Any]:
    form = await request.form()

    product_name = optional_text(form.get("product_name"))

    if not product_name:
        raise ProductValidationError(
            "Product name is required."
        )

    supplied_slug = optional_text(form.get("slug"))
    supplied_sku = optional_text(form.get("sku"))
    supplied_barcode = optional_text(form.get("barcode"))

    if supplied_slug:
        slug = ProductService.slugify(supplied_slug)
    else:
        slug = ProductService.generate_unique_slug(
            db,
            product_name,
            exclude_product_id=product_id,
        )

    if supplied_sku:
        sku = ProductService.normalize_sku(supplied_sku)
    else:
        sku = ProductService.generate_unique_sku(
            db,
            product_name,
            exclude_product_id=product_id,
        )

    if supplied_barcode:
        barcode = ProductService.normalize_barcode(
            supplied_barcode
        )
    else:
        barcode = ProductService.generate_unique_barcode(
            db,
            exclude_product_id=product_id,
        )

    category_id = parse_int(form.get("category_id"))

    if category_id is None:
        raise ProductValidationError(
            "Category is required."
        )

    payload = {
        "product_name": product_name,
        "short_name": optional_text(form.get("short_name")),
        "slug": slug,
        "sku": sku,
        "barcode": barcode,
        "category_id": category_id,
        "brand_id": parse_int(form.get("brand_id")),
        "mrp": parse_decimal(form.get("mrp")),
        "selling_price": parse_decimal(
            form.get("selling_price")
        ),
        "cost_price": parse_decimal(form.get("cost_price")),
        "gst_percentage": parse_decimal(
            form.get("gst_percentage")
        ),
        "hsn_code": optional_text(form.get("hsn_code")),
        "track_inventory": parse_bool(
            form.get("track_inventory")
        ),
        "allow_cod": parse_bool(form.get("allow_cod")),
        "opening_stock": parse_int(
            form.get("opening_stock"),
            default=0,
        ),
        "min_stock": parse_int(
            form.get("min_stock"),
            default=0,
        ),
        "max_stock": parse_int(
            form.get("max_stock"),
            default=0,
        ),
        "short_description": optional_text(
            form.get("short_description")
        ),
        "long_description": optional_text(
            form.get("long_description")
        ),
        "meta_title": optional_text(form.get("meta_title")),
        "meta_description": optional_text(
            form.get("meta_description")
        ),
        "meta_keywords": optional_text(
            form.get("meta_keywords")
        ),
        "is_active": parse_bool(form.get("is_active")),
        "is_featured": parse_bool(
            form.get("is_featured")
        ),
        "is_new_arrival": parse_bool(
            form.get("is_new_arrival")
        ),
        "is_best_seller": parse_bool(
            form.get("is_best_seller")
        ),
    }

    return payload


def get_reference_data(
    db: Session,
) -> tuple[list[Category], list[Brand]]:
    category_query = select(Category)

    if hasattr(Category, "is_active"):
        category_query = category_query.where(
            Category.is_active.is_(True)
        )

    category_order_column = getattr(
        Category,
        "category_name",
        getattr(Category, "name", Category.id),
    )

    categories = list(
        db.scalars(
            category_query.order_by(category_order_column.asc())
        ).all()
    )

    brand_query = select(Brand)

    if hasattr(Brand, "is_active"):
        brand_query = brand_query.where(
            Brand.is_active.is_(True)
        )

    brand_order_column = getattr(
        Brand,
        "brand_name",
        getattr(Brand, "name", Brand.id),
    )

    brands = list(
        db.scalars(
            brand_query.order_by(brand_order_column.asc())
        ).all()
    )

    return categories, brands


def validation_message(exc: ValidationError) -> str:
    messages: list[str] = []

    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"])
        message = error["msg"]
        messages.append(f"{location}: {message}")

    return " | ".join(messages)


@router.get("")
@router.get("/")
def product_list(
    request: Request,
    search: str | None = None,
    category_id: int | None = None,
    brand_id: int | None = None,
    is_active: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)

    if auth_redirect:
        return auth_redirect

    active_filter: bool | None = None

    if is_active == "true":
        active_filter = True
    elif is_active == "false":
        active_filter = False

    product_page = ProductService.list_products(
        db=db,
        search=search,
        category_id=category_id,
        brand_id=brand_id,
        is_active=active_filter,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    categories, brands = get_reference_data(db)

    query_values = {
        "search": search or "",
        "category_id": category_id or "",
        "brand_id": brand_id or "",
        "is_active": is_active or "",
        "page_size": page_size,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }

    return templates.TemplateResponse(
        request,
        "admin/products/list.html",
        {
            "request": request,
            "products": product_page.items,
            "pagination": product_page,
            "categories": categories,
            "brands": brands,
            "filters": query_values,
            "query_string": urlencode(
                {
                    key: value
                    for key, value in query_values.items()
                    if value != ""
                }
            ),
            "flash": pop_flash(request),
        },
    )


@router.get("/create")
def product_create_form(
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)

    if auth_redirect:
        return auth_redirect

    categories, brands = get_reference_data(db)

    return templates.TemplateResponse(
        request,
        "admin/products/create.html",
        {
            "request": request,
            "categories": categories,
            "brands": brands,
            "product": None,
            "form_data": {},
            "errors": [],
            "flash": pop_flash(request),
        },
    )


@router.post("/create")
async def product_create(
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)

    if auth_redirect:
        return auth_redirect

    categories, brands = get_reference_data(db)
    raw_form = dict(await request.form())

    try:
        payload_data = await build_product_payload(
            request,
            db,
        )
        payload = ProductCreate.model_validate(payload_data)
        product = ProductService.create_product(db, payload)

        set_flash(
            request,
            f"Product '{product.product_name}' created successfully.",
        )

        return RedirectResponse(
            url=f"/admin/products/{product.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except (
        ProductConflictError,
        ProductValidationError,
    ) as exc:
        errors = [str(exc)]

    except ValidationError as exc:
        errors = [validation_message(exc)]

    return templates.TemplateResponse(
        request,
        "admin/products/create.html",
        {
            "request": request,
            "categories": categories,
            "brands": brands,
            "product": None,
            "form_data": raw_form,
            "errors": errors,
            "flash": None,
        },
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


@router.get("/{product_id:int}")
def product_view(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)

    if auth_redirect:
        return auth_redirect

    try:
        product = ProductService.get_by_id(db, product_id)
    except ProductNotFoundError:
        set_flash(
            request,
            "Product not found.",
            "danger",
        )
        return RedirectResponse(
            url="/admin/products",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        request,
        "admin/products/view.html",
        {
            "request": request,
            "product": product,
            "flash": pop_flash(request),
        },
    )


@router.get("/{product_id:int}/edit")
def product_edit_form(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)

    if auth_redirect:
        return auth_redirect

    try:
        product = ProductService.get_by_id(db, product_id)
    except ProductNotFoundError:
        set_flash(
            request,
            "Product not found.",
            "danger",
        )
        return RedirectResponse(
            url="/admin/products",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    categories, brands = get_reference_data(db)

    return templates.TemplateResponse(
        request,
        "admin/products/edit.html",
        {
            "request": request,
            "product": product,
            "categories": categories,
            "brands": brands,
            "form_data": {},
            "errors": [],
            "flash": pop_flash(request),
        },
    )


@router.post("/{product_id:int}/edit")
async def product_update(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)

    if auth_redirect:
        return auth_redirect

    categories, brands = get_reference_data(db)
    raw_form = dict(await request.form())

    try:
        existing_product = ProductService.get_by_id(
            db,
            product_id,
        )

        payload_data = await build_product_payload(
            request,
            db,
            product_id=product_id,
        )
        payload = ProductUpdate.model_validate(payload_data)

        product = ProductService.update_product(
            db,
            product_id,
            payload,
        )

        set_flash(
            request,
            f"Product '{product.product_name}' updated successfully.",
        )

        return RedirectResponse(
            url=f"/admin/products/{product.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except ProductNotFoundError:
        set_flash(
            request,
            "Product not found.",
            "danger",
        )
        return RedirectResponse(
            url="/admin/products",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except (
        ProductConflictError,
        ProductValidationError,
    ) as exc:
        errors = [str(exc)]
        existing_product = ProductService.get_by_id(
            db,
            product_id,
        )

    except ValidationError as exc:
        errors = [validation_message(exc)]
        existing_product = ProductService.get_by_id(
            db,
            product_id,
        )

    return templates.TemplateResponse(
        request,
        "admin/products/edit.html",
        {
            "request": request,
            "product": existing_product,
            "categories": categories,
            "brands": brands,
            "form_data": raw_form,
            "errors": errors,
            "flash": None,
        },
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


@router.post("/{product_id:int}/delete")
def product_delete(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)

    if auth_redirect:
        return auth_redirect

    try:
        product = ProductService.soft_delete_product(
            db,
            product_id,
        )

        set_flash(
            request,
            f"Product '{product.product_name}' deleted successfully.",
        )

    except ProductNotFoundError:
        set_flash(
            request,
            "Product not found.",
            "danger",
        )

    return RedirectResponse(
        url="/admin/products",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{product_id:int}/toggle-status")
def product_toggle_status(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)

    if auth_redirect:
        return auth_redirect

    try:
        product = ProductService.toggle_product_status(
            db,
            product_id,
        )

        state = "activated" if product.is_active else "deactivated"

        set_flash(
            request,
            f"Product '{product.product_name}' {state}.",
        )

    except ProductNotFoundError:
        set_flash(
            request,
            "Product not found.",
            "danger",
        )

    referer = request.headers.get(
        "referer",
        "/admin/products",
    )

    return RedirectResponse(
        url=referer,
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{product_id:int}/images")
async def product_image_upload(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)
    if auth_redirect:
        return auth_redirect

    form = await request.form()
    image = form.get("image")
    if not isinstance(image, UploadFile):
        set_flash(request, "Select an image to upload.", "danger")
        return RedirectResponse(
            url=f"/admin/products/{product_id}#product-images",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    alt_text = optional_text(form.get("alt_text"))
    try:
        await ProductImageService.upload(
            db,
            product_id,
            image,
            alt_text=alt_text,
        )
        set_flash(request, "Product image uploaded successfully.")
    except (ProductImageError, ProductNotFoundError) as exc:
        set_flash(request, str(exc), "danger")
    finally:
        await image.close()

    return RedirectResponse(
        url=f"/admin/products/{product_id}#product-images",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{product_id:int}/images/{image_id:int}/primary")
def product_image_primary(
    product_id: int,
    image_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)
    if auth_redirect:
        return auth_redirect
    try:
        ProductImageService.set_primary(db, product_id, image_id)
        set_flash(request, "Primary product image updated.")
    except ProductImageError as exc:
        set_flash(request, str(exc), "danger")
    return RedirectResponse(
        url=f"/admin/products/{product_id}#product-images",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{product_id:int}/images/{image_id:int}/move")
def product_image_move(
    product_id: int,
    image_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)
    if auth_redirect:
        return auth_redirect
    direction = str(request.query_params.get("direction", ""))
    if direction not in {"up", "down"}:
        set_flash(request, "Invalid image position request.", "danger")
    else:
        try:
            ProductImageService.move(db, product_id, image_id, direction)
        except ProductImageError as exc:
            set_flash(request, str(exc), "danger")
    return RedirectResponse(
        url=f"/admin/products/{product_id}#product-images",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{product_id:int}/images/{image_id:int}/delete")
def product_image_delete(
    product_id: int,
    image_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_redirect = require_admin(request)
    if auth_redirect:
        return auth_redirect
    try:
        ProductImageService.delete(db, product_id, image_id)
        set_flash(request, "Product image deleted.")
    except ProductImageError as exc:
        set_flash(request, str(exc), "danger")
    return RedirectResponse(
        url=f"/admin/products/{product_id}#product-images",
        status_code=status.HTTP_303_SEE_OTHER,
    )
