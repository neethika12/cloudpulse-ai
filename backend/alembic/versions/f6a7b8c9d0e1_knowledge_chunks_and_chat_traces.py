"""replace cost_embeddings with knowledge_chunks (hybrid RAG) and add chat_traces

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The old summary-embedding RAG table is no longer used.
    op.drop_table('cost_embeddings')

    op.create_table(
        'knowledge_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=200), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('section', sa.String(length=300), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('content_hash'),
    )
    op.create_index('ix_knowledge_chunks_source', 'knowledge_chunks', ['source'])
    # Approximate nearest-neighbour index for cosine distance (vector retriever).
    op.execute(
        'CREATE INDEX ix_knowledge_chunks_embedding ON knowledge_chunks '
        'USING hnsw (embedding vector_cosine_ops)'
    )
    # Full-text index for the keyword retriever. The query must use the same expression.
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_fts ON knowledge_chunks "
        "USING gin (to_tsvector('english', content))"
    )

    op.create_table(
        'chat_traces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('citations', sa.JSON(), nullable=False),
        sa.Column('llm_calls', sa.Integer(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False),
        sa.Column('completion_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chat_traces_user_id', 'chat_traces', ['user_id'])
    op.create_index('ix_chat_traces_created_at', 'chat_traces', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_chat_traces_created_at', table_name='chat_traces')
    op.drop_index('ix_chat_traces_user_id', table_name='chat_traces')
    op.drop_table('chat_traces')
    op.drop_index('ix_knowledge_chunks_fts', table_name='knowledge_chunks')
    op.drop_index('ix_knowledge_chunks_embedding', table_name='knowledge_chunks')
    op.drop_index('ix_knowledge_chunks_source', table_name='knowledge_chunks')
    op.drop_table('knowledge_chunks')

    op.create_table(
        'cost_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('embedding', Vector(384), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
