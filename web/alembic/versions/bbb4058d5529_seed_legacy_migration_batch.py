"""seed legacy migration batch

Revision ID: bbb4058d5529
Revises: 2b4cf6fc0424
Create Date: 2026-03-12 23:12:17.944015

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bbb4058d5529'
down_revision: Union[str, Sequence[str], None] = '2b4cf6fc0424'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_BATCH_NAME = "历史迁移批次"
LEGACY_BATCH_DESCRIPTION = "系统创建：用于承接批次功能上线前的历史无批次任务"
DEFAULT_ADMIN_USERNAME = "admin"


def _get_default_admin_id(conn) -> int:
    result = conn.execute(
        sa.text(
            """
            SELECT id
            FROM users
            WHERE username = :username
            ORDER BY id
            LIMIT 1
            """
        ),
        {"username": DEFAULT_ADMIN_USERNAME},
    ).fetchone()

    if not result:
        raise RuntimeError(
            f"Default admin user '{DEFAULT_ADMIN_USERNAME}' not found; "
            "cannot create legacy migration batch."
        )

    return result[0]


def _get_legacy_batch_id(conn):
    result = conn.execute(
        sa.text(
            """
            SELECT id
            FROM batches
            WHERE name = :name
            ORDER BY id
            LIMIT 1
            """
        ),
        {"name": LEGACY_BATCH_NAME},
    ).fetchone()

    return result[0] if result else None


def upgrade() -> None:
    """Create the legacy migration batch and backfill historical tasks."""
    conn = op.get_bind()

    batch_id = _get_legacy_batch_id(conn)
    if batch_id is None:
        admin_id = _get_default_admin_id(conn)
        now = datetime.utcnow()
        conn.execute(
            sa.text(
                """
                INSERT INTO batches (name, description, created_by, created_at, updated_at)
                VALUES (:name, :description, :created_by, :created_at, :updated_at)
                """
            ),
            {
                "name": LEGACY_BATCH_NAME,
                "description": LEGACY_BATCH_DESCRIPTION,
                "created_by": admin_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        batch_id = _get_legacy_batch_id(conn)
        if batch_id is None:
            raise RuntimeError("Failed to create legacy migration batch.")
        print(f"Created legacy migration batch '{LEGACY_BATCH_NAME}' (id={batch_id})")
    else:
        print(f"Reusing existing legacy migration batch '{LEGACY_BATCH_NAME}' (id={batch_id})")

    result = conn.execute(
        sa.text(
            """
            UPDATE tasks
            SET batch_id = :batch_id
            WHERE batch_id IS NULL
            """
        ),
        {"batch_id": batch_id},
    )
    print(f"Moved {result.rowcount or 0} historical tasks into '{LEGACY_BATCH_NAME}'")


def downgrade() -> None:
    """Best-effort rollback for the legacy migration batch data backfill."""
    conn = op.get_bind()
    batch_id = _get_legacy_batch_id(conn)

    if batch_id is None:
        print(f"Legacy migration batch '{LEGACY_BATCH_NAME}' not found, skipping rollback")
        return

    reset_result = conn.execute(
        sa.text(
            """
            UPDATE tasks
            SET batch_id = NULL
            WHERE batch_id = :batch_id
            """
        ),
        {"batch_id": batch_id},
    )

    conn.execute(
        sa.text(
            """
            DELETE FROM batch_allocations
            WHERE batch_id = :batch_id
            """
        ),
        {"batch_id": batch_id},
    )

    conn.execute(
        sa.text(
            """
            DELETE FROM batches
            WHERE id = :batch_id
            """
        ),
        {"batch_id": batch_id},
    )

    print(
        f"Rolled back legacy migration batch '{LEGACY_BATCH_NAME}' "
        f"and reset {reset_result.rowcount or 0} tasks to no batch"
    )
