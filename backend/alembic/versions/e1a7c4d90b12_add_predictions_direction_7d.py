"""add predictions.direction_7d column

Revision ID: e1a7c4d90b12
Revises: 79df7bf433be
Create Date: 2026-06-11 12:00:00.000000

v3 prompt asks the LLM for a separate 7-day direction call — the 24h impulse
and the week-out drift can legitimately differ (earnings pop that fades, FOMC
knee-jerk that reverses). Nullable: legacy v1/v2 predictions stay NULL and the
validator falls back to `direction` when scoring their 7d window.

Reuses the existing prediction_direction enum type (create_type=False).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1a7c4d90b12"
down_revision: str | Sequence[str] | None = "79df7bf433be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "predictions",
        sa.Column(
            "direction_7d",
            postgresql.ENUM(name="prediction_direction", create_type=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("predictions", "direction_7d")
