"""Pydantic response models for the dataset endpoints.

Mirrors the `data` shape in spec/api.md for `POST /datasets` and
`GET /datasets/{dataset_id}` exactly. Carries only schema + metadata —
never raw rows.
"""
from pydantic import BaseModel, ConfigDict, Field


class ColumnSchema(BaseModel):
    name: str
    dtype: str  # "string" | "number" | "date"


class DatasetSchema(BaseModel):
    columns: list[ColumnSchema]


class DatasetResponse(BaseModel):
    # `schema` clashes with BaseModel internals, so store as `schema_` and emit
    # the wire field "schema" via alias + by_alias serialization.
    model_config = ConfigDict(populate_by_name=True)

    dataset_id: str
    filename: str
    file_type: str  # "csv" | "xlsx"
    row_count: int
    schema_: DatasetSchema = Field(alias="schema")

    def to_wire(self) -> dict:
        """Serialize to the exact spec/api.md `data` shape (field name `schema`)."""
        return self.model_dump(by_alias=True)
