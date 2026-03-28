from __future__ import annotations

from decimal import Decimal

from app.services.dedupe import build_notification_dedupe_key


def test_dedupe_key_changes_with_price(subscription_stub, offer_stub) -> None:
    key_a = build_notification_dedupe_key(subscription_stub, offer_stub, Decimal("10000"))
    key_b = build_notification_dedupe_key(subscription_stub, offer_stub, Decimal("11000"))

    assert key_a != key_b


def test_dedupe_key_is_stable_for_same_input(subscription_stub, offer_stub) -> None:
    key_a = build_notification_dedupe_key(subscription_stub, offer_stub, Decimal("10000"))
    key_b = build_notification_dedupe_key(subscription_stub, offer_stub, Decimal("10000"))

    assert key_a == key_b
