import json
import struct
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_pwa_manifest_and_service_worker_routes() -> None:
    client = TestClient(app, base_url="https://testserver")
    manifest_response = client.get("/manifest.webmanifest")
    worker_response = client.get("/service-worker.js")
    offline_response = client.get("/offline")

    assert manifest_response.status_code == 200
    assert manifest_response.headers["content-type"].startswith("application/manifest+json")
    manifest = json.loads(manifest_response.text)
    assert manifest["name"] == "Leaf Organic Store"
    assert manifest["display"] == "standalone"
    assert "standalone" in manifest["display_override"]
    assert manifest["prefer_related_applications"] is False
    assert manifest["start_url"].startswith("/")
    assert {icon["sizes"] for icon in manifest["icons"]} >= {"192x192", "512x512"}

    assert worker_response.status_code == 200
    assert worker_response.headers["service-worker-allowed"] == "/"
    assert "no-cache" in worker_response.headers["cache-control"]
    assert '"/admin"' in worker_response.text
    assert '"/checkout"' in worker_response.text
    assert 'store.css?v=organic-4' in worker_response.text
    assert 'store.js?v=organic-2' in worker_response.text
    assert offline_response.status_code == 200
    assert "currently offline" in offline_response.text


def test_pwa_icons_have_declared_dimensions() -> None:
    icon_root = Path("app/static/icons")
    assert png_size(icon_root / "icon-192.png") == (192, 192)
    assert png_size(icon_root / "icon-512.png") == (512, 512)
    assert png_size(icon_root / "icon-maskable-512.png") == (512, 512)


def test_storefront_layout_declares_pwa_metadata() -> None:
    template = Path("app/templates/layouts/store_base.html").read_text(encoding="utf-8")
    script = Path("app/static/js/store.js").read_text(encoding="utf-8")
    assert 'rel="manifest" href="/manifest.webmanifest"' in template
    assert 'name="theme-color" content="#0D1A14"' in template
    assert 'rel="apple-touch-icon"' in template
    assert 'navigator.serviceWorker.register("/service-worker.js")' in script
    assert 'beforeinstallprompt' in script
    assert 'SKIP_WAITING' in script
    assert 'id="pwaInstallButton"' in template
    assert 'id="pwaUpdateToast"' not in template
