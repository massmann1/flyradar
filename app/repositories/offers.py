from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Offer, OfferPrice
from app.domain.schemas import OfferDTO


class OfferRepository:
    async def get_by_stable_variant_key(self, session: AsyncSession, stable_variant_key: str) -> Offer | None:
        result = await session.execute(select(Offer).where(Offer.stable_variant_key == stable_variant_key))
        return result.scalar_one_or_none()

    async def upsert_offer(self, session: AsyncSession, dto: OfferDTO) -> Offer:
        offer = await self.get_by_stable_variant_key(session, dto.stable_variant_key)
        if offer is None:
            offer = Offer(
                stable_variant_key=dto.stable_variant_key,
                origin_iata=dto.origin_iata,
                destination_iata=dto.destination_iata,
                origin_airport_iata=dto.origin_airport_iata,
                destination_airport_iata=dto.destination_airport_iata,
                departure_at=dto.departure_at,
                return_at=dto.return_at,
                airline_iata=dto.airline_iata,
                flight_number=dto.flight_number,
                transfers=dto.transfers,
                return_transfers=dto.return_transfers,
                duration_minutes=dto.duration_minutes,
                deeplink_path=dto.deeplink,
                source_endpoint=dto.source_endpoint,
                raw_payload=dto.raw_payload,
            )
            session.add(offer)
            await session.flush()
            return offer

        offer.origin_airport_iata = dto.origin_airport_iata
        offer.destination_airport_iata = dto.destination_airport_iata
        offer.departure_at = dto.departure_at
        offer.return_at = dto.return_at
        offer.airline_iata = dto.airline_iata
        offer.flight_number = dto.flight_number
        offer.transfers = dto.transfers
        offer.return_transfers = dto.return_transfers
        offer.duration_minutes = dto.duration_minutes
        offer.deeplink_path = dto.deeplink
        offer.raw_payload = dto.raw_payload
        offer.last_seen_at = datetime.now(timezone.utc)
        return offer

    async def get_last_price_for_offer_and_subscription(
        self,
        session: AsyncSession,
        *,
        offer_id: int,
        subscription_id: str,
    ) -> OfferPrice | None:
        result = await session.execute(
            select(OfferPrice)
            .where(OfferPrice.offer_id == offer_id, OfferPrice.subscription_id == subscription_id)
            .order_by(OfferPrice.observed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add_price_observation(
        self,
        session: AsyncSession,
        *,
        offer_id: int,
        subscription_id: str,
        price_amount: Decimal,
        currency: str,
        found_at: datetime | None,
        api_cache_key: str | None,
    ) -> OfferPrice:
        latest = await self.get_last_price_for_offer_and_subscription(
            session,
            offer_id=offer_id,
            subscription_id=subscription_id,
        )
        if latest and latest.price_amount == price_amount and latest.observed_at >= datetime.now(timezone.utc) - timedelta(hours=24):
            latest.is_actual = True
            return latest

        offer_price = OfferPrice(
            offer_id=offer_id,
            subscription_id=subscription_id,
            price_amount=price_amount,
            currency=currency,
            found_at=found_at,
            api_cache_key=api_cache_key,
            is_actual=True,
        )
        session.add(offer_price)
        await session.flush()
        return offer_price

    async def list_recent_for_subscription(self, session: AsyncSession, subscription_id: str, limit: int = 5) -> list[tuple[Offer, OfferPrice]]:
        result = await session.execute(
            select(Offer, OfferPrice)
            .join(OfferPrice, OfferPrice.offer_id == Offer.id)
            .where(OfferPrice.subscription_id == subscription_id)
            .order_by(desc(OfferPrice.observed_at))
            .limit(limit)
        )
        return list(result.all())
