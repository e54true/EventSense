"""add prediction_kind enum + predictions.kind column + ECONOMIC_RELEASE backfill

Revision ID: 22387af2be6f
Revises: a50331f904f4
Create Date: 2026-06-08 21:05:00.000000

Adds:
- prediction_kind enum ('MARKET', 'COMPANY')
- predictions.kind column (NOT NULL, defaults existing rows to 'COMPANY' since
  every v1 prediction was per-ticker COMPANY-style)
- ix_predictions_kind_time index

Also runs a one-shot data migration to rename historical FRED CPI events from
event_type='ECONOMIC_RELEASE' to 'CPI_RELEASE'. The new multi-series FRED
adapter writes CPI_RELEASE / NFP_RELEASE / GDP_RELEASE, so this aligns
existing rows under the new taxonomy.

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "22387af2be6f"
down_revision: str | Sequence[str] | None = "a50331f904f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    prediction_kind = sa.Enum("MARKET", "COMPANY", name="prediction_kind")
    prediction_kind.create(op.get_bind(), checkfirst=True)
    # server_default='COMPANY' lets us add NOT NULL on a non-empty table; we drop
    # it immediately after so application code is the source of truth going forward.
    op.add_column(
        "predictions",
        sa.Column("kind", prediction_kind, nullable=False, server_default="COMPANY"),
    )
    op.alter_column("predictions", "kind", server_default=None)
    op.create_index(
        "ix_predictions_kind_time", "predictions", ["kind", "predicted_at"], unique=False
    )

    # Data migration: rename historical FRED events from the ambiguous
    # ECONOMIC_RELEASE to the explicit CPI_RELEASE. Only CPI was emitted under
    # the old single-series FRED adapter, so this is safe.
    op.execute(
        """
        UPDATE events
        SET event_type = 'CPI_RELEASE'
        WHERE source = 'FRED' AND event_type = 'ECONOMIC_RELEASE'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        UPDATE events
        SET event_type = 'ECONOMIC_RELEASE'
        WHERE source = 'FRED' AND event_type = 'CPI_RELEASE'
        """
    )
    op.drop_index("ix_predictions_kind_time", table_name="predictions")
    op.drop_column("predictions", "kind")
    sa.Enum(name="prediction_kind").drop(op.get_bind(), checkfirst=True)
