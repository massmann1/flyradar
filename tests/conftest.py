from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.clients.travelpayouts_rest import TravelpayoutsRestClient
from app.core.config import Settings
from app.domain.enums import TripType


@pytest.fixture
def settings() -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "DATABASE_URL": "postgresql+psycopg://flight_alerts:flight_alerts@localhost:5432/flight_alerts",
            "ADMIN_API_TOKEN": "admin-token",
            "TELEGRAM_BOT_TOKEN": "telegram-token",
            "TELEGRAM_ALLOWED_USER_IDS": "1",
            "TRAVELPAYOUTS_API_TOKEN": "tp-token",
        }
    )


@pytest.fixture
def travelpayouts_client(settings: Settings) -> TravelpayoutsRestClient:
    http_client = httpx.AsyncClient()
    try:
        yield TravelpayoutsRestClient(http_client=http_client, settings=settings)
    finally:
        asyncio.run(http_client.aclose())


@pytest.fixture
def valid_subscription_create() -> dict:
    return {
        "name": "Weekend in Istanbul",
        "origin_iata": "mow",
        "destination_iata": "ist",
        "trip_type": TripType.ROUND_TRIP,
        "departure_date_from": date(2026, 5, 1),
        "departure_date_to": date(2026, 5, 10),
        "min_trip_duration_days": 3,
        "max_trip_duration_days": 5,
        "max_price": Decimal("15000"),
        "currency": "rub",
        "market": "RU",
        "direct_only": True,
        "preferred_airlines": ["tk", " pc "],
        "check_interval_minutes": 60,
    }


@pytest.fixture
def subscription_stub() -> SimpleNamespace:
    return SimpleNamespace(
        id="sub-1",
        name="Weekend in Istanbul",
        currency="RUB",
        max_price=Decimal("15000"),
        preferred_airlines=[],
    )


@pytest.fixture
def offer_stub() -> SimpleNamespace:
    return SimpleNamespace(
        stable_variant_key="offer-1",
        origin_iata="MOW",
        destination_iata="IST",
        airline_iata="TK",
    )
