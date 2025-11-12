"""remove search_index_name from folders

Revision ID: 20251111_215242
Revises:
Create Date: 2025-11-11 21:52:42

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251111_215242'
down_revision = None  # Update this if there are previous migrations
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Remove search_index_name column from folders table.

    This migration is part of the transition from per-folder Azure AI Search indexes
    to a single shared index with folder_id filtering (Integrated Vectorization approach).
    """
    # Drop the search_index_name column
    op.drop_column('folders', 'search_index_name')


def downgrade() -> None:
    """
    Restore search_index_name column to folders table.

    Note: This will restore the column structure but not the original index name values.
    """
    # Add back the search_index_name column
    op.add_column('folders',
        sa.Column('search_index_name', sa.String(), unique=True, nullable=True)
    )
