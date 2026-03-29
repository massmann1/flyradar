from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.domain.enums import NotificationReason
from app.domain.schemas import PriceHistoryContext, PriceHistoryPoint
from app.services.notifications import format_offer_message


def test_format_offer_message_uses_russian_reason_and_airline_name() -> None:
    subscription = SimpleNamespace(name="Лето во Вьетнаме")
    offer = SimpleNamespace(
        origin_iata="KZN",
        destination_iata="NHA",
        departure_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        return_at=datetime(2026, 6, 12, 15, 0, tzinfo=timezone.utc),
        transfers=0,
        airline_iata="TK",
        deeplink_path="/search/mock",
        first_seen_at=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 3, 2, 10, 30, tzinfo=timezone.utc),
    )

    message = format_offer_message(
        subscription=subscription,
        offer=offer,
        price_amount=Decimal("45670"),
        currency="RUB",
        reason=NotificationReason.PRICE_DROP,
        previous_price=Decimal("49800"),
        airline_name="Turkish Airlines",
        provider_found_at=datetime(2026, 2, 28, 23, 15, tzinfo=timezone.utc),
    )

    assert "цена снизилась относительно прошлого уведомления" in message
    assert "Turkish Airlines (TK)" in message
    assert "45 670 RUB" in message
    assert "01.06.2026" in message
    assert "12.06.2026" in message
    assert "Найден в кэше провайдера" in message
    assert "Впервые замечен ботом" in message
    assert "Последнее наблюдение ботом" in message
    assert "Ссылка:" not in message
    assert "<a href=\"https://www.aviasales.com/search/mock\">Открыть вариант в Aviasales</a>" in message
    assert "Данные кэшированные, цена и наличие могли измениться." in message


def test_format_offer_message_includes_history_context() -> None:
    subscription = SimpleNamespace(name="Лето во Вьетнаме")
    offer = SimpleNamespace(
        origin_iata="KZN",
        destination_iata="NHA",
        departure_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        return_at=None,
        transfers=1,
        airline_iata="TK",
        deeplink_path=None,
        first_seen_at=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 3, 2, 10, 30, tzinfo=timezone.utc),
    )
    history_context = PriceHistoryContext(
        lookback_days=30,
        min_price=Decimal("39990"),
        min_price_day=datetime(2026, 5, 10, tzinfo=timezone.utc).date(),
        delta_to_min=Decimal("5680"),
        sample_days=7,
        points=[
            PriceHistoryPoint(day=datetime(2026, 5, 10, tzinfo=timezone.utc).date(), price_amount=Decimal("39990")),
            PriceHistoryPoint(day=datetime(2026, 5, 12, tzinfo=timezone.utc).date(), price_amount=Decimal("42000")),
        ],
    )

    message = format_offer_message(
        subscription=subscription,
        offer=offer,
        price_amount=Decimal("45670"),
        currency="RUB",
        reason=NotificationReason.PRICE_BELOW_THRESHOLD,
        airline_name="Turkish Airlines",
        history_context=history_context,
        provider_found_at=None,
    )

    assert "По истории наблюдений бота за" in message
    assert "минимум" in message
    assert "Дней в истории" in message
    assert "Найден в кэше провайдера" not in message
