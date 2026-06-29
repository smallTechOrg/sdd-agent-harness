"""datasets table + analysis columns on runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-29 00:00:00.000000

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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("duckdb_path", sa.Text(), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # SQLite cannot ALTER ... ADD COLUMN with some clauses; use batch mode.
    with op.batch_alter_table("runs") as batch_op:
        batch_op.add_column(sa.Column("dataset_id", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("question", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("sql", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("result_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("tokens_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch_op:
        batch_op.drop_column("tokens_json")
        batch_op.drop_column("result_json")
        batch_op.drop_column("sql")
        batch_op.drop_column("question")
        batch_op.drop_column("dataset_id")

    op.drop_table("datasets")
