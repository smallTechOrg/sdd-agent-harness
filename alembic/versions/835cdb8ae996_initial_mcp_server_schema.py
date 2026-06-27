"""initial database (MCP server instance) schema

Revision ID: 835cdb8ae996
Revises:
Create Date: 2026-06-26 02:01:01.827371

The primary entity is a **database** (an instance of an MCP server type). Its MCP capabilities
(mcp_tools / mcp_resources / mcp_prompts) are child rows keyed by ``database_id``. Partial-unique
indexes carry BOTH ``sqlite_where`` and ``postgresql_where`` (uniqueness over active rows) and are
created with ``op.create_index`` (not batch mode) so they apply on PostgreSQL as well as SQLite.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '835cdb8ae996'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = sa.text('deleted_at IS NULL')


def upgrade() -> None:
    op.create_table('agent_runs',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('query_record_id', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('mcp_prompts',
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('arguments_json', sa.Text(), nullable=True),
    sa.Column('template_json', sa.Text(), nullable=True),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('database_id', sa.Text(), nullable=False),
    sa.Column('created_version', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('deleted_version', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mcp_prompts_database_id', 'mcp_prompts', ['database_id'], unique=False)
    op.create_index('uq_mcp_prompts_active_name', 'mcp_prompts', ['database_id', 'name'], unique=True,
                    sqlite_where=_ACTIVE, postgresql_where=_ACTIVE)

    op.create_table('mcp_resources',
    sa.Column('uri', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('mime_type', sa.Text(), nullable=True),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('content_json', sa.Text(), nullable=True),
    sa.Column('size', sa.Integer(), nullable=True),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('database_id', sa.Text(), nullable=False),
    sa.Column('created_version', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('deleted_version', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mcp_resources_database_id', 'mcp_resources', ['database_id'], unique=False)
    op.create_index('uq_mcp_resources_active_uri', 'mcp_resources', ['uri'], unique=True,
                    sqlite_where=_ACTIVE, postgresql_where=_ACTIVE)

    op.create_table('databases',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('uri', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('last_synced_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('last_sync_status', sa.Text(), nullable=True),
    sa.Column('connection_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sa.UniqueConstraint('uri')
    )

    op.create_table('mcp_tools',
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('execution_json', sa.Text(), nullable=False),
    sa.Column('output_schema_json', sa.Text(), nullable=True),
    sa.Column('annotations_json', sa.Text(), nullable=True),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('database_id', sa.Text(), nullable=False),
    sa.Column('created_version', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('deleted_version', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mcp_tools_database_id', 'mcp_tools', ['database_id'], unique=False)
    op.create_index('uq_mcp_tools_active_name', 'mcp_tools', ['database_id', 'name'], unique=True,
                    sqlite_where=_ACTIVE, postgresql_where=_ACTIVE)

    op.create_table('query_records',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('session_id', sa.Text(), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('iteration_count', sa.Integer(), nullable=True),
    sa.Column('query_history_json', sa.Text(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('total_tokens', sa.Integer(), nullable=True),
    sa.Column('estimated_cost_usd', sa.Float(), nullable=True),
    sa.Column('api_request_count', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('session_databases',
    sa.Column('session_id', sa.Text(), nullable=False),
    sa.Column('database_id', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('session_id', 'database_id')
    )

    op.create_table('sessions',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('sessions')
    op.drop_table('session_databases')
    op.drop_table('query_records')
    op.drop_index('uq_mcp_tools_active_name', table_name='mcp_tools',
                  sqlite_where=_ACTIVE, postgresql_where=_ACTIVE)
    op.drop_index('ix_mcp_tools_database_id', table_name='mcp_tools')
    op.drop_table('mcp_tools')
    op.drop_table('databases')
    op.drop_index('uq_mcp_resources_active_uri', table_name='mcp_resources',
                  sqlite_where=_ACTIVE, postgresql_where=_ACTIVE)
    op.drop_index('ix_mcp_resources_database_id', table_name='mcp_resources')
    op.drop_table('mcp_resources')
    op.drop_index('uq_mcp_prompts_active_name', table_name='mcp_prompts',
                  sqlite_where=_ACTIVE, postgresql_where=_ACTIVE)
    op.drop_index('ix_mcp_prompts_database_id', table_name='mcp_prompts')
    op.drop_table('mcp_prompts')
    op.drop_table('agent_runs')
