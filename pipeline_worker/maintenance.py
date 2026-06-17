from __future__ import annotations

from sqlalchemy import text

from app.database import async_session


async def deactivate_expired_listings() -> dict[str, int]:
    statement = text(
        """
        UPDATE listings
           SET is_active = false,
               updated_at = NOW()
         WHERE is_active = true
           AND expiry_date IS NOT NULL
           AND expiry_date <> ''
           AND (
                CASE WHEN expiry_date ~ '^\\d{2}/\\d{2}/\\d{4}$'
                     THEN to_date(expiry_date, 'DD/MM/YYYY') < CURRENT_DATE
                     WHEN expiry_date ~ '^\\d{4}-\\d{2}-\\d{2}$'
                     THEN to_date(expiry_date, 'YYYY-MM-DD') < CURRENT_DATE
                     ELSE false
                END
           )
        """
    )
    async with async_session() as session:
        result = await session.execute(statement)
        await session.commit()
    return {"deactivated": result.rowcount or 0}


async def cleanup_expired_listing_chunks(retention_days: int) -> dict[str, int]:
    statement = text(
        """
        DELETE FROM chunks c
         USING listings l
         WHERE c.parent_type = 'listing'
           AND c.parent_id = l.id
           AND l.is_active = false
           AND COALESCE(l.updated_at, l.created_at) < NOW() - (:retention_days * INTERVAL '1 day')
        """
    )
    async with async_session() as session:
        result = await session.execute(statement, {"retention_days": retention_days})
        await session.commit()
    return {"deleted_chunks": result.rowcount or 0}
