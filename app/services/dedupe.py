from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.config import Settings
from app.domain.enums import NotificationReason
from app.domain.models import NotificationEvent, Offer, Subscription


def build_notification_dedupe_key(subscription: Subscription, offer: Offer, price_amount: Decimal) -> str:
    payload = "|".join(
        [
            subscription.id,
            offer.stable_variant_key,
            str(price_amount),
            subscription.currency,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def notification_cooldown_boundary(settings: Settings) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=settings.alert_cooldown_hours)


def choose_notification_reason(
    *,
    subscription: Subscription,
    last_sent_event: NotificationEvent | None,
    current_price: Decimal,
    is_new_offer: bool,
    settings: Settings,
) -> NotificationReason | None:
    if subscription.max_price is not None and current_price <= subscription.max_price:
        return NotificationReason.PRICE_BELOW_THRESHOLD

    if last_sent_event is not None:
        previous_price = last_sent_event.price_amount
        absolute_drop = previous_price - current_price
        if absolute_drop >= settings.min_price_drop_abs:
            return NotificationReason.PRICE_DROP
        if previous_price > 0:
            percent_drop = (absolute_drop / previous_price) * 100
            if percent_drop >= settings.min_price_drop_pct:
                return NotificationReason.PRICE_DROP

    if is_new_offer:
        if subscription.max_price is None or current_price <= subscription.max_price:
            return NotificationReason.NEW_VARIANT

    return None
