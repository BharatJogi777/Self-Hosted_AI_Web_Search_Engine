"""Create durable crawl job queue."""
from alembic import op
import sqlalchemy as sa

revision = "0004_crawl_jobs"
down_revision = "0003_weighted_fts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.String(200), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result_page_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crawl_jobs_status", "crawl_jobs", ["status"])
    op.create_index("ix_crawl_jobs_available_at", "crawl_jobs", ["available_at"])
    op.create_index("ix_crawl_jobs_locked_until", "crawl_jobs", ["locked_until"])
    op.create_index(
        "uq_crawl_jobs_active_url",
        "crawl_jobs",
        ["url"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_crawl_jobs_active_url", table_name="crawl_jobs")
    op.drop_index("ix_crawl_jobs_locked_until", table_name="crawl_jobs")
    op.drop_index("ix_crawl_jobs_available_at", table_name="crawl_jobs")
    op.drop_index("ix_crawl_jobs_status", table_name="crawl_jobs")
    op.drop_table("crawl_jobs")
