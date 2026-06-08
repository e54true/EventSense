"""add event_documents table

Revision ID: c37f9609d269
Revises: 22387af2be6f
Create Date: 2026-06-08 22:30:00.000000

Stores large per-event documents (SEC filing bodies, earnings call transcripts,
press-release text) outside the events.payload JSONB column. Keeps events
rows small and JSONB indexable while making documents fetchable lazily.

UNIQUE(event_id, doc_kind) — one document per (event, kind). If we want
multiple exhibits per filing, doc_kind discriminates (PRESS_RELEASE vs
EXHIBIT vs FILING_COVER).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c37f9609d269"
down_revision: str | Sequence[str] | None = "22387af2be6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "event_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column(
            "doc_kind",
            sa.Enum(
                "FILING_COVER",
                "PRESS_RELEASE",
                "EXHIBIT",
                "TRANSCRIPT",
                name="document_kind",
            ),
            nullable=False,
        ),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("raw_url", sa.String(length=500), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "doc_kind", name="uq_event_documents_event_kind"),
    )
    op.create_index(
        "ix_event_documents_event", "event_documents", ["event_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_event_documents_event", table_name="event_documents")
    op.drop_table("event_documents")
    sa.Enum(name="document_kind").drop(op.get_bind(), checkfirst=True)
