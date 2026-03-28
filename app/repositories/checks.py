from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CheckStatus, CheckTrigger
from app.domain.models import SubscriptionCheck


class CheckRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        subscription_id: str,
        trigger_type: CheckTrigger,
        status: CheckStatus = CheckStatus.RUNNING,
    ) -> SubscriptionCheck:
        check = SubscriptionCheck(
            subscription_id=subscription_id,
            trigger_type=trigger_type,
            status=status,
        )
        session.add(check)
        await session.flush()
        return check

    async def list_recent(self, session: AsyncSession, limit: int = 20) -> list[SubscriptionCheck]:
        result = await session.execute(select(SubscriptionCheck).order_by(desc(SubscriptionCheck.started_at)).limit(limit))
        return list(result.scalars().all())

    async def get_by_id(self, session: AsyncSession, check_id: int) -> SubscriptionCheck | None:
        result = await session.execute(select(SubscriptionCheck).where(SubscriptionCheck.id == check_id))
        return result.scalar_one_or_none()

    async def get_last_successful(self, session: AsyncSession) -> SubscriptionCheck | None:
        result = await session.execute(
            select(SubscriptionCheck)
            .where(SubscriptionCheck.status == CheckStatus.SUCCESS)
            .order_by(desc(SubscriptionCheck.finished_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete_finished_before(self, session: AsyncSession, *, older_than: datetime) -> int:
        result = await session.execute(
            delete(SubscriptionCheck).where(
                SubscriptionCheck.finished_at.is_not(None),
                SubscriptionCheck.finished_at < older_than,
            )
        )
        return result.rowcount or 0
