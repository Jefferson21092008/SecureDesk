"""Private Supabase Storage S3-compatible storage for ticket attachments.

The API, never a public bucket URL, is the authorization boundary. Keep the
bucket private and do not create presigned/public URLs for these objects.
"""

import logging
import re
from tempfile import SpooledTemporaryFile
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.services.attachment_storage import (
    CHUNK_SIZE,
    _validate_content_signature,
    _validate_upload,
)

logger = logging.getLogger("securedesk.attachments")

# No paths or arbitrary client-provided keys are accepted by the S3 backend.
_STORAGE_KEY_PATTERN = re.compile(r"[0-9a-f]{32}\.(?:pdf|png|jpe?g|txt|log)\Z")
_S3_ERRORS = (BotoCoreError, ClientError, OSError)


def _validated_key(storage_key: str) -> str:
    if not _STORAGE_KEY_PATTERN.fullmatch(storage_key):
        raise ValueError("Invalid S3 storage key")
    return storage_key


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        region_name=settings.s3_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=20,
            retries={"mode": "standard", "max_attempts": 2},
        ),
    )


def store_s3_upload(upload: UploadFile) -> tuple[str, str, str, int]:
    """Validate and upload a bounded file to a private bucket; no local final copy."""
    key = None
    uploaded = False
    try:
        original_filename, content_type = _validate_upload(upload)
        extension = "." + original_filename.rsplit(".", 1)[-1].lower()
        key = _validated_key(f"{uuid4().hex}{extension}")

        # Spool to RAM for small files, disk for larger files. Never exceed the
        # configured limit; do not hold the entire file in process memory.
        with SpooledTemporaryFile(max_size=CHUNK_SIZE, mode="w+b") as staged:
            first_chunk = upload.file.read(CHUNK_SIZE)
            if not first_chunk:
                raise HTTPException(status_code=400, detail="Attachment cannot be empty")
            _validate_content_signature(content_type, first_chunk)

            size_bytes = 0
            chunk = first_chunk
            while chunk:
                size_bytes += len(chunk)
                if size_bytes > settings.attachment_max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Attachment exceeds maximum allowed size",
                    )
                staged.write(chunk)
                chunk = upload.file.read(CHUNK_SIZE)
            staged.seek(0)
            _client().put_object(
                Bucket=settings.s3_bucket_name,
                Key=key,
                Body=staged,
                ContentLength=size_bytes,
                ContentType=content_type,
            )
            uploaded = True
        return original_filename, key, content_type, size_bytes
    except _S3_ERRORS as exc:
        # A timed-out PutObject may have succeeded server-side. Attempt cleanup
        # for that uncertain outcome; a logged orphan may still need repair.
        if key is not None and not uploaded:
            delete_s3_file(key)
        logger.warning("attachment_s3_upload_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Attachment storage temporarily unavailable") from exc
    finally:
        upload.file.close()


def get_s3_object(storage_key: str):
    """Open an S3 object after the caller has checked ticket authorization."""
    try:
        return _client().get_object(Bucket=settings.s3_bucket_name, Key=_validated_key(storage_key))["Body"]
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"NoSuchKey", "404", "NotFound"}:
            raise HTTPException(status_code=404, detail="Attachment file not found") from None
        logger.warning("attachment_s3_read_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Attachment storage temporarily unavailable") from exc
    except ValueError:
        raise HTTPException(status_code=404, detail="Attachment file not found") from None
    except (BotoCoreError, OSError) as exc:
        logger.warning("attachment_s3_read_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Attachment storage temporarily unavailable") from exc


def delete_s3_file(storage_key: str) -> bool:
    """Best-effort idempotent removal; never log SDK exception text or credentials."""
    try:
        _client().delete_object(Bucket=settings.s3_bucket_name, Key=_validated_key(storage_key))
        return True
    except _S3_ERRORS + (ValueError,) as exc:
        logger.warning("attachment_s3_cleanup_failed error_type=%s", type(exc).__name__)
        return False
