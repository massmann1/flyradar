from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ApiCache


class ApiCacheRepository:
    async def get_by_cache_key(self, session: AsyncSession, *, cache_key: str) -> ApiCache | None:
        result = await session.execute(select(ApiCache).where(ApiCache.cache_key == cache_key))
        return result.scalar_one_or_none()

    async def get_valid(self, session: AsyncSession, *, cache_key: str, now: datetime) -> ApiCache | None:
        result = await session.execute(
            select(ApiCache).where(ApiCache.cache_key == cache_key, ApiCache.expires_at >= now)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        session: AsyncSession,
        *,
        cache_key: str,
        endpoint: str,
        normalized_params: dict,
        response_json: dict,
        fetched_at: datetime,
        expires_at: datetime,
        http_status: int,
    ) -> ApiCache:
        cached = await self.get_by_cache_key(session, cache_key=cache_key)
        if cached is None:
            cached = ApiCache(
                cache_key=cache_key,
                endpoint=endpoint,
                normalized_params=normalized_params,
                response_json=response_json,
                fetched_at=fetched_at,
                expires_at=expires_at,
                http_status=http_status,
            )
            session.add(cached)
            await session.flush()
            return cached

        cached.normalized_params = normalized_params
        cached.response_json = response_json
        cached.fetched_at = fetched_at
        cached.expires_at = expires_at
        cached.http_status = http_status
        return cached
