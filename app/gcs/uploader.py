from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional

from app.logging_utils import AuditLogger, NullAuditLogger


def upload_files(
    *,
    file_paths: Iterable[Path],
    bucket_name: str,
    prefix: str,
    credentials_path: str,
    logger: AuditLogger | NullAuditLogger | None = None,
) -> Dict[str, str]:
    active_logger = logger or NullAuditLogger()
    try:
        from google.cloud import storage  # type: ignore
    except Exception as exc:
        active_logger.exception("GCS client import failed.", exc)
        return {}

    if not credentials_path:
        active_logger.warning("GCS credentials path not provided; skipping upload.")
        return {}

    if not bucket_name:
        active_logger.warning("GCS bucket name not provided; skipping upload.")
        return {}

    cred_path = Path(credentials_path)
    if not cred_path.exists():
        active_logger.warning("GCS credentials file missing; skipping upload.", credentials_path=str(cred_path))
        return {}

    try:
        client = storage.Client.from_service_account_json(str(cred_path))
        bucket = client.bucket(bucket_name)
    except Exception as exc:
        active_logger.exception("Failed to initialize GCS client.", exc)
        return {}

    uploaded: Dict[str, str] = {}
    clean_prefix = prefix.strip("/").strip()
    for path in file_paths:
        if not path.exists():
            active_logger.warning("GCS upload skipped; file not found.", file=str(path))
            continue
        object_name = f"{clean_prefix}/{path.name}" if clean_prefix else path.name
        try:
            blob = bucket.blob(object_name)
            blob.upload_from_filename(str(path))
            uploaded[str(path)] = object_name
            active_logger.info("GCS upload complete.", file=str(path), object_name=object_name)
        except Exception as exc:
            active_logger.exception("GCS upload failed.", exc, file=str(path), object_name=object_name)

    return uploaded
