from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    type: str


class DatasetResponse(BaseModel):
    dataset_id: str
    name: str
    row_count: int
    columns: list[ColumnInfo]
