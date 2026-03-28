from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.domain.schemas import SubscriptionCreate
from app.repositories.offers import OfferRepository
from app.repositories.subscriptions import SubscriptionRepository
from app.repositories.users import UserRepository


class SubscriptionService:
    def __init__(self, session_factory: async_sessionmaker, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._users = UserRepository()
        self._subscriptions = SubscriptionRepository()
        self._offers = OfferRepository()

    async def create_subscription(self, *, telegram_user_id: int, username: str | None, payload: SubscriptionCreate) -> str:
        async with self._session_factory() as session:
            user = await self._users.get_or_create(
                session,
                telegram_user_id=telegram_user_id,
                username=username,
                is_admin=telegram_user_id in self._settings.allowed_user_ids,
            )
            next_check_at = datetime.now(timezone.utc) + timedelta(minutes=1)
            subscription = await self._subscriptions.create(session, user_id=user.id, payload=payload, next_check_at=next_check_at)
            await session.commit()
            return subscription.id

    async def list_subscriptions(self, *, telegram_user_id: int, username: str | None) -> list:
        async with self._session_factory() as session:
            user = await self._users.get_or_create(
                session,
                telegram_user_id=telegram_user_id,
                username=username,
                is_admin=telegram_user_id in self._settings.allowed_user_ids,
            )
            items = await self._subscriptions.list_for_user(session, user.id)
            await session.commit()
            return items

    async def get_subscription(self, *, telegram_user_id: int, username: str | None, subscription_id: str):
        async with self._session_factory() as session:
            user = await self._users.get_or_create(
                session,
                telegram_user_id=telegram_user_id,
                username=username,
                is_admin=telegram_user_id in self._settings.allowed_user_ids,
            )
            subscription = await self._subscriptions.get_for_user(session, subscription_id, user.id)
            await session.commit()
            return subscription

    async def set_enabled(self, *, telegram_user_id: int, username: str | None, subscription_id: str, enabled: bool) -> bool:
        async with self._session_factory() as session:
            user = await self._users.get_or_create(
                session,
                telegram_user_id=telegram_user_id,
                username=username,
                is_admin=telegram_user_id in self._settings.allowed_user_ids,
            )
            subscription = await self._subscriptions.get_for_user(session, subscription_id, user.id)
            if subscription is None:
                await session.commit()
                return False

            subscription.enabled = enabled
            if enabled:
                subscription.next_check_at = datetime.now(timezone.utc)
            await session.commit()
            return True

    async def delete(self, *, telegram_user_id: int, username: str | None, subscription_id: str) -> bool:
        async with self._session_factory() as session:
            user = await self._users.get_or_create(
                session,
                telegram_user_id=telegram_user_id,
                username=username,
                is_admin=telegram_user_id in self._settings.allowed_user_ids,
            )
            subscription = await self._subscriptions.get_for_user(session, subscription_id, user.id)
            if subscription is None:
                await session.commit()
                return False

            await self._subscriptions.delete(session, subscription.id)
            await session.commit()
            return True

    async def request_manual_check(self, *, telegram_user_id: int, username: str | None, subscription_id: str) -> bool:
        async with self._session_factory() as session:
            user = await self._users.get_or_create(
                session,
                telegram_user_id=telegram_user_id,
                username=username,
                is_admin=telegram_user_id in self._settings.allowed_user_ids,
            )
            subscription = await self._subscriptions.get_for_user(session, subscription_id, user.id)
            if subscription is None:
                await session.commit()
                return False

            subscription.next_check_at = datetime.now(timezone.utc)
            await session.commit()
            return True

    async def list_recent_offers(self, *, telegram_user_id: int, username: str | None, subscription_id: str, limit: int = 5) -> list:
        async with self._session_factory() as session:
            user = await self._users.get_or_create(
                session,
                telegram_user_id=telegram_user_id,
                username=username,
                is_admin=telegram_user_id in self._settings.allowed_user_ids,
            )
            subscription = await self._subscriptions.get_for_user(session, subscription_id, user.id)
            if subscription is None:
                await session.commit()
                return []
            items = await self._offers.list_recent_for_subscription(session, subscription.id, limit=limit)
            await session.commit()
            return items
