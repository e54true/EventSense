"""add events.llm_summary column

Revision ID: 79df7bf433be
Revises: c37f9609d269
Create Date: 2026-06-09 18:30:00.000000

Stores the v2/v3 analyzer's `EventAnalysis.summary` — the thesis paragraph
the prompt asks for. Previously the LLM produced it (instructor-validated)
but the analyzer dropped it on the floor. Adding the column + persistence
fixes the gap; nullable so historical pre-fix rows stay readable.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "79df7bf433be"
down_revision: str | Sequence[str] | None = "c37f9609d269"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("events", sa.Column("llm_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("events", "llm_summary")
