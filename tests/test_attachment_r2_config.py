"""Configuration safety checks do not access R2 or PostgreSQL."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_r2_requires_private_https_endpoint_and_credentials():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, attachment_storage_backend="r2")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            attachment_storage_backend="r2",
            r2_endpoint_url="http://insecure.example.com",
            r2_bucket_name="private",
            r2_access_key_id="access",
            r2_secret_access_key="secret",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            attachment_storage_backend="r2",
            r2_endpoint_url="https://account.r2.cloudflarestorage.com/presigned",
            r2_bucket_name="private",
            r2_access_key_id="access",
            r2_secret_access_key="secret",
        )


def test_r2_https_configuration_validates_and_hides_secret():
    config = Settings(
        _env_file=None,
        attachment_storage_backend="r2",
        r2_endpoint_url="https://account.r2.cloudflarestorage.com",
        r2_bucket_name="private",
        r2_access_key_id="access",
        r2_secret_access_key="not-a-real-secret",
    )
    assert config.attachment_storage_backend == "r2"
    assert "not-a-real-secret" not in repr(config)
