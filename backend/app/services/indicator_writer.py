"""Persist IndicatorObservations to the indicators table.

Mirrors `app/services/price_writer.py:persist_prices` choices — bulk
INSERT...ON CONFLICT DO NOTHING in chunks, one round trip per chunk. The
unique constraint `uq_indicators_key_observed` is the dedup safety net.
"""

from decimal import Decimal

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Indicator
from app.schemas.indicator import IndicatorObservation

logger = structlog.get_logger(__name__)

# Same cap as price_writer — keeps query plan logging readable on large batches.
_MAX_BATCH = 1000


async def persist_indicators(db: AsyncSession, observations: list[IndicatorObservation]) -> int:
    """Bulk insert observations; rows violating uq_indicators_key_observed are skipped."""
    if not observations:
        return 0

    log = logger.bind(count=len(observations))
    log.info("indicator_writer.persist.started")

    inserted_total = 0
    for chunk_start in range(0, len(observations), _MAX_BATCH):
        chunk = observations[chunk_start : chunk_start + _MAX_BATCH]
        rows = [
            {
                "indicator_key": o.indicator_key,
                "observed_at": o.observed_at,
                # Decimal preserves the source precision; float coerces back fine on read.
                "value": Decimal(str(o.value)),
                "source": o.source,
                "payload": o.payload,
            }
            for o in chunk
        ]
        stmt = (
            pg_insert(Indicator)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_indicators_key_observed")
        )
        result = await db.execute(stmt)
        inserted_total += getattr(result, "rowcount", 0) or 0

    await db.commit()
    log.info("indicator_writer.persist.completed", inserted=inserted_total)
    return inserted_total
