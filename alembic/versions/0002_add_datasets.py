"""add datasets table and analysis columns to runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("columns_json", sa.Text(), nullable=False),
        sa.Column("sample_rows_json", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("runs") as batch_op:
        batch_op.add_column(sa.Column("dataset_id", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("question", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("chart_type", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("labels_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("values_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_table("datasets")
    with op.batch_alter_table("runs") as batch_op:
        for col in ["dataset_id", "question", "chart_type", "labels_json", "values_json", "summary"]:
            batch_op.drop_column(col)
