from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.deps import get_db
from app.models import Order
from app.routers.admin_products import require_admin


router = APIRouter(prefix="/admin/orders", tags=["Admin Orders"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def order_list(request: Request, db: Session = Depends(get_db)):
    redirect = require_admin(request)
    if redirect:
        return redirect
    orders = db.scalars(
        select(Order)
        .options(selectinload(Order.customer), selectinload(Order.items))
        .order_by(Order.created_at.desc())
    ).all()
    return templates.TemplateResponse(request, "admin/orders/list.html", {"request": request, "orders": orders})


@router.get("/{order_id:int}", response_class=HTMLResponse)
def order_detail(order_id: int, request: Request, db: Session = Depends(get_db)):
    redirect = require_admin(request)
    if redirect:
        return redirect
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.customer), selectinload(Order.items), selectinload(Order.shipping_address))
        .where(Order.id == order_id)
    )
    if not order:
        return RedirectResponse("/admin/orders", status_code=303)
    return templates.TemplateResponse(request, "admin/orders/view.html", {"request": request, "order": order})
