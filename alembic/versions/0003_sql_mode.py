"""add sql mode support

Adds the ``mode`` column to the ``runs`` table to track whether the analysis
was performed in pandas or SQL mode (Phase 2+). Defaults to "pandas" for
backward compatibility.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("mode", sa.Text(), nullable=True, server_default="pandas"))


def downgrade() -> None:
    op.drop_column("runs", "mode")
