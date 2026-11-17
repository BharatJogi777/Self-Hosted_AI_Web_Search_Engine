"""Add bounded crawl runs and job lineage."""
from alembic import op
import sqlalchemy as sa

revision = "0006_crawl_runs"
down_revision = "0005_crawl_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seed_url", sa.String(2048), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crawl_runs_status", "crawl_runs", ["status"])
    op.add_column("crawl_jobs", sa.Column("run_id", sa.Uuid(), nullable=True))
    op.add_column("crawl_jobs", sa.Column("depth", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_jobs", sa.Column("parent_url", sa.String(2048), nullable=True))
    op.create_foreign_key("fk_crawl_jobs_run_id", "crawl_jobs", "crawl_runs", ["run_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_crawl_jobs_run_url", "crawl_jobs", ["run_id", "url"])
    op.create_index("ix_crawl_jobs_run_id", "crawl_jobs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_crawl_jobs_run_id", table_name="crawl_jobs")
    op.drop_constraint("uq_crawl_jobs_run_url", "crawl_jobs", type_="unique")
    op.drop_constraint("fk_crawl_jobs_run_id", "crawl_jobs", type_="foreignkey")
    op.drop_column("crawl_jobs", "parent_url")
    op.drop_column("crawl_jobs", "depth")
    op.drop_column("crawl_jobs", "run_id")
    op.drop_index("ix_crawl_runs_status", table_name="crawl_runs")
    op.drop_table("crawl_runs")
