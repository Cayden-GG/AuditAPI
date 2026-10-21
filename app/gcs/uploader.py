"""
GCS uploader
Uploads audit reports to and downloads them from the Google Cloud Storage bucket
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable 

from app.logging_utils import AuditLogger 


def upload_files(
    *,
    file_paths: Iterable[Path],
    bucket_name: str,
    prefix: str,
    credentials_path: str,
    logger: AuditLogger,
) -> Dict[str, str]:
    """
    Uploads files to the GCS bucket under a prefix. Skips the upload and returns an empty dict
    if the GCS client, credentials or bucket are unavailable, failures are logged not raised.

    @Args:
        file_paths (Iterable[Path]) -- local files to upload
        bucket_name (str) -- GCS bucket name
        prefix (str) -- object name prefix the files are uploaded under
        credentials_path (str) -- path to the service account json
        logger (AuditLogger | None) -- logger for upload results

    @Returns:
        local file path to uploaded object name (Dict[str, str])
    """
    try:
        from google.cloud import storage  # type: ignore
    except Exception as exc:
        logger.exception("GCS client import failed.", exc)
        return {}

    if not credentials_path:
        logger.warning("GCS credentials path not provided; skipping upload.")
        return {}

    if not bucket_name:
        logger.warning("GCS bucket name not provided; skipping upload.")
        return {}

    cred_path = Path(credentials_path)
    if not cred_path.exists():
        logger.warning("GCS credentials file missing; skipping upload.", credentials_path=str(cred_path))
        return {}

    try:
        client = storage.Client.from_service_account_json(str(cred_path))
        bucket = client.bucket(bucket_name)
    except Exception as exc:
        logger.exception("Failed to initialize GCS client.", exc)
        return {}

    uploaded: Dict[str, str] = {}
    clean_prefix = prefix.strip("/").strip()
    for path in file_paths:
        if not path.exists():
            logger.warning("GCS upload skipped; file not found.", file=str(path))
            continue
        object_name = f"{clean_prefix}/{path.name}" if clean_prefix else path.name
        try:
            blob = bucket.blob(object_name)
            blob.upload_from_filename(str(path))
            uploaded[str(path)] = object_name
            logger.info("GCS upload complete.", file=str(path), object_name=object_name)
        except Exception as exc:
            logger.exception("GCS upload failed.", exc, file=str(path), object_name=object_name)

    return uploaded


def download_objects(
    *,
    object_names: Iterable[str],
    bucket_name: str,
    credentials_path: str,
    output_dir: Path,
    logger: AuditLogger,
) -> Dict[str, str]:
    """
    Downloads objects from the GCS bucket into a local directory. Skips the download and returns an empty dict
    if the GCS client, credentials or bucket are unavailable, failures are logged not raised.

    @Args:
        object_names (Iterable[str]) -- GCS object names to download
        bucket_name (str) -- GCS bucket name
        credentials_path (str) -- path to the service account json
        output_dir (Path) -- local directory the files are saved to
        logger (AuditLogger | None) -- logger for download results

    @Returns:
        object name to downloaded local file path (Dict[str, str])
    """
    try:
        from google.cloud import storage  # type: ignore
    except Exception as exc:
        logger.exception("GCS client import failed.", exc)
        return {}

    if not credentials_path:
        logger.warning("GCS credentials path not provided; skipping download.")
        return {}

    if not bucket_name:
        logger.warning("GCS bucket name not provided; skipping download.")
        return {}

    cred_path = Path(credentials_path)
    if not cred_path.exists():
        logger.warning("GCS credentials file missing; skipping download.", credentials_path=str(cred_path))
        return {}

    try:
        client = storage.Client.from_service_account_json(str(cred_path))
        bucket = client.bucket(bucket_name)
    except Exception as exc:
        logger.exception("Failed to initialize GCS client.", exc)
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: Dict[str, str] = {}
    for object_name in object_names:
        if not object_name:
            continue
        try:
            blob = bucket.blob(object_name)
            local_path = output_dir / Path(object_name).name
            blob.download_to_filename(str(local_path))
            downloaded[object_name] = str(local_path)
            logger.info("GCS download complete.", object_name=object_name, file=str(local_path))
        except Exception as exc:
            logger.exception("GCS download failed.", exc, object_name=object_name)

    return downloaded
