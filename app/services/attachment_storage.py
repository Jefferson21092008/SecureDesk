from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

CHUNK_SIZE = 1024 * 1024
ALLOWED_ATTACHMENT_TYPES: dict[str, set[str]] = {
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "text/plain": {".txt", ".log"},
}


def _storage_root() -> Path:
    root = Path(settings.attachments_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def attachment_path(storage_key: str) -> Path:
    root = _storage_root()
    if not storage_key or Path(storage_key).name != storage_key or storage_key in {".", ".."}:
        raise ValueError("Invalid attachment storage key")

    candidate = (root / storage_key).resolve()
    if candidate.parent != root:
        raise ValueError("Attachment path escapes storage root")
    return candidate


def _validate_upload(upload: UploadFile) -> tuple[str, str]:
    original_filename = (upload.filename or "").replace("\\", "/").split("/")[-1].strip()
    if not original_filename or len(original_filename) > 255:
        raise HTTPException(status_code=400, detail="Invalid attachment filename")
    if any(ord(char) < 32 or ord(char) == 127 for char in original_filename):
        raise HTTPException(status_code=400, detail="Invalid attachment filename")

    content_type = upload.content_type or ""
    allowed_extensions = ALLOWED_ATTACHMENT_TYPES.get(content_type)
    extension = Path(original_filename).suffix.lower()
    if allowed_extensions is None or extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported attachment type",
        )

    return original_filename, content_type


def _validate_content_signature(content_type: str, sample: bytes) -> None:
    matches = False
    if content_type == "application/pdf":
        matches = b"%PDF-" in sample[:1024]
    elif content_type == "image/png":
        matches = sample.startswith(b"\x89PNG\r\n\x1a\n")
    elif content_type == "image/jpeg":
        matches = sample.startswith(b"\xff\xd8\xff")
    elif content_type == "text/plain":
        try:
            sample.decode("utf-8")
            matches = b"\x00" not in sample
        except UnicodeDecodeError:
            matches = False

    if not matches:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Attachment content does not match declared type",
        )


def store_upload(upload: UploadFile) -> tuple[str, str, str, int]:
    original_filename, content_type = _validate_upload(upload)
    extension = Path(original_filename).suffix.lower()
    storage_key = f"{uuid4().hex}{extension}"
    destination = attachment_path(storage_key)
    size_bytes = 0

    try:
        first_chunk = upload.file.read(CHUNK_SIZE)
        if not first_chunk:
            raise HTTPException(status_code=400, detail="Attachment cannot be empty")
        _validate_content_signature(content_type, first_chunk)

        with destination.open("xb") as output:
            chunk = first_chunk
            while chunk:
                size_bytes += len(chunk)
                if size_bytes > settings.attachment_max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Attachment exceeds maximum allowed size",
                    )
                output.write(chunk)
                chunk = upload.file.read(CHUNK_SIZE)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        upload.file.close()

    return original_filename, storage_key, content_type, size_bytes


def delete_stored_file(storage_key: str) -> None:
    try:
        attachment_path(storage_key).unlink(missing_ok=True)
    except (OSError, ValueError):
        # Database state is authoritative. Storage cleanup can be retried separately
        # if the local filesystem is unavailable or a stored key is malformed.
        pass
