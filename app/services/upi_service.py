import base64
from io import BytesIO
from urllib.parse import urlencode

import qrcode

from app.core.config import settings
from app.models import Order


def upi_is_available() -> bool:
    return settings.UPI_ENABLED and bool(settings.UPI_VPA)


def build_upi_uri(order: Order) -> str:
    if not upi_is_available():
        raise ValueError("UPI payment is not configured.")
    query = urlencode(
        {
            "pa": settings.UPI_VPA,
            "pn": settings.UPI_PAYEE_NAME,
            "tr": order.order_number,
            "tn": f"Leaf order {order.order_number}",
            "am": f"{order.grand_total:.2f}",
            "cu": "INR",
        }
    )
    return f"upi://pay?{query}"


def qr_data_uri(value: str) -> str:
    image = qrcode.make(value)
    output = BytesIO()
    image.save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def payment_details(order: Order) -> dict[str, str]:
    uri = build_upi_uri(order)
    return {
        "uri": uri,
        "qr_data_uri": qr_data_uri(uri),
        "vpa": settings.UPI_VPA,
        "payee_name": settings.UPI_PAYEE_NAME,
    }
