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

    # The API image intentionally does not copy the frontend source tree.
    # Under Docker Compose, validate the built frontend service instead.
    assert "SecureDesk" in _served_text("/")
    assert _served_text("/styles.css").strip()
    assert _served_text("/app.js").strip()


def test_frontend_is_self_contained() -> None:
    if FRONTEND.exists():
        index = (FRONTEND / "index.html").read_text(encoding="utf-8")
    else:
        index = _served_text("/")

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

    # Inside the API container the compose file is intentionally absent,
    # so verify that Compose networking exposes the frontend service.
    assert "SecureDesk" in _served_text("/")
