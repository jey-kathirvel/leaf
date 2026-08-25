from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import (
    generate_csrf_token,
    verify_password,
)
from app.db.deps import get_db
from app.models import (
    AdminUser,
    Category,
    Customer,
    Order,
    OrderStatus,
    PaymentStatus,
    Product,
)


BASE_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(
    directory=BASE_DIR / "templates",
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


def get_current_admin(
    request: Request,
    db: Session,
) -> AdminUser | None:
    admin_id = request.session.get("admin_user_id")

    if not admin_id:
        return None

    admin = db.scalar(
        select(AdminUser).where(
            AdminUser.id == int(admin_id),
            AdminUser.is_active.is_(True),
        )
    )

    if admin is None:
        request.session.clear()

    return admin


@router.get(
    "/login",
    response_class=HTMLResponse,
)
def admin_login_page(
    request: Request,
    db: Session = Depends(get_db),
):
    if get_current_admin(request, db):
        return RedirectResponse(
            url="/admin",
            status_code=303,
        )

    csrf_token = generate_csrf_token()
    request.session["admin_login_csrf"] = csrf_token

    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/login")
def admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    session_csrf = request.session.pop(
        "admin_login_csrf",
        None,
    )

    if (
        not session_csrf
        or not csrf_token
        or csrf_token != session_csrf
    ):
        return RedirectResponse(
            url=(
                "/admin/login?error="
                + quote("Invalid or expired login request.")
            ),
            status_code=303,
        )

    normalized_email = email.strip().lower()

    admin = db.scalar(
        select(AdminUser).where(
            func.lower(AdminUser.email)
            == normalized_email
        )
    )

    if (
        admin is None
        or not admin.is_active
        or not verify_password(
            password,
            admin.password_hash,
        )
    ):
        return RedirectResponse(
            url=(
                "/admin/login?error="
                + quote("Invalid email or password.")
            ),
            status_code=303,
        )

    admin.last_login_at = datetime.now(timezone.utc)
    db.commit()

    request.session.clear()
    request.session["admin_user_id"] = admin.id
    request.session["admin_role"] = admin.role

    return RedirectResponse(
        url="/admin",
        status_code=303,
    )


@router.post("/logout")
def admin_logout(
    request: Request,
):
    request.session.clear()

    return RedirectResponse(
        url="/admin/login",
        status_code=303,
    )


@router.get(
    "",
    response_class=HTMLResponse,
)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    admin = get_current_admin(request, db)

    if admin is None:
        return RedirectResponse(
            url="/admin/login",
            status_code=303,
        )

    metrics = {
        "products": db.scalar(
            select(func.count(Product.id))
        ) or 0,
        "categories": db.scalar(
            select(func.count(Category.id))
        ) or 0,
        "customers": db.scalar(
            select(func.count(Customer.id))
        ) or 0,
        "orders": db.scalar(
            select(func.count(Order.id))
        ) or 0,
    }

    recent_orders = db.scalars(
        select(Order)
        .order_by(Order.created_at.desc())
        .limit(8)
    ).all()

    csrf_token = request.session.get("admin_action_csrf")
    if not csrf_token:
        csrf_token = generate_csrf_token()
        request.session["admin_action_csrf"] = csrf_token

    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "request": request,
            "admin": admin,
            "metrics": metrics,
            "recent_orders": recent_orders,
            "statuses": list(OrderStatus),
            "payment_statuses": [
                PaymentStatus.PENDING,
                PaymentStatus.PAID,
                PaymentStatus.FAILED,
            ],
            "csrf_token": csrf_token,
        },
    )
