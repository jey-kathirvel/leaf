from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from fastapi.testclient import TestClient

from app.main import app
from app.db.deps import get_db
from app.routers import admin_products
from tests.test_product_service import database_session


EXPECTED_ROUTES = {
    ("GET", "/admin/products"),
    ("GET", "/admin/products/"),
    ("GET", "/admin/products/create"),
    ("POST", "/admin/products/create"),
    ("GET", "/admin/products/{product_id:int}"),
    ("GET", "/admin/products/{product_id:int}/edit"),
    ("POST", "/admin/products/{product_id:int}/edit"),
    ("POST", "/admin/products/{product_id:int}/delete"),
    ("POST", "/admin/products/{product_id:int}/toggle-status"),
    ("POST", "/admin/products/{product_id:int}/images"),
    ("POST", "/admin/products/{product_id:int}/images/{image_id:int}/primary"),
    ("POST", "/admin/products/{product_id:int}/images/{image_id:int}/move"),
    ("POST", "/admin/products/{product_id:int}/images/{image_id:int}/delete"),
}

EXPECTED_TEMPLATES = {
    "admin/products/list.html",
    "admin/products/create.html",
    "admin/products/edit.html",
    "admin/products/view.html",
}


def registered_routes(application) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()

    for route in application.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()

        for method in methods:
            result.add((method.upper(), path))

    return result


def test_admin_product_router_contains_expected_routes() -> None:
    routes = registered_routes(admin_products.router)

    missing = EXPECTED_ROUTES - routes

    assert not missing, (
        "Product router is missing routes: "
        + ", ".join(
            sorted(
                f"{method} {path}"
                for method, path in missing
            )
        )
    )


def test_application_contains_expected_product_routes() -> None:
    routes = registered_routes(app)

    missing = EXPECTED_ROUTES - routes

    assert not missing, (
        "FastAPI application is missing product routes: "
        + ", ".join(
            sorted(
                f"{method} {path}"
                for method, path in missing
            )
        )
    )


def test_product_route_identities_are_unique() -> None:
    route_identities = []

    for route in app.routes:
        path = getattr(route, "path", "")

        if not path.startswith("/admin/products"):
            continue

        methods = tuple(
            sorted(
                getattr(route, "methods", set()) or set()
            )
        )

        route_identities.append(
            (
                methods,
                path,
            )
        )

    assert route_identities

    assert len(route_identities) == len(
        set(route_identities)
    ), (
        "Duplicate product route method/path pairs found: "
        f"{route_identities}"
    )


def test_product_templates_exist_and_compile() -> None:
    template_root = Path("app/templates")

    environment = Environment(
        loader=FileSystemLoader(str(template_root)),
        autoescape=True,
    )

    for template_name in EXPECTED_TEMPLATES:
        template_path = template_root / template_name

        assert template_path.exists(), (
            f"Template does not exist: {template_name}"
        )

        environment.get_template(template_name)


def test_product_templates_use_expected_actions() -> None:
    template_root = Path("app/templates/admin/products")

    list_content = (
        template_root / "list.html"
    ).read_text(encoding="utf-8")

    create_content = (
        template_root / "create.html"
    ).read_text(encoding="utf-8")

    edit_content = (
        template_root / "edit.html"
    ).read_text(encoding="utf-8")

    view_content = (
        template_root / "view.html"
    ).read_text(encoding="utf-8")

    assert "/admin/products/create" in create_content

    assert (
        "/admin/products/{{ product.id }}/edit"
        in edit_content
    )

    assert (
        "/admin/products/{{ product.id }}/delete"
        in view_content
    )

    assert (
        "/admin/products/{{ product.id }}/toggle-status"
        in view_content
    )

    assert "/admin/products" in list_content


def test_image_upload_checks_authentication_before_form_validation() -> None:
    client = TestClient(app)
    response = client.post(
        "/admin/products/1/images",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_public_pages_use_https_safe_root_relative_assets() -> None:
    db = database_session()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    try:
        storefront = client.get("/")
        login = client.get("/admin/login")
    finally:
        app.dependency_overrides.clear()
        db.close()

    assert storefront.status_code == 200
    assert login.status_code == 200
    assert 'href="/static/css/store.css?v=atelier-3"' in storefront.text
    assert 'src="/static/js/store.js?v=atelier-2"' in storefront.text
    assert '/static/images/leaf-fashion-hero.png' in Path("app/static/css/store.css").read_text(encoding="utf-8")
    assert 'href="/static/css/admin.css?v=atelier-1"' in login.text
    assert "http://leaf.ads-ai.in/static" not in storefront.text
    assert "http://leaf.ads-ai.in/static" not in login.text
