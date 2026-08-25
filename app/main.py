import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings


BASE_DIR = Path(__file__).resolve().parent

SESSION_SECRET = os.getenv(
    "SESSION_SECRET_KEY",
    os.getenv(
        "SECRET_KEY",
        "leaf-store-change-this-session-secret",
    ),
)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    debug=settings.DEBUG,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="leaf_admin_session",
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=True,
)

app.mount(
    "/static",
    StaticFiles(
        directory=BASE_DIR / "static",
    ),
    name="static",
)

app.mount(
    "/uploads",
    StaticFiles(directory=settings.UPLOAD_DIR, check_dir=False),
    name="uploads",
)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "application": settings.APP_NAME,
        "environment": settings.APP_ENV,
    }


@app.get("/manifest.webmanifest", include_in_schema=False)
async def web_manifest():
    return FileResponse(
        BASE_DIR / "static" / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/service-worker.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        BASE_DIR / "static" / "service-worker.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Service-Worker-Allowed": "/",
        },
    )


@app.get("/offline", include_in_schema=False)
async def offline_page():
    return FileResponse(
        BASE_DIR / "static" / "offline.html",
        media_type="text/html",
        headers={"Cache-Control": "public, max-age=86400"},
    )

# Router imports are intentionally placed after application initialization
# and route declarations to prevent circular-import registration issues.
from app.routers.admin_auth import router as admin_router
from app.routers.admin_product_delete import router as admin_product_delete_router
from app.routers import admin_products
from app.routers.store import router as store_router
from app.routers.checkout import router as checkout_router
from app.routers.admin_orders import router as admin_orders_router
from app.routers.admin_operations import router as admin_operations_router
from app.routers.customer_account import router as customer_account_router

app.include_router(store_router)
app.include_router(checkout_router)
app.include_router(admin_router)
# Register this before the legacy admin_products router so product-delete POSTs
# always use the guarded direct-update handler.
app.include_router(admin_product_delete_router)
app.include_router(admin_products.router)
app.include_router(admin_orders_router)
app.include_router(admin_operations_router)
app.include_router(customer_account_router)
