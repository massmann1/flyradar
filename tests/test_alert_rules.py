from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.domain.enums import NotificationReason
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
