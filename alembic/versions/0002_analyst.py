"""analyst columns

Adds the analyst-capability columns to the ``runs`` table: question,
generated_code, result_table (JSON text), answer, explanation. All nullable so
the migration applies cleanly under SQLite's ALTER ADD COLUMN constraints.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("question", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("generated_code", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("result_table", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("answer", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("explanation", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "explanation")
    op.drop_column("runs", "answer")
    op.drop_column("runs", "result_table")
    op.drop_column("runs", "generated_code")
    op.drop_column("runs", "question")
