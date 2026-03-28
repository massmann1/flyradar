from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

from app.domain import models  # noqa: F401

revision = "20260329_000002"
down_revision = "20260328_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    models.OfferPriceDailyStat.__table__.create(bind, checkfirst=True)
    _create_index_if_missing(bind, "offers", "ix_offers_last_seen_at", ["last_seen_at"])
    _create_index_if_missing(bind, "offer_prices", "ix_offer_prices_observed_at", ["observed_at"])
    _create_index_if_missing(bind, "subscription_checks", "ix_subscription_checks_finished_at", ["finished_at"])
    _create_index_if_missing(bind, "notification_events", "ix_notification_events_created_at", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    _drop_index_if_exists(bind, "notification_events", "ix_notification_events_created_at")
    _drop_index_if_exists(bind, "subscription_checks", "ix_subscription_checks_finished_at")
    _drop_index_if_exists(bind, "offer_prices", "ix_offer_prices_observed_at")
    _drop_index_if_exists(bind, "offers", "ix_offers_last_seen_at")
    models.OfferPriceDailyStat.__table__.drop(bind, checkfirst=True)


def _create_index_if_missing(bind, table_name: str, index_name: str, columns: list[str]) -> None:
    inspector = inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=False)


def _drop_index_if_exists(bind, table_name: str, index_name: str) -> None:
    inspector = inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)
