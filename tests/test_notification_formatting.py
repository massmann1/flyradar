from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.domain.enums import NotificationReason
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
    )

    message = format_offer_message(
        subscription=subscription,
        offer=offer,
        price_amount=Decimal("45670"),
        currency="RUB",
        reason=NotificationReason.PRICE_DROP,
        previous_price=Decimal("49800"),
        airline_name="Turkish Airlines",
    )

    assert "цена снизилась относительно прошлого уведомления" in message
    assert "Turkish Airlines (TK)" in message
    assert "45 670 RUB" in message
    assert "01.06.2026" in message
    assert "12.06.2026" in message
