"""Add generated tsvector and GIN index for page versions."""
from alembic import op

revision = "0002_full_text"
down_revision = "0001_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE page_versions ADD COLUMN search_vector TSVECTOR "
        "GENERATED ALWAYS AS (to_tsvector('english', coalesce(extracted_text, ''))) STORED"
    )
    op.execute(
        "CREATE INDEX ix_page_versions_search_vector "
        "ON page_versions USING GIN (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_page_versions_search_vector")
    op.execute("ALTER TABLE page_versions DROP COLUMN IF EXISTS search_vector")
