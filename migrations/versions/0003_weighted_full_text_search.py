"""Add weighted title and body fields to the full-text vector."""
from alembic import op
import sqlalchemy as sa

revision = "0003_weighted_fts"
down_revision = "0002_full_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "page_versions",
        sa.Column("title_snapshot", sa.Text(), nullable=False, server_default=""),
    )
    op.execute("""
        UPDATE page_versions AS pv
        SET title_snapshot = COALESCE(p.title, '')
        FROM pages AS p
        WHERE p.id = pv.page_id
    """)
    op.alter_column("page_versions", "title_snapshot", server_default=None)

    op.drop_index("ix_page_versions_search_vector", table_name="page_versions")
    op.drop_column("page_versions", "search_vector")
    op.execute("""
        ALTER TABLE page_versions
        ADD COLUMN search_vector TSVECTOR
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title_snapshot, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(extracted_text, '')), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_page_versions_search_vector
        ON page_versions USING GIN (search_vector)
    """)


def downgrade() -> None:
    op.drop_index("ix_page_versions_search_vector", table_name="page_versions")
    op.drop_column("page_versions", "search_vector")
    op.execute("""
        ALTER TABLE page_versions
        ADD COLUMN search_vector TSVECTOR
        GENERATED ALWAYS AS (
            to_tsvector('english', coalesce(extracted_text, ''))
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_page_versions_search_vector
        ON page_versions USING GIN (search_vector)
    """)
    op.drop_column("page_versions", "title_snapshot")
