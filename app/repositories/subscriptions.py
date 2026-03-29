from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import Subscription
from app.domain.schemas import SubscriptionCreate


class SubscriptionRepository:
    async def create(self, session: AsyncSession, *, user_id: int, payload: SubscriptionCreate, next_check_at: datetime) -> Subscription:
        subscription = Subscription(
            user_id=user_id,
            name=payload.name,
            origin_iata=payload.origin_iata,
            destination_iata=payload.destination_iata,
            trip_type=payload.trip_type,
            departure_date_from=payload.departure_date_from,
            departure_date_to=payload.departure_date_to,
            return_date_from=payload.return_date_from,
            return_date_to=payload.return_date_to,
            min_trip_duration_days=payload.min_trip_duration_days,
            max_trip_duration_days=payload.max_trip_duration_days,
            max_price=payload.max_price,
            currency=payload.currency,
            market=payload.market,
            direct_only=payload.direct_only,
            baggage_policy=payload.baggage_policy,
            preferred_airlines=payload.preferred_airlines,
            check_interval_minutes=payload.check_interval_minutes,
            next_check_at=next_check_at,
        )
        session.add(subscription)
        await session.flush()
        return subscription

    async def get_by_id(self, session: AsyncSession, subscription_id: str) -> Subscription | None:
        result = await session.execute(
            select(Subscription).options(selectinload(Subscription.user)).where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, session: AsyncSession, subscription_id: str, user_id: int) -> Subscription | None:
        result = await session.execute(
            select(Subscription)
            .options(selectinload(Subscription.user))
            .where(Subscription.id == subscription_id, Subscription.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, session: AsyncSession, user_id: int) -> list[Subscription]:
        result = await session.execute(
            select(Subscription)
            .options(selectinload(Subscription.user))
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_due(self, session: AsyncSession, *, now: datetime, limit: int) -> list[Subscription]:
        result = await session.execute(
            select(Subscription)
            .options(selectinload(Subscription.user))
            .where(Subscription.enabled.is_(True), Subscription.next_check_at.is_not(None), Subscription.next_check_at <= now)
            .order_by(Subscription.next_check_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_all(self, session: AsyncSession, limit: int = 500) -> list[Subscription]:
        result = await session.execute(
            select(Subscription).options(selectinload(Subscription.user)).order_by(Subscription.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def delete(self, session: AsyncSession, subscription_id: str) -> None:
        await session.execute(delete(Subscription).where(Subscription.id == subscription_id))

    async def update(self, session: AsyncSession, *, subscription: Subscription, payload: SubscriptionCreate) -> Subscription:
        subscription.name = payload.name
        subscription.origin_iata = payload.origin_iata
        subscription.destination_iata = payload.destination_iata
        subscription.trip_type = payload.trip_type
        subscription.departure_date_from = payload.departure_date_from
        subscription.departure_date_to = payload.departure_date_to
        subscription.return_date_from = payload.return_date_from
        subscription.return_date_to = payload.return_date_to
        subscription.min_trip_duration_days = payload.min_trip_duration_days
        subscription.max_trip_duration_days = payload.max_trip_duration_days
        subscription.max_price = payload.max_price
        subscription.currency = payload.currency
        subscription.market = payload.market
        subscription.direct_only = payload.direct_only
        subscription.baggage_policy = payload.baggage_policy
        subscription.preferred_airlines = payload.preferred_airlines
        subscription.check_interval_minutes = payload.check_interval_minutes
        await session.flush()
        return subscription
