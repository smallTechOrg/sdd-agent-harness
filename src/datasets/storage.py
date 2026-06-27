from pathlib import Path

from observability.events import get_logger

log = get_logger("datasets.storage")

UPLOAD_DIR = Path("data/uploads")


def save_file(dataset_id: str, extension: str, content: bytes) -> str:
    """Write uploaded bytes to data/uploads/<dataset_id>.<ext> and return the path.

    Purely local — the raw file is never transmitted anywhere.
    """
    ext = extension.lstrip(".").lower()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{dataset_id}.{ext}"
    path.write_bytes(content)
    log.info(
        "dataset.file_saved",
        dataset_id=dataset_id,
        local_path=str(path),
        bytes=len(content),
    )
    return str(path)


def load_file(local_path: str) -> bytes:
    """Read previously-stored bytes back from local disk."""
    path = Path(local_path)
    data = path.read_bytes()
    log.info("dataset.file_loaded", local_path=str(path), bytes=len(data))
    return data
