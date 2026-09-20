from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
FRONTEND_URL = "http://frontend"


def _served_text(path: str) -> str:
    with urlopen(f"{FRONTEND_URL}{path}", timeout=3) as response:  # noqa: S310
        assert response.status == 200
        return response.read().decode("utf-8")


def test_frontend_shell_files_exist() -> None:
    if FRONTEND.exists():
        expected = {"index.html", "styles.css", "app.js", "nginx.conf", "Dockerfile"}
        assert expected <= {path.name for path in FRONTEND.iterdir()}
        return

    assert "SecureDesk" in _served_text("/")
    assert _served_text("/styles.css").strip()
    assert _served_text("/app.js").strip()


def test_frontend_is_self_contained() -> None:
    index = (FRONTEND / "index.html").read_text(encoding="utf-8") if FRONTEND.exists() else _served_text("/")

    assert 'href="/styles.css"' in index
    assert 'src="/app.js"' in index
    assert "cdnjs" not in index
    assert "unpkg" not in index


def test_frontend_is_exposed_by_compose() -> None:
    compose_path = ROOT / "docker-compose.yml"
    if compose_path.exists():
        compose = compose_path.read_text(encoding="utf-8")
        assert "frontend:" in compose
        assert '"3000:80"' in compose
        return

    assert "SecureDesk" in _served_text("/")


def test_frontend_proxies_api_through_same_origin() -> None:
    if FRONTEND.exists():
        nginx = (FRONTEND / "nginx.conf").read_text(encoding="utf-8")
        assert "location /api/" in nginx
        assert "proxy_pass http://api:8000/;" in nginx
        return

    assert '"status":"ok"' in _served_text("/api/health")


def test_frontend_uses_real_api_session() -> None:
    app_js = (FRONTEND / "app.js").read_text(encoding="utf-8") if FRONTEND.exists() else _served_text("/app.js")
    index = (FRONTEND / "index.html").read_text(encoding="utf-8") if FRONTEND.exists() else _served_text("/")

    assert 'const API_BASE = "/api";' in app_js
    assert "sessionStorage" in app_js
    assert 'apiRequest("/auth/login"' in app_js
    assert 'apiRequest("/auth/me"' in app_js
    assert "modo demonstração" not in index.lower()
