from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import NotificationStatus
from app.domain.models import NotificationEvent
from app.domain.schemas import NotificationDTO


class NotificationRepository:
    async def was_recently_sent(
        self,
        session: AsyncSession,
        *,
        subscription_id: str,
        dedupe_key: str,
        sent_after: datetime,
    ) -> bool:
        result = await session.execute(
            select(NotificationEvent.id)
            .where(
                NotificationEvent.subscription_id == subscription_id,
                NotificationEvent.dedupe_key == dedupe_key,
                NotificationEvent.status == NotificationStatus.SENT,
                NotificationEvent.sent_at.is_not(None),
                NotificationEvent.sent_at >= sent_after,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_last_sent_for_offer(
        self,
        session: AsyncSession,
        *,
        subscription_id: str,
        offer_id: int,
    ) -> NotificationEvent | None:
        result = await session.execute(
            select(NotificationEvent)
            .where(
                NotificationEvent.subscription_id == subscription_id,
                NotificationEvent.offer_id == offer_id,
                NotificationEvent.status == NotificationStatus.SENT,
            )
            .order_by(desc(NotificationEvent.sent_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, session: AsyncSession, dto: NotificationDTO) -> NotificationEvent:
        event = NotificationEvent(
            subscription_id=dto.subscription_id,
            offer_id=dto.offer_id,
            reason=dto.reason,
            status=dto.status,
            dedupe_key=dto.dedupe_key,
            price_amount=dto.price_amount,
            currency=dto.currency,
            chat_id=dto.chat_id,
            message_text=dto.message_text,
        )
        session.add(event)
        await session.flush()
        return event

    async def get_by_id(self, session: AsyncSession, notification_id: int) -> NotificationEvent | None:
        result = await session.execute(select(NotificationEvent).where(NotificationEvent.id == notification_id))
        return result.scalar_one_or_none()

    async def list_pending(self, session: AsyncSession, limit: int = 20) -> list[NotificationEvent]:
        result = await session.execute(
            select(NotificationEvent)
            .where(NotificationEvent.status.in_([NotificationStatus.PENDING, NotificationStatus.FAILED]))
            .order_by(NotificationEvent.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_recent(self, session: AsyncSession, limit: int = 50) -> list[NotificationEvent]:
        result = await session.execute(
            select(NotificationEvent).order_by(NotificationEvent.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def delete_created_before(self, session: AsyncSession, *, older_than: datetime) -> int:
        result = await session.execute(delete(NotificationEvent).where(NotificationEvent.created_at < older_than))
        return result.rowcount or 0
