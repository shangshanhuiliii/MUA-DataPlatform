"""add claim_limit_per_user to batches

Revision ID: c3d4e5f6a7b8
Revises: bbb4058d5529
Create Date: 2026-03-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'bbb4058d5529'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add batch-level claim limit and migrate legacy allocation quota data."""
    op.add_column('batches', sa.Column('claim_limit_per_user', sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE batches
        SET claim_limit_per_user = (
            SELECT MAX(batch_allocations.quota)
            FROM batch_allocations
            WHERE batch_allocations.batch_id = batches.id
        )
        WHERE claim_limit_per_user IS NULL
          AND EXISTS (
            SELECT 1
            FROM batch_allocations
            WHERE batch_allocations.batch_id = batches.id
          )
        """
    )
    op.execute("UPDATE batches SET claim_limit_per_user = 10 WHERE claim_limit_per_user IS NULL")
    with op.batch_alter_table('batches') as batch_op:
        batch_op.alter_column(
            'claim_limit_per_user',
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text('10'),
        )
    with op.batch_alter_table('batch_allocations') as batch_op:
        batch_op.drop_column('quota')


def downgrade() -> None:
    """Restore legacy allocation quota data and remove batch-level claim limit."""
    with op.batch_alter_table('batch_allocations') as batch_op:
        batch_op.add_column(sa.Column('quota', sa.Integer(), nullable=False, server_default='0'))
    op.execute(
        """
        UPDATE batch_allocations
        SET quota = COALESCE(
            (
                SELECT batches.claim_limit_per_user
                FROM batches
                WHERE batches.id = batch_allocations.batch_id
            ),
            0
        )
        """
    )
    with op.batch_alter_table('batches') as batch_op:
        batch_op.drop_column('claim_limit_per_user')
