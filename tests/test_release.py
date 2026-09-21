from importlib.metadata import PackageNotFoundError, version as package_version
import tomllib
from pathlib import Path

import pytest

from app.core.openapi import API_VERSION
from scripts.bootstrap_admin import InitialAdminConfigurationError, ensure_initial_admin
from scripts.smoke_test import EXPECTED_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent(client) -> None:
    assert API_VERSION == "1.0.0"
    assert EXPECTED_VERSION == API_VERSION
    try:
        installed_version = package_version("securedesk")
    except PackageNotFoundError:
        pyproject = ROOT / "pyproject.toml"
        installed_version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert installed_version == API_VERSION

    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["version"] == API_VERSION


def test_bootstrap_validation_does_not_echo_invalid_password(db) -> None:
    invalid_password = "THISPASSWORDHASNOLOWERCASE123"

    with pytest.raises(InitialAdminConfigurationError) as exc_info:
        ensure_initial_admin(
            db,
            email="owner@example.com",
            password=invalid_password,
        )

    message = str(exc_info.value)
    assert invalid_password not in message
    assert "validation rules" in message


def test_release_frontend_identifies_v1_when_checkout_is_available() -> None:
    frontend = ROOT / "frontend" / "index.html"
    if not frontend.exists():
        # The API development image intentionally does not copy frontend sources.
        return

    html = frontend.read_text(encoding="utf-8")
    assert "SecureDesk v1.0.0" in html
    assert "Ambiente local" not in html


def test_release_documentation_when_checkout_is_available() -> None:
    readme = ROOT / "README.md"
    changelog = ROOT / "CHANGELOG.md"
    if not readme.exists() or not changelog.exists():
        return

    readme_text = readme.read_text(encoding="utf-8")
    changelog_text = changelog.read_text(encoding="utf-8")

    assert "https://securedesk-e2pb.onrender.com" in readme_text
    assert "V1.0.6 — polimento e release `v1.0.0`" in readme_text
    assert "## [1.0.0]" in changelog_text
