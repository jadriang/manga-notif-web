"""clerk auth migration

Revision ID: 56fb52de0032
Revises: c192f2cc1ef6
Create Date: 2026-06-06 14:27:55.511776

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56fb52de0032'
down_revision: Union[str, None] = 'c192f2cc1ef6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. invite_codes
    op.create_table(
        'invite_codes',
        sa.Column('code', sa.String(length=64), primary_key=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('max_uses', sa.Integer(), nullable=False),
        sa.Column('used_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('used_count <= max_uses', name='used_count_le_max'),
    )

    # 2. Truncate users (cascades to subscriptions). Keep manga + chapter_state.
    op.execute('TRUNCATE TABLE users CASCADE')

    # 3. users.clerk_id
    op.add_column('users', sa.Column('clerk_id', sa.String(length=64), nullable=False))
    op.create_unique_constraint('uq_users_clerk_id', 'users', ['clerk_id'])

    # 4. Drop allowed_emails
    op.drop_table('allowed_emails')


def downgrade() -> None:
    op.create_table(
        'allowed_emails',
        sa.Column('email', sa.String(length=320), primary_key=True),
    )
    op.drop_constraint('uq_users_clerk_id', 'users', type_='unique')
    op.drop_column('users', 'clerk_id')
    op.drop_table('invite_codes')
