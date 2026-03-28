from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.domain.schemas import PriceHistoryContext, PriceHistoryPoint
from app.repositories.offers import OfferRepository


class PriceHistoryService:
    def __init__(self, session_factory: async_sessionmaker, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._offers = OfferRepository()

    async def build_context(
        self,
        *,
        subscription_id: str,
        offer_id: int,
        current_price: Decimal,
    ) -> PriceHistoryContext | None:
        async with self._session_factory() as session:
            context = await self.build_context_for_session(
                session,
                subscription_id=subscription_id,
                offer_id=offer_id,
                current_price=current_price,
            )
            await session.commit()
            return context

    async def build_context_for_session(
        self,
        session: AsyncSession,
        *,
        subscription_id: str,
        offer_id: int,
        current_price: Decimal,
    ) -> PriceHistoryContext | None:
        now = datetime.now(timezone.utc)
        since_day = (now - timedelta(days=self._settings.history_context_days)).date()
        since_dt = now - timedelta(days=self._settings.history_context_days)

        daily_points = await self._offers.list_daily_price_points(
            session,
            subscription_id=subscription_id,
            offer_id=offer_id,
            since_day=since_day,
        )
        detail_points = await self._offers.list_recent_detail_price_points(
            session,
            subscription_id=subscription_id,
            offer_id=offer_id,
            since=since_dt,
        )

        combined: dict = {}
        for point_day, price_amount in [*daily_points, *detail_points]:
            existing = combined.get(point_day)
            if existing is None or price_amount < existing:
                combined[point_day] = Decimal(price_amount)

        if not combined:
            return None

        ordered_points = [
            PriceHistoryPoint(day=point_day, price_amount=price_amount)
            for point_day, price_amount in sorted(combined.items())
        ]
        min_day, min_price = min(combined.items(), key=lambda item: item[1])
        return PriceHistoryContext(
            lookback_days=self._settings.history_context_days,
            min_price=Decimal(min_price),
            min_price_day=min_day,
            delta_to_min=(current_price - Decimal(min_price)).quantize(Decimal("0.01")),
            sample_days=len(ordered_points),
            points=ordered_points,
        )

    async def aggregate_old_detail_history(self) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        detail_cutoff = now - timedelta(days=self._settings.offer_price_detail_retention_days)
        daily_retention_cutoff = now.date() - timedelta(days=self._settings.offer_price_daily_retention_days)

        aggregated_rows = 0
        aggregated_days = 0
        deleted_rows = 0

        while True:
            async with self._session_factory() as session:
                rows = await self._offers.list_old_price_observations(
                    session,
                    older_than=detail_cutoff,
                    limit=self._settings.cleanup_batch_size,
                )
                if not rows:
                    deleted_daily = await self._offers.prune_old_daily_stats(
                        session,
                        older_than=daily_retention_cutoff,
                    )
                    await session.commit()
                    return {
                        "aggregated_rows": aggregated_rows,
                        "aggregated_days": aggregated_days,
                        "deleted_rows": deleted_rows,
                        "deleted_daily_stats": deleted_daily,
                    }

                grouped: dict[tuple, dict] = {}
                for row in rows:
                    key = (row.subscription_id, row.offer_id, row.observed_at.date(), row.currency)
                    bucket = grouped.setdefault(
                        key,
                        {
                            "min_price": row.price_amount,
                            "max_price": row.price_amount,
                            "sum_price": Decimal("0"),
                            "sample_count": 0,
                        },
                    )
                    bucket["min_price"] = min(bucket["min_price"], row.price_amount)
                    bucket["max_price"] = max(bucket["max_price"], row.price_amount)
                    bucket["sum_price"] += row.price_amount
                    bucket["sample_count"] += 1

                for (subscription_id, offer_id, day, currency), bucket in grouped.items():
                    avg_price = (bucket["sum_price"] / bucket["sample_count"]).quantize(Decimal("0.01"))
                    await self._offers.upsert_daily_stat(
                        session,
                        subscription_id=subscription_id,
                        offer_id=offer_id,
                        day=day,
                        currency=currency,
                        min_price=bucket["min_price"],
                        max_price=bucket["max_price"],
                        avg_price=avg_price,
                        sample_count=bucket["sample_count"],
                    )

                deleted_rows += await self._offers.delete_price_observations(
                    session,
                    price_ids=[row.id for row in rows],
                )
                aggregated_rows += len(rows)
                aggregated_days += len(grouped)
                await session.commit()
