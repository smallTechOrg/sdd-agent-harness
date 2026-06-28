from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_count: int
    sample_values: list[Any]


class FileProfile(BaseModel):
    columns: list[ColumnProfile]
    row_count: int
    column_count: int
    file_size_bytes: int
    profiled_at: str  # ISO datetime string


class UploadResponse(BaseModel):
    file_id: str
    original_filename: str
    profile: FileProfile


class FileListItem(BaseModel):
    file_id: str
    original_filename: str
    file_size_bytes: int
    row_count: int
    column_count: int
    created_at: datetime


class FileListResponse(BaseModel):
    files: list[FileListItem]


class SessionsStubResponse(BaseModel):
    sessions: list  # always empty list in Phase 1
