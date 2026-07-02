"""add aws connect fields to accounts, slack/onboarding fields to users

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('user_id', sa.Integer(), nullable=True))
    op.add_column('accounts', sa.Column('is_connected', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('accounts', sa.Column('aws_access_key_id', sa.String(length=255), nullable=True))
    op.add_column('accounts', sa.Column('aws_secret_access_key_encrypted', sa.String(length=512), nullable=True))
    op.add_column('accounts', sa.Column('aws_region', sa.String(length=50), nullable=True))
    op.create_foreign_key('fk_accounts_user_id', 'accounts', 'users', ['user_id'], ['id'])

    op.add_column('users', sa.Column('slack_webhook_url', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('users', 'onboarding_completed')
    op.drop_column('users', 'slack_webhook_url')

    op.drop_constraint('fk_accounts_user_id', 'accounts', type_='foreignkey')
    op.drop_column('accounts', 'aws_region')
    op.drop_column('accounts', 'aws_secret_access_key_encrypted')
    op.drop_column('accounts', 'aws_access_key_id')
    op.drop_column('accounts', 'is_connected')
    op.drop_column('accounts', 'user_id')
