"""add anomalies table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'anomalies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('service', sa.String(length=80), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('amount_usd', sa.Float(), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_anomalies_date'), 'anomalies', ['date'], unique=False)
    op.create_index(op.f('ix_anomalies_service'), 'anomalies', ['service'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_anomalies_service'), table_name='anomalies')
    op.drop_index(op.f('ix_anomalies_date'), table_name='anomalies')
    op.drop_table('anomalies')
