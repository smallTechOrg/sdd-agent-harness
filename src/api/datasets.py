import io
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session
from db.models import DatasetRow
from domain.dataset import DatasetResponse

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"


@router.post("/datasets")
async def upload_dataset(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise api_error("INVALID_FILE_TYPE", f"Only .csv, .xlsx, .xls accepted; got {suffix!r}", 422)

    # Read file content
    content = await file.read()

    # Parse with pandas
    try:
        if suffix == ".csv":
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise api_error("PARSE_ERROR", f"Could not parse file: {e}", 422)

    # Generate ID upfront so we can name the file before inserting
    dataset_id = str(uuid4())

    # Save file to disk
    dest = UPLOAD_DIR / f"{dataset_id}_{filename}"
    dest.write_bytes(content)

    # Extract schema + sample
    columns = [{"name": col, "dtype": str(df[col].dtype)} for col in df.columns]
    sample_rows = df.head(20).to_dict(orient="records")

    # Create dataset record with all required fields
    dataset = DatasetRow(
        id=dataset_id,
        filename=filename,
        file_path=str(dest),
        columns_json=json.dumps(columns),
        sample_rows_json=json.dumps(sample_rows, default=str),
        row_count=len(df),
    )
    session.add(dataset)

    return ok(DatasetResponse(
        dataset_id=dataset_id,
        filename=filename,
        columns=[c["name"] for c in columns],
        row_count=len(df),
    ).model_dump())


@router.get("/datasets")
def list_datasets(session: Session = Depends(get_session)) -> dict:
    datasets = session.execute(
        select(DatasetRow).order_by(DatasetRow.created_at.desc())
    ).scalars().all()
    return ok([
        DatasetResponse(
            dataset_id=d.id,
            filename=d.filename,
            columns=[c["name"] for c in json.loads(d.columns_json)] if d.columns_json else [],
            row_count=d.row_count,
        ).model_dump()
        for d in datasets
    ])
