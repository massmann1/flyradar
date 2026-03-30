from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.domain.enums import NotificationReason, TripType
from app.domain.schemas import NotificationDTO
from app.services.alerts import AlertService
from app.services.alerts import _pick_cheapest_notification_candidate
from app.services.dedupe import choose_notification_reason


def test_alert_rule_prefers_threshold(subscription_stub, settings) -> None:
    subscription_stub.max_price = Decimal("12000")

    reason = choose_notification_reason(
        subscription=subscription_stub,
        last_sent_event=None,
        current_price=Decimal("11000"),
        is_new_offer=True,
        settings=settings,
    )

    assert reason == NotificationReason.PRICE_BELOW_THRESHOLD


def test_alert_rule_detects_absolute_price_drop(subscription_stub, settings) -> None:
    subscription_stub.max_price = None
    last_sent_event = SimpleNamespace(price_amount=Decimal("15000"))

    reason = choose_notification_reason(
        subscription=subscription_stub,
        last_sent_event=last_sent_event,
        current_price=Decimal("14000"),
        is_new_offer=False,
        settings=settings,
    )

    assert reason == NotificationReason.PRICE_DROP


def test_alert_rule_detects_new_variant(subscription_stub, settings) -> None:
    subscription_stub.max_price = None

    reason = choose_notification_reason(
        subscription=subscription_stub,
        last_sent_event=None,
        current_price=Decimal("20000"),
        is_new_offer=True,
        settings=settings,
    )

    assert reason == NotificationReason.NEW_VARIANT


def test_alert_rule_returns_none_when_nothing_changed(subscription_stub, settings) -> None:
    subscription_stub.max_price = Decimal("10000")
    last_sent_event = SimpleNamespace(price_amount=Decimal("15000"))

    reason = choose_notification_reason(
        subscription=subscription_stub,
        last_sent_event=last_sent_event,
        current_price=Decimal("14990"),
        is_new_offer=False,
        settings=settings,
    )

    assert reason is None


def test_round_trip_offer_without_return_is_rejected() -> None:
    subscription = SimpleNamespace(
        trip_type=TripType.ROUND_TRIP,
        max_price=Decimal("15000"),
        departure_date_from=datetime(2026, 6, 1, tzinfo=timezone.utc).date(),
        departure_date_to=None,
        return_date_from=datetime(2026, 6, 12, tzinfo=timezone.utc).date(),
        return_date_to=None,
        min_trip_duration_days=None,
        max_trip_duration_days=None,
        direct_only=False,
        preferred_airlines=[],
    )
    offer = SimpleNamespace(
        departure_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        return_at=None,
        price_amount=Decimal("10336"),
        transfers=0,
        return_transfers=None,
        airline_iata="N4",
    )

    assert AlertService._offer_matches_subscription(subscription, offer) is False  # noqa: SLF001


def test_round_trip_offer_with_expected_return_is_accepted() -> None:
    subscription = SimpleNamespace(
        trip_type=TripType.ROUND_TRIP,
        max_price=Decimal("15000"),
        departure_date_from=datetime(2026, 6, 1, tzinfo=timezone.utc).date(),
        departure_date_to=None,
        return_date_from=datetime(2026, 6, 12, tzinfo=timezone.utc).date(),
        return_date_to=None,
        min_trip_duration_days=None,
        max_trip_duration_days=None,
        direct_only=False,
        preferred_airlines=[],
    )
    offer = SimpleNamespace(
        departure_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        return_at=datetime(2026, 6, 12, 19, 0, tzinfo=timezone.utc),
        price_amount=Decimal("10336"),
        transfers=0,
        return_transfers=0,
        airline_iata="N4",
    )

    assert AlertService._offer_matches_subscription(subscription, offer) is True  # noqa: SLF001


def test_pick_cheapest_notification_candidate_returns_lowest_price() -> None:
    candidates = [
        NotificationDTO(
            subscription_id="sub-1",
            offer_id=1,
            dedupe_key="a",
            reason=NotificationReason.PRICE_BELOW_THRESHOLD,
            price_amount=Decimal("12912"),
            currency="RUB",
            chat_id=1,
            message_text="a",
        ),
        NotificationDTO(
            subscription_id="sub-1",
            offer_id=2,
            dedupe_key="b",
            reason=NotificationReason.PRICE_BELOW_THRESHOLD,
            price_amount=Decimal("12522"),
            currency="RUB",
            chat_id=1,
            message_text="b",
        ),
        NotificationDTO(
            subscription_id="sub-1",
            offer_id=3,
            dedupe_key="c",
            reason=NotificationReason.PRICE_BELOW_THRESHOLD,
            price_amount=Decimal("12700"),
            currency="RUB",
            chat_id=1,
            message_text="c",
        ),
    ]

    selected = _pick_cheapest_notification_candidate(candidates)

    assert selected is not None
    assert selected.offer_id == 2
    assert selected.price_amount == Decimal("12522")
