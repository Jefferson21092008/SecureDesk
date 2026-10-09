"""Fault-injection checks for attachment storage (no network or real DB required)."""

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.core.config import settings
from app.services import attachment_storage as storage


def _upload(content: bytes = b"complete attachment") -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename="evidence.txt",
        headers=Headers({"content-type": "text/plain"}),
    )


def _configure_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "attachments"
    monkeypatch.setattr(settings, "attachments_dir", str(root))
    monkeypatch.setattr(settings, "attachment_max_bytes", 5 * 1024 * 1024)
    return root


def test_upload_is_published_only_after_complete_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _configure_storage(tmp_path, monkeypatch)
    content = b"complete attachment" * 1024
    original_replace = storage.os.replace
    observed = []

    def assert_then_replace(source, destination):
        assert Path(source).read_bytes() == content
        assert Path(source).parent == root.resolve()
        assert Path(source).suffix == ".part"
        assert not Path(destination).exists()
        observed.append(True)
        original_replace(source, destination)

    monkeypatch.setattr(storage.os, "replace", assert_then_replace)
    filename, key, content_type, size_bytes = storage.store_upload(_upload(content))

    assert observed == [True]
    assert filename == "evidence.txt"
    assert content_type == "text/plain"
    assert size_bytes == len(content)
    assert (root / key).read_bytes() == content
    assert list(root.glob(".upload-*.part")) == []


def test_oversize_upload_does_not_leave_temporary_or_final_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "attachment_max_bytes", 3)

    with pytest.raises(HTTPException) as error:
        storage.store_upload(_upload(b"1234"))

    assert error.value.status_code == 413
    assert list(root.iterdir()) == []


def test_failed_atomic_promotion_cleans_up_and_returns_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _configure_storage(tmp_path, monkeypatch)

    def fail_replace(_source, _destination):
        raise OSError("simulated permission failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)

    with pytest.raises(HTTPException) as error:
        storage.store_upload(_upload())

    assert error.value.status_code == 503
    assert error.value.detail == "Attachment storage temporarily unavailable"
    assert list(root.iterdir()) == []


def test_failed_temp_creation_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _configure_storage(tmp_path, monkeypatch)

    def fail_create(**_kwargs):
        raise OSError("simulated filesystem unavailable")

    monkeypatch.setattr(storage.tempfile, "NamedTemporaryFile", fail_create)

    with pytest.raises(HTTPException) as error:
        storage.store_upload(_upload())

    assert error.value.status_code == 503
    assert list(root.iterdir()) == []


def test_partial_write_error_removes_temporary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _configure_storage(tmp_path, monkeypatch)
    original_temp_factory = storage.tempfile.NamedTemporaryFile

    class FailingWriter:
        def __init__(self, real_file):
            self.real_file = real_file
            self.name = real_file.name

        def __enter__(self):
            self.real_file.__enter__()
            return self

        def __exit__(self, *args):
            return self.real_file.__exit__(*args)

        def write(self, chunk):
            self.real_file.write(chunk[:3])
            raise OSError("simulated full disk")

    def broken_temp_factory(**kwargs):
        return FailingWriter(original_temp_factory(**kwargs))

    monkeypatch.setattr(storage.tempfile, "NamedTemporaryFile", broken_temp_factory)

    with pytest.raises(HTTPException) as error:
        storage.store_upload(_upload())

    assert error.value.status_code == 503
    assert list(root.iterdir()) == []


def test_cleanup_success_and_missing_are_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _configure_storage(tmp_path, monkeypatch)
    key = storage.store_upload(_upload())[1]

    assert storage.delete_stored_file(key) is True
    assert storage.delete_stored_file(key) is True
    assert not (root / key).exists()


def test_failed_cleanup_logs_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    _configure_storage(tmp_path, monkeypatch)

    class BrokenPath:
        def unlink(self, *, missing_ok):
            raise OSError("simulated unavailable volume")

    monkeypatch.setattr(storage, "attachment_path", lambda _key: BrokenPath())

    with caplog.at_level("WARNING", logger="securedesk.attachments"):
        assert storage.delete_stored_file("abcdef123.txt") is False

    assert "attachment_cleanup_failed" in caplog.text
    assert "OSError" in caplog.text
    assert "simulated unavailable volume" not in caplog.text
