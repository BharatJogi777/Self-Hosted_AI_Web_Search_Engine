"""Create pages and page_versions tables."""
from alembic import op
import sqlalchemy as sa

revision = "0001_pages"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("normalized_url", sa.String(2048), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("title", sa.String(1000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("current_content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_url", name="uq_pages_normalized_url"),
    )
    op.create_index("ix_pages_domain", "pages", ["domain"])
    op.create_index("ix_pages_current_content_hash", "pages", ["current_content_hash"])
    op.create_table(
        "page_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("extractor", sa.String(100), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("page_id", "version_number", name="uq_page_version_number"),
        sa.UniqueConstraint("page_id", "content_hash", name="uq_page_version_content_hash"),
    )
    op.create_index("ix_page_versions_page_id", "page_versions", ["page_id"])
    op.create_index("ix_page_versions_content_hash", "page_versions", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_page_versions_content_hash", table_name="page_versions")
    op.drop_index("ix_page_versions_page_id", table_name="page_versions")
    op.drop_table("page_versions")
    op.drop_index("ix_pages_current_content_hash", table_name="pages")
    op.drop_index("ix_pages_domain", table_name="pages")
    op.drop_table("pages")
