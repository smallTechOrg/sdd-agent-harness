"""data_analysis

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to runs table
    op.add_column("runs", sa.Column("session_id", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("question", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("sql_query", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("insight_json", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("chart_specs", sa.Text(), nullable=True))

    # Create sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create uploaded_files table
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_names", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
    )

    # Create analysis_cache table
    op.create_table(
        "analysis_cache",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("question_hash", sa.Text(), nullable=False),
        sa.Column("table_hash", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_hash", "table_hash"),
    )


def downgrade() -> None:
    op.drop_table("analysis_cache")
    op.drop_table("uploaded_files")
    op.drop_table("sessions")

    op.drop_column("runs", "chart_specs")
    op.drop_column("runs", "insight_json")
    op.drop_column("runs", "sql_query")
    op.drop_column("runs", "question")
    op.drop_column("runs", "session_id")
