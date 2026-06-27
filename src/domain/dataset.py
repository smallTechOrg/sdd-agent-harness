from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    dtype: str


class DatasetResponse(BaseModel):
    dataset_id: str
    filename: str
    columns: list[str]
    row_count: int
