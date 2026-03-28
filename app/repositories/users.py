from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import User


class UserRepository:
    async def get_by_telegram_user_id(self, session: AsyncSession, telegram_user_id: int) -> User | None:
        result = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        session: AsyncSession,
        *,
        telegram_user_id: int,
        username: str | None,
        is_admin: bool,
        locale: str = "ru",
        timezone_name: str = "UTC",
    ) -> User:
        user = await self.get_by_telegram_user_id(session, telegram_user_id)
        if user:
            if username is not None:
                user.username = username
            user.is_admin = is_admin
            return user

        user = User(
            telegram_user_id=telegram_user_id,
            username=username,
            is_admin=is_admin,
            locale=locale,
            timezone=timezone_name,
        )
        session.add(user)
        await session.flush()
        return user
