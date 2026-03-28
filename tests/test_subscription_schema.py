from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.enums import TripType
from app.domain.schemas import SubscriptionCreate


def test_subscription_create_normalizes_fields(valid_subscription_create) -> None:
    model = SubscriptionCreate.model_validate(valid_subscription_create)

    assert model.origin_iata == "MOW"
    assert model.destination_iata == "IST"
    assert model.currency == "RUB"
    assert model.market == "ru"
    assert model.preferred_airlines == ["TK", "PC"]


def test_subscription_create_rejects_same_origin_and_destination(valid_subscription_create) -> None:
    payload = {**valid_subscription_create, "destination_iata": "MOW"}

    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate(payload)


def test_subscription_create_requires_round_trip_constraints(valid_subscription_create) -> None:
    payload = {
        **valid_subscription_create,
        "return_date_from": None,
        "return_date_to": None,
        "min_trip_duration_days": None,
        "max_trip_duration_days": None,
    }

    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate(payload)


def test_subscription_create_rejects_return_fields_for_one_way(valid_subscription_create) -> None:
    payload = {
        **valid_subscription_create,
        "trip_type": TripType.ONE_WAY,
        "return_date_from": date(2026, 5, 3),
    }

    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate(payload)


def test_subscription_create_rejects_invalid_interval(valid_subscription_create) -> None:
    payload = {**valid_subscription_create, "check_interval_minutes": 10}

    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate(payload)


def test_subscription_create_rejects_non_positive_price(valid_subscription_create) -> None:
    payload = {**valid_subscription_create, "max_price": Decimal("0")}

    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate(payload)
