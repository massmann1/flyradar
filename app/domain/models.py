from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.domain.enums import BaggagePolicy, CheckStatus, CheckTrigger, NotificationReason, NotificationStatus, TripType


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(16), default="ru")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_enabled_next_check_at", "enabled", "next_check_at"),
        Index("ix_subscriptions_user_enabled", "user_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    origin_iata: Mapped[str] = mapped_column(String(8))
    destination_iata: Mapped[str] = mapped_column(String(8))
    trip_type: Mapped[TripType] = mapped_column(Enum(TripType))
    departure_date_from: Mapped[date] = mapped_column(Date)
    departure_date_to: Mapped[date | None] = mapped_column(Date)
    return_date_from: Mapped[date | None] = mapped_column(Date)
    return_date_to: Mapped[date | None] = mapped_column(Date)
    min_trip_duration_days: Mapped[int | None] = mapped_column(Integer)
    max_trip_duration_days: Mapped[int | None] = mapped_column(Integer)
    max_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    market: Mapped[str] = mapped_column(String(8), default="ru")
    direct_only: Mapped[bool] = mapped_column(Boolean, default=False)
    baggage_policy: Mapped[BaggagePolicy] = mapped_column(Enum(BaggagePolicy), default=BaggagePolicy.IGNORE)
    preferred_airlines: Mapped[list[str]] = mapped_column(JSON, default=list)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_match_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="subscriptions")
    offer_prices: Mapped[list["OfferPrice"]] = relationship(back_populates="subscription", cascade="all, delete-orphan")
    checks: Mapped[list["SubscriptionCheck"]] = relationship(back_populates="subscription", cascade="all, delete-orphan")
    notifications: Mapped[list["NotificationEvent"]] = relationship(back_populates="subscription", cascade="all, delete-orphan")


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (Index("ix_offers_last_seen_at", "last_seen_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stable_variant_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    origin_iata: Mapped[str] = mapped_column(String(8))
    destination_iata: Mapped[str] = mapped_column(String(8))
    origin_airport_iata: Mapped[str | None] = mapped_column(String(8))
    destination_airport_iata: Mapped[str | None] = mapped_column(String(8))
    departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    return_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    airline_iata: Mapped[str | None] = mapped_column(String(8))
    flight_number: Mapped[str | None] = mapped_column(String(32))
    transfers: Mapped[int | None] = mapped_column(Integer)
    return_transfers: Mapped[int | None] = mapped_column(Integer)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    deeplink_path: Mapped[str | None] = mapped_column(Text)
    source_endpoint: Mapped[str] = mapped_column(String(64))
    raw_payload: Mapped[dict] = mapped_column(JSON)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    prices: Mapped[list["OfferPrice"]] = relationship(back_populates="offer", cascade="all, delete-orphan")
    notifications: Mapped[list["NotificationEvent"]] = relationship(back_populates="offer", cascade="all, delete-orphan")


class OfferPrice(Base):
    __tablename__ = "offer_prices"
    __table_args__ = (
        Index("ix_offer_prices_observed_at", "observed_at"),
        Index("ix_offer_prices_subscription_observed_at", "subscription_id", "observed_at"),
        Index("ix_offer_prices_offer_observed_at", "offer_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"))
    subscription_id: Mapped[str] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    provider_found_at: Mapped[datetime | None] = mapped_column("found_at", DateTime(timezone=True))
    api_cache_key: Mapped[str | None] = mapped_column(String(255))
    is_actual: Mapped[bool] = mapped_column(Boolean, default=True)

    offer: Mapped[Offer] = relationship(back_populates="prices")
    subscription: Mapped[Subscription] = relationship(back_populates="offer_prices")


class OfferPriceDailyStat(Base):
    __tablename__ = "offer_price_daily_stats"
    __table_args__ = (
        UniqueConstraint("subscription_id", "offer_id", "day", "currency", name="uq_offer_price_daily_stats_key"),
        Index("ix_offer_price_daily_stats_day", "day"),
        Index("ix_offer_price_daily_stats_subscription_day", "subscription_id", "day"),
        Index("ix_offer_price_daily_stats_offer_day", "offer_id", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"))
    subscription_id: Mapped[str] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    min_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    max_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    avg_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sample_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SubscriptionCheck(Base):
    __tablename__ = "subscription_checks"
    __table_args__ = (
        Index("ix_subscription_checks_subscription_started_at", "subscription_id", "started_at"),
        Index("ix_subscription_checks_finished_at", "finished_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subscription_id: Mapped[str] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"))
    trigger_type: Mapped[CheckTrigger] = mapped_column(Enum(CheckTrigger))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[CheckStatus] = mapped_column(Enum(CheckStatus), default=CheckStatus.PENDING)
    endpoint_used: Mapped[str | None] = mapped_column(String(64))
    request_hash: Mapped[str | None] = mapped_column(String(255))
    offers_found: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    subscription: Mapped[Subscription] = relationship(back_populates="checks")


class NotificationEvent(Base):
    __tablename__ = "notification_events"
    __table_args__ = (
        Index("ix_notification_events_created_at", "created_at"),
        Index("ix_notification_events_subscription_dedupe_created", "subscription_id", "dedupe_key", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subscription_id: Mapped[str] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"))
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"))
    reason: Mapped[NotificationReason] = mapped_column(Enum(NotificationReason))
    status: Mapped[NotificationStatus] = mapped_column(Enum(NotificationStatus), default=NotificationStatus.PENDING)
    dedupe_key: Mapped[str] = mapped_column(String(255))
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    subscription: Mapped[Subscription] = relationship(back_populates="notifications")
    offer: Mapped[Offer] = relationship(back_populates="notifications")


class ApiCache(Base):
    __tablename__ = "api_cache"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_api_cache_cache_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(255), index=True)
    endpoint: Mapped[str] = mapped_column(String(64))
    normalized_params: Mapped[dict] = mapped_column(JSON)
    response_json: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    http_status: Mapped[int] = mapped_column(Integer)
