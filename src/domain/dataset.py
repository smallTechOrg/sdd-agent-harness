from pydantic import BaseModel


class ColumnProfile(BaseModel):
    """Per-column entry in the bounded schema summary sent to the LLM."""

    name: str
    dtype: str
    stats: dict[str, str]


class SchemaSummary(BaseModel):
    """The bounded schema + sample + per-column stats.

    This is the ONLY view of the data that may leave the machine (sent to the
    LLM). It is capped: a small number of sample rows plus per-column summary
    stats — never the full dataset.
    """

    columns: list[ColumnProfile]
    sample_rows: list[dict[str, str]]
    sample_row_count: int


class DatasetProfile(BaseModel):
    """Result of parsing + profiling an uploaded file (internal DTO).

    Consumed by the API layer to persist a `datasets` row and by the analysis
    graph to know the schema.
    """

    row_count: int
    column_count: int
    columns: list[str]
    schema_summary: SchemaSummary


class DatasetResponse(BaseModel):
    """The `data` payload returned by POST /datasets (per spec/api.md)."""

    dataset_id: str
    filename: str
    file_format: str
    row_count: int
    column_count: int
    columns: list[str]
    status: str
