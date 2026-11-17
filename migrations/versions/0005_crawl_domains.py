"""Add shared domain leases and persistent robots cache."""
from alembic import op
import sqlalchemy as sa

revision = "0005_crawl_domains"
down_revision = "0004_crawl_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_domains",
        sa.Column("domain", sa.String(255), primary_key=True),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(200), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("robots_text", sa.Text(), nullable=True),
        sa.Column("robots_status", sa.Integer(), nullable=True),
        sa.Column("robots_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("robots_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crawl_domains_next_allowed_at", "crawl_domains", ["next_allowed_at"])


def downgrade() -> None:
    op.drop_index("ix_crawl_domains_next_allowed_at", table_name="crawl_domains")
    op.drop_table("crawl_domains")
