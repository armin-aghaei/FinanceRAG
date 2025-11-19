"""Add processing deduplication fields to documents

Revision ID: 20251118_add_dedup
Revises: 20251114_add_desc
Create Date: 2025-11-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20251118_add_dedup'
down_revision = '20251114_add_desc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add processing_started_at column
    op.add_column('documents', sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True))

    # Add processing_lock_id column
    op.add_column('documents', sa.Column('processing_lock_id', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove processing_lock_id column
    op.drop_column('documents', 'processing_lock_id')

    # Remove processing_started_at column
    op.drop_column('documents', 'processing_started_at')
