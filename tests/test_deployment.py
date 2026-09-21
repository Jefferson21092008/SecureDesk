from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.core.rate_limit import client_ip
from app.models.user import UserRole
from scripts.bootstrap_admin import ensure_initial_admin

ROOT = Path(__file__).resolve().parents[1]


def test_managed_postgres_url_uses_psycopg3_driver() -> None:
    config = Settings(database_url="postgresql://user:pass@db.internal:5432/securedesk")
    assert config.database_url == "postgresql+psycopg://user:pass@db.internal:5432/securedesk"


def test_client_ip_can_use_trusted_proxy_header(monkeypatch) -> None:
    app = FastAPI()

    @app.get("/")
    def read_ip(request: Request) -> dict[str, str]:
        return {"ip": client_ip(request)}

    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    response = TestClient(app).get("/", headers={"X-Forwarded-For": "203.0.113.8, 10.0.0.5"})
    assert response.json() == {"ip": "203.0.113.8"}


def test_bootstrap_creates_admin(db) -> None:
    admin = ensure_initial_admin(
        db,
        email="owner@example.com",
        password="VeryStrong!Admin2026",
    )
    assert admin.email == "owner@example.com"
    assert admin.role == UserRole.ADMIN


def test_render_blueprint_declares_complete_stack() -> None:
    blueprint_path = ROOT / "render.yaml"
    if not blueprint_path.exists():
        # The development API image intentionally does not copy deployment IaC.
        # GitHub CI runs this assertion from the repository checkout.
        return
    blueprint = blueprint_path.read_text(encoding="utf-8")
    assert "name: securedesk" in blueprint
    assert "databases:" not in blueprint
    assert "generateValue: true" in blueprint
    assert "key: DATABASE_URL" in blueprint
    assert "sync: false" in blueprint
    assert "healthCheckPath: /api/health" in blueprint
    assert "APP_ENV" in blueprint and "production" in blueprint


def test_production_image_serves_frontend_and_api() -> None:
    production_dockerfile = ROOT / "docker" / "Dockerfile.production"
    if not production_dockerfile.exists():
        return
    api_dockerfile = production_dockerfile.read_text(encoding="utf-8")
    nginx_template = (ROOT / "docker" / "nginx.production.conf.template").read_text(encoding="utf-8")
    start_script = (ROOT / "docker" / "start-production.sh").read_text(encoding="utf-8")

    assert "pip install --no-cache-dir ." in api_dockerfile
    assert '".[dev]"' not in api_dockerfile
    assert "frontend/index.html" in api_dockerfile
    assert "bootstrap_admin.py" in start_script
    assert "uvicorn app.main:app --host 127.0.0.1 --port 8000" in start_script
    assert "nginx -g 'daemon off;'" in start_script
    assert "proxy_pass http://127.0.0.1:8000/;" in nginx_template
    assert "X-Forwarded-For" in nginx_template
