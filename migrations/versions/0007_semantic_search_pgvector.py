"""Add chunk storage and pgvector embeddings for semantic retrieval."""
from alembic import op
import sqlalchemy as sa

revision = "0007_semantic_search"
down_revision = "0006_crawl_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The PostgreSQL server must have the pgvector extension files installed.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "page_chunks",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("page_version_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float()), nullable=True),
        sa.ForeignKeyConstraint(["page_version_id"], ["page_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "page_version_id", "chunk_index", "embedding_model",
            name="uq_page_chunk_version_index_model",
        ),
    )
    # Replace the generic ARRAY column with pgvector's fixed 768-dimensional type.
    op.execute("ALTER TABLE page_chunks ALTER COLUMN embedding TYPE vector(768) USING NULL::vector(768)")
    op.create_index("ix_page_chunks_version_id", "page_chunks", ["page_version_id"])
    op.execute("""
        CREATE INDEX ix_page_chunks_embedding_hnsw
        ON page_chunks USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_page_chunks_embedding_hnsw")
    op.drop_index("ix_page_chunks_version_id", table_name="page_chunks")
    op.drop_table("page_chunks")
    # Do not drop the shared vector extension; other tables may depend on it.
