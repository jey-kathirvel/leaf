from datetime import datetime, time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.deps import get_db
from app.models import Customer, Order, OrderStatus, PaymentStatus
from app.routers.admin_products import require_admin, set_flash, pop_flash
from app.services.order_service import OrderWorkflowError, allowed_next_statuses, update_fulfilment


router = APIRouter(prefix="/admin/orders", tags=["Admin Orders"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def order_list(request: Request, q: str = "", status: str = "", date_from: str = "", date_to: str = "", db: Session = Depends(get_db)):
    redirect = require_admin(request)
    if redirect:
        return redirect
    filters = []
    if q.strip():
        term = f"%{q.strip()}%"
        filters.append(or_(Order.order_number.ilike(term), Customer.email.ilike(term), Order.tracking_number.ilike(term)))
    if status:
        try:
            filters.append(Order.status == OrderStatus(status))
        except ValueError:
            status = ""
    if date_from:
        try:
            filters.append(Order.created_at >= datetime.combine(datetime.strptime(date_from, "%Y-%m-%d").date(), time.min))
        except ValueError:
            date_from = ""
    if date_to:
        try:
            filters.append(Order.created_at <= datetime.combine(datetime.strptime(date_to, "%Y-%m-%d").date(), time.max))
        except ValueError:
            date_to = ""
    orders = db.scalars(
        select(Order).outerjoin(Customer)
        .options(selectinload(Order.customer), selectinload(Order.items))
        .where(*filters)
        .order_by(Order.created_at.desc())
        .limit(100)
    ).all()
    return templates.TemplateResponse(request, "admin/orders/list.html", {"request": request, "orders": orders, "statuses": list(OrderStatus), "filters": {"q": q, "status": status, "date_from": date_from, "date_to": date_to}, "flash": pop_flash(request)})


@router.get("/{order_id:int}", response_class=HTMLResponse)
def order_detail(order_id: int, request: Request, db: Session = Depends(get_db)):
    redirect = require_admin(request)
    if redirect:
        return redirect
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.customer), selectinload(Order.items), selectinload(Order.shipping_address), selectinload(Order.status_history))
        .where(Order.id == order_id)
    )
    if not order:
        return RedirectResponse("/admin/orders", status_code=303)
    return templates.TemplateResponse(request, "admin/orders/view.html", {"request": request, "order": order, "next_statuses": allowed_next_statuses(order.status), "flash": pop_flash(request)})


@router.post("/{order_id:int}/fulfilment")
def order_fulfilment(
    order_id: int,
    request: Request,
    target_status: str = Form(...),
    courier_name: str = Form(""),
    tracking_number: str = Form(""),
    internal_notes: str = Form(""),
    status_note: str = Form(""),
    db: Session = Depends(get_db),
):
    redirect = require_admin(request)
    if redirect:
        return redirect
    try:
        update_fulfilment(db, order_id, target_status, courier_name, tracking_number, internal_notes, status_note)
        set_flash(request, "Order fulfilment details updated.")
    except OrderWorkflowError as exc:
        db.rollback()
        set_flash(request, str(exc), "danger")
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


@router.post("/{order_id:int}/payment")
def order_payment_update(
    order_id: int,
    request: Request,
    payment_status: str = Form(...),
    payment_reference: str = Form(""),
    db: Session = Depends(get_db),
):
    redirect = require_admin(request)
    if redirect:
        return redirect
    order = db.get(Order, order_id)
    if not order:
        return RedirectResponse("/admin/orders", status_code=303)
    try:
        target = PaymentStatus(payment_status)
    except ValueError:
        set_flash(request, "Choose a valid payment status.", "danger")
        return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)
    if target not in {PaymentStatus.PENDING, PaymentStatus.PAID, PaymentStatus.FAILED}:
        set_flash(request, "This payment status cannot be set manually.", "danger")
        return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)
    order.payment_status = target
    order.payment_reference = payment_reference.strip() or order.payment_reference
    db.commit()
    set_flash(request, f"Payment marked {target.value}.")
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)
