from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Dataset(BaseModel):
    """API/serialization view of a ``datasets`` row.

    ``profile`` is the parsed profile (the row stores it as a JSON string in
    ``profile_json``); callers parse/serialize at the boundary.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    original_filename: str
    file_path: str
    profile: dict[str, Any] = Field(default_factory=dict)
    source_kind: str = "csv"
    created_at: datetime
    updated_at: datetime
