import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as _app_models  # noqa: F401
from app.core.config import settings
from app.core.rate_limit import rate_limiter
from app.db import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def override_get_db():
    with TestingSessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "attachments_dir", str(tmp_path / "attachments"))
    monkeypatch.setattr(settings, "attachment_max_bytes", 5 * 1024 * 1024)
    rate_limiter.reset()
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    rate_limiter.reset()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db() -> Session:
    with TestingSessionLocal() as session:
        yield session
