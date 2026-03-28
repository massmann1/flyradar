from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.domain.enums import NotificationReason, NotificationStatus
from app.domain.models import NotificationEvent, Offer, Subscription
from app.repositories.notifications import NotificationRepository


class NotificationService:
    def __init__(self, session_factory: async_sessionmaker, bot: Bot | None = None) -> None:
        self._session_factory = session_factory
        self._bot = bot
        self._notifications = NotificationRepository()

    async def send_event(self, event_id: int) -> bool:
        if self._bot is None:
            return False

        async with self._session_factory() as session:
            event = await self._notifications.get_by_id(session, event_id)
            if event is None:
                await session.commit()
                return False

            try:
                await self._bot.send_message(chat_id=event.chat_id, text=event.message_text, parse_mode="HTML")
                event.status = NotificationStatus.SENT
                event.sent_at = datetime.now(timezone.utc)
                event.error_message = None
                await session.commit()
                return True
            except Exception as exc:  # noqa: BLE001
                event.status = NotificationStatus.FAILED
                event.error_message = str(exc)
                await session.commit()
                return False

    async def retry_pending(self, limit: int = 20) -> int:
        if self._bot is None:
            return 0

        async with self._session_factory() as session:
            events = await self._notifications.list_pending(session, limit=limit)
            event_ids = [event.id for event in events]
            await session.commit()

        sent = 0
        for event_id in event_ids:
            if await self.send_event(event_id):
                sent += 1
        return sent


def format_offer_message(
    *,
    subscription: Subscription,
    offer: Offer,
    price_amount: Decimal,
    currency: str,
    reason: NotificationReason,
    previous_price: Decimal | None = None,
    airline_name: str | None = None,
) -> str:
    parts = [
        "<b>Найден билет</b>",
        f"Подписка: <b>{subscription.name}</b>",
        f"Маршрут: <b>{offer.origin_iata} -> {offer.destination_iata}</b>",
        f"Дата вылета: <b>{_format_trip_date(offer.departure_at)}</b>",
    ]

    if offer.return_at:
        parts.append(f"Дата возврата: <b>{_format_trip_date(offer.return_at)}</b>")

    parts.extend(
        [
            f"Цена: <b>{_format_money(price_amount)} {currency}</b>",
            f"Причина: <b>{_render_notification_reason(reason)}</b>",
            f"Пересадки: <b>{_render_transfers(offer.transfers)}</b>",
        ]
    )

    if offer.airline_iata:
        airline_label = f"{airline_name} ({offer.airline_iata})" if airline_name else offer.airline_iata
        parts.append(f"Авиакомпания: <b>{airline_label}</b>")
    if previous_price is not None and previous_price > price_amount:
        parts.append(f"Прошлая отправленная цена: <b>{_format_money(previous_price)} {currency}</b>")
    if offer.deeplink_path:
        parts.append(f"Ссылка: https://www.aviasales.com{offer.deeplink_path}")
    return "\n".join(parts)


def _render_notification_reason(reason: NotificationReason) -> str:
    labels = {
        NotificationReason.PRICE_BELOW_THRESHOLD: "цена ниже заданного лимита",
        NotificationReason.PRICE_DROP: "цена снизилась относительно прошлого уведомления",
        NotificationReason.NEW_VARIANT: "найден новый подходящий вариант",
    }
    return labels.get(reason, reason.value)


def _render_transfers(transfers: int | None) -> str:
    if transfers in (None, 0):
        return "без пересадок"
    return str(transfers)


def _format_trip_date(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.date().strftime("%d.%m.%Y")


def _format_money(value: Decimal) -> str:
    if value == value.to_integral_value():
        return f"{int(value):,}".replace(",", " ")
    return f"{value:,.2f}".replace(",", " ").rstrip("0").rstrip(".")
