"""Supabase S3 configuration safety and boto3 endpoint tests (no network)."""

from urllib.parse import urlsplit

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.services import attachment_s3


def _valid_options():
    return dict(
        attachment_storage_backend="s3",
        s3_endpoint_url="https://fake-project.storage.supabase.co/storage/v1/s3",
        s3_bucket_name="securedesk-attachments",
        s3_access_key_id="fake-access-id",
        s3_secret_access_key="fake-secret",
        s3_region="sa-east-1",
    )


def test_supabase_s3_requires_credentials_and_complete_endpoint():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, attachment_storage_backend="s3")
    for url in (
        "http://fake-project.storage.supabase.co/storage/v1/s3",
        "https://fake-project.supabase.co",
        "https://fake-project.supabase.co/storage/v1/object/public/bucket",
        "https://fake-project.supabase.co/storage/v1/s3?x=1",
        "https://fake-project.supabase.co.evil.test/storage/v1/s3",
        "https://fake-project.supabase.co:8443/storage/v1/s3",
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{**_valid_options(), "s3_endpoint_url": url})


def test_supabase_s3_endpoint_and_secret_handling():
    config = Settings(_env_file=None, **_valid_options())
    assert config.attachment_storage_backend == "s3"
    assert config.s3_region == "sa-east-1"
    assert config.s3_endpoint_url.endswith("/storage/v1/s3")
    assert "fake-secret" not in repr(config)
    # The standard hostname without .storage also works.
    config = Settings(
        _env_file=None,
        **{**_valid_options(), "s3_endpoint_url": "https://fake-project.supabase.co/storage/v1/s3"},
    )
    assert urlsplit(config.s3_endpoint_url).hostname == "fake-project.supabase.co"


def test_boto3_client_uses_supabase_region_path_style_and_explicit_keys(monkeypatch):
    captured = {}

    def fake_client(service, **kw):
        captured["service"] = service
        captured.update(kw)
        return object()

    monkeypatch.setattr(attachment_s3.boto3, "client", fake_client)
    opts = _valid_options()
    for key, value in opts.items():
        if key == "s3_secret_access_key":
            from pydantic import SecretStr
            value = SecretStr(value)
        monkeypatch.setattr(settings, key, value)
    attachment_s3._client()
    assert captured["service"] == "s3"
    assert captured["endpoint_url"] == opts["s3_endpoint_url"]
    assert captured["region_name"] == "sa-east-1"
    assert captured["config"].s3["addressing_style"] == "path"
    assert captured["config"].signature_version == "s3v4"
    assert captured["aws_access_key_id"] == "fake-access-id"
    assert captured["aws_secret_access_key"] == "fake-secret"
