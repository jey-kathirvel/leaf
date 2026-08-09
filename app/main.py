import os
from pathlib import Path

from fastapi import FastAPI
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

# Router imports are intentionally placed after application initialization
# and route declarations to prevent circular-import registration issues.
from app.routers.admin_auth import router as admin_router
from app.routers import admin_products
from app.routers.store import router as store_router
from app.routers.checkout import router as checkout_router
from app.routers.admin_orders import router as admin_orders_router

app.include_router(store_router)
app.include_router(checkout_router)
app.include_router(admin_router)
app.include_router(admin_products.router)
app.include_router(admin_orders_router)
