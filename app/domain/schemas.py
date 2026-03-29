from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import BaggagePolicy, CheckStatus, NotificationReason, NotificationStatus, TripType


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    origin_iata: str = Field(min_length=3, max_length=8)
    destination_iata: str = Field(min_length=3, max_length=8)
    trip_type: TripType
    departure_date_from: date
    departure_date_to: date | None = None
    return_date_from: date | None = None
    return_date_to: date | None = None
    min_trip_duration_days: int | None = None
    max_trip_duration_days: int | None = None
    max_price: Decimal | None = None
    currency: str = "RUB"
    market: str = "ru"
    direct_only: bool = False
    baggage_policy: BaggagePolicy = BaggagePolicy.IGNORE
    preferred_airlines: list[str] = Field(default_factory=list)
    check_interval_minutes: int = 60

    @field_validator("origin_iata", "destination_iata")
    @classmethod
    def normalize_iata(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("preferred_airlines")
    @classmethod
    def normalize_airlines(cls, values: list[str]) -> list[str]:
        return [value.strip().upper() for value in values if value.strip()]

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_subscription(self) -> "SubscriptionCreate":
        if self.origin_iata == self.destination_iata:
            raise ValueError("Origin and destination must be different.")

        if self.departure_date_to and self.departure_date_to < self.departure_date_from:
            raise ValueError("Departure date range is invalid.")

        if self.max_price is not None and self.max_price <= 0:
            raise ValueError("Max price must be positive.")

        if self.check_interval_minutes < 15:
            raise ValueError("Check interval must be at least 15 minutes.")

        if self.trip_type == TripType.ONE_WAY:
            if any(
                value is not None
                for value in (
                    self.return_date_from,
                    self.return_date_to,
                    self.min_trip_duration_days,
                    self.max_trip_duration_days,
                )
            ):
                raise ValueError("One-way subscriptions cannot have return dates or trip duration.")
            return self

        if self.return_date_to and self.return_date_from is None:
            raise ValueError("Return date range requires return_date_from.")

        if self.return_date_from and self.return_date_to and self.return_date_to < self.return_date_from:
            raise ValueError("Return date range is invalid.")

        if self.min_trip_duration_days is not None and self.min_trip_duration_days <= 0:
            raise ValueError("Trip duration must be positive.")

        if self.max_trip_duration_days is not None and self.max_trip_duration_days <= 0:
            raise ValueError("Trip duration must be positive.")

        if (
            self.min_trip_duration_days is not None
            and self.max_trip_duration_days is not None
            and self.max_trip_duration_days < self.min_trip_duration_days
        ):
            raise ValueError("Trip duration range is invalid.")

        has_return_dates = self.return_date_from is not None
        has_duration = self.min_trip_duration_days is not None
        if not has_return_dates and not has_duration:
            raise ValueError("Round-trip subscriptions require return dates or trip duration.")

        return self


class SubscriptionUpdate(BaseModel):
    enabled: bool | None = None
    next_check_at: datetime | None = None


class OfferDTO(BaseModel):
    stable_variant_key: str
    exact_offer_key: str
    origin_iata: str
    destination_iata: str
    origin_airport_iata: str | None = None
    destination_airport_iata: str | None = None
    departure_at: datetime | None = None
    return_at: datetime | None = None
    airline_iata: str | None = None
    flight_number: str | None = None
    transfers: int | None = None
    return_transfers: int | None = None
    duration_minutes: int | None = None
    price_amount: Decimal
    currency: str
    deeplink: str | None = None
    source_endpoint: str
    provider_found_at: datetime | None = None
    raw_payload: dict


class CheckResult(BaseModel):
    subscription_id: str
    status: CheckStatus
    endpoint_used: str | None = None
    offers_found: int = 0
    notifications_sent: int = 0
    error_message: str | None = None


class NotificationDTO(BaseModel):
    subscription_id: str
    offer_id: int
    dedupe_key: str
    reason: NotificationReason
    status: NotificationStatus = NotificationStatus.PENDING
    price_amount: Decimal
    currency: str
    chat_id: int
    message_text: str


class PriceHistoryPoint(BaseModel):
    day: date
    price_amount: Decimal


class PriceHistoryContext(BaseModel):
    lookback_days: int
    min_price: Decimal
    min_price_day: date | None = None
    delta_to_min: Decimal
    sample_days: int = 0
    points: list[PriceHistoryPoint] = Field(default_factory=list)
