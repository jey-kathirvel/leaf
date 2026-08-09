import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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

templates = Jinja2Templates(
    directory=BASE_DIR / "templates",
)



FEATURED_PRODUCTS = [
    {
        "id": 1,
        "name": "Everyday Essentials Pack",
        "slug": "everyday-essentials-pack",
        "category": "Essentials",
        "price": 499.00,
        "badge": "Popular",
    },
    {
        "id": 2,
        "name": "Premium Home Collection",
        "slug": "premium-home-collection",
        "category": "Home & Living",
        "price": 899.00,
        "badge": "New",
    },
    {
        "id": 3,
        "name": "Modern Lifestyle Kit",
        "slug": "modern-lifestyle-kit",
        "category": "Lifestyle",
        "price": 749.00,
        "badge": None,
    },
    {
        "id": 4,
        "name": "Leaf Featured Selection",
        "slug": "leaf-featured-selection",
        "category": "Featured",
        "price": 1299.00,
        "badge": "Featured",
    },
]


@app.api_route(
    "/",
    methods=["GET", "HEAD"],
    response_class=HTMLResponse,
)
async def home(request: Request):
    return templates.TemplateResponse(
        request,
        "store/home.html",
        {
            "request": request,
            "featured_products": FEATURED_PRODUCTS,
            "current_year": datetime.now().year,
        },
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

app.include_router(admin_router)
app.include_router(admin_products.router)
