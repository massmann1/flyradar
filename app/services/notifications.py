from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.domain.enums import NotificationReason, NotificationStatus
from app.domain.models import NotificationEvent, Offer, Subscription
from app.domain.schemas import PriceHistoryContext
from app.repositories.notifications import NotificationRepository
from app.services.charts import build_price_history_chart
from app.services.price_history import PriceHistoryService


class NotificationService:
    def __init__(self, session_factory: async_sessionmaker, price_history_service: PriceHistoryService, bot: Bot | None = None) -> None:
        self._session_factory = session_factory
        self._price_history_service = price_history_service
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
                history_context = await self._price_history_service.build_context_for_session(
                    session,
                    subscription_id=event.subscription_id,
                    offer_id=event.offer_id,
                    current_price=event.price_amount,
                )
                chart_bytes = (
                    build_price_history_chart(
                        context=history_context,
                        current_price=event.price_amount,
                        currency=event.currency,
                    )
                    if history_context is not None
                    else None
                )

                if chart_bytes:
                    if len(event.message_text) <= 1024:
                        await self._bot.send_photo(
                            chat_id=event.chat_id,
                            photo=BufferedInputFile(chart_bytes, filename="price-history.png"),
                            caption=event.message_text,
                            parse_mode="HTML",
                        )
                    else:
                        await self._bot.send_photo(
                            chat_id=event.chat_id,
                            photo=BufferedInputFile(chart_bytes, filename="price-history.png"),
                            caption="Аналитика цены по истории наблюдений бота",
                        )
                        await self._bot.send_message(chat_id=event.chat_id, text=event.message_text, parse_mode="HTML")
                else:
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
    history_context: PriceHistoryContext | None = None,
    provider_found_at: datetime | None = None,
) -> str:
    parts = [
        "<b>Найден оффер</b>",
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
    if provider_found_at is not None:
        parts.append(f"Найден в кэше провайдера: <b>{_format_timestamp(provider_found_at)}</b>")
    parts.append(f"Впервые замечен ботом: <b>{_format_timestamp(offer.first_seen_at)}</b>")
    parts.append(f"Последнее наблюдение ботом: <b>{_format_timestamp(offer.last_seen_at)}</b>")
    if history_context is not None:
        parts.extend(_render_history_context(history_context=history_context, current_price=price_amount, currency=currency))
    if offer.deeplink_path:
        parts.append(f"Ссылка: https://www.aviasales.com{offer.deeplink_path}")
    parts.append("Данные кэшированные, цена и наличие могли измениться.")
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


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "-"
    current = value.astimezone(timezone.utc) if value.tzinfo is not None else value
    suffix = " UTC" if current.tzinfo is not None else ""
    return current.strftime("%d.%m.%Y %H:%M") + suffix


def _format_money(value: Decimal) -> str:
    if value == value.to_integral_value():
        return f"{int(value):,}".replace(",", " ")
    return f"{value:,.2f}".replace(",", " ").rstrip("0").rstrip(".")


def _render_history_context(
    *,
    history_context: PriceHistoryContext,
    current_price: Decimal,
    currency: str,
) -> list[str]:
    parts = [
        (
            f"По истории наблюдений бота за <b>{history_context.lookback_days} дн.</b>: "
            f"минимум <b>{_format_money(history_context.min_price)} {currency}</b>"
            + (
                f" ({history_context.min_price_day.strftime('%d.%m.%Y')})"
                if history_context.min_price_day is not None
                else ""
            )
        )
    ]

    if history_context.delta_to_min > 0 and history_context.min_price > 0:
        percent = (history_context.delta_to_min / history_context.min_price) * 100
        parts.append(
            f"Сейчас выше минимума на <b>{_format_money(history_context.delta_to_min)} {currency}</b> "
            f"({percent.quantize(Decimal('0.1'))}%)"
        )
    elif history_context.delta_to_min == 0:
        parts.append("Сейчас это минимум по истории наблюдений бота.")
    elif history_context.delta_to_min < 0:
        parts.append(
            f"Сейчас ниже прошлого минимума на <b>{_format_money(abs(history_context.delta_to_min))} {currency}</b>"
        )

    parts.append(f"Дней в истории: <b>{history_context.sample_days}</b>")
    return parts
