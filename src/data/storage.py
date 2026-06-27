"""Local file storage for uploaded datasets.

Raw uploaded bytes are written to ./data/uploads/<dataset_id>.<ext> and live
there ONLY. Nothing in this module logs, returns, or otherwise exposes row
contents — it deals in bytes and paths only.
"""
from __future__ import annotations

import os
from uuid import uuid4

# Supported upload extensions → canonical file_type label.
_EXT_TO_TYPE = {
    "csv": "csv",
    "xlsx": "xlsx",
}

# Upload root, relative to the process working directory (repo root). Gitignored.
UPLOAD_DIR = os.path.join("data", "uploads")


def _ensure_upload_dir() -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    return UPLOAD_DIR


def _normalize_ext(original_filename: str) -> str:
    ext = os.path.splitext(original_filename)[1].lower().lstrip(".")
    if ext not in _EXT_TO_TYPE:
        raise ValueError(
            f"Unsupported file type {ext or '(none)'!r}; expected csv or xlsx"
        )
    return ext


def save_upload(file_bytes: bytes, original_filename: str) -> tuple[str, str, str]:
    """Persist raw upload bytes to local disk.

    Returns (dataset_id, stored_path, file_type). The dataset_id is a fresh uuid;
    the stored file is ./data/uploads/<dataset_id>.<ext>. file_type ∈ {csv, xlsx}.

    Raises ValueError on an unsupported extension or empty payload.
    """
    if not file_bytes:
        raise ValueError("Empty upload — no bytes received")

    ext = _normalize_ext(original_filename)
    file_type = _EXT_TO_TYPE[ext]
    dataset_id = str(uuid4())

    _ensure_upload_dir()
    stored_path = os.path.join(UPLOAD_DIR, f"{dataset_id}.{ext}")
    with open(stored_path, "wb") as fh:
        fh.write(file_bytes)

    return dataset_id, stored_path, file_type


def resolve_path(dataset_id: str, file_type: str) -> str:
    """Resolve the stored path for a dataset given its id + file_type.

    Returns the expected ./data/uploads/<dataset_id>.<ext> path. Raises ValueError
    if the file is missing on disk (e.g. it was manually deleted).
    """
    ext = _EXT_TO_TYPE.get(file_type)
    if ext is None:
        raise ValueError(f"Unknown file_type {file_type!r}; expected csv or xlsx")
    path = os.path.join(UPLOAD_DIR, f"{dataset_id}.{ext}")
    if not os.path.isfile(path):
        raise ValueError(f"Stored file missing for dataset {dataset_id}")
    return path
