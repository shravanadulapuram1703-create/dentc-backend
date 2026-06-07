"""Local-filesystem upload helper (patient documents, claim attachments).

Writes under ``settings.UPLOAD_DIR/<subdir>`` and returns ``(relative_path, url)``.
Swap the body for object storage (S3/GCS) in production — the contract is stable.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings


def save_file(subdir: str, original_name: str, data: bytes) -> tuple[str, str]:
    directory = Path(settings.UPLOAD_DIR) / subdir
    directory.mkdir(parents=True, exist_ok=True)
    ext = Path(original_name or "").suffix
    stored = f"{uuid.uuid4().hex}{ext}"
    (directory / stored).write_bytes(data)
    rel = f"{subdir}/{stored}"
    return rel, f"{settings.UPLOAD_URL_BASE}/{rel}"


def delete_file(rel_path: str | None) -> None:
    if not rel_path:
        return
    try:
        (Path(settings.UPLOAD_DIR) / rel_path).unlink(missing_ok=True)
    except OSError:
        pass
