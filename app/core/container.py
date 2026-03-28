from __future__ import annotations

from dataclasses import dataclass

import httpx
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.clients.travelpayouts_rest import TravelpayoutsRestClient
from app.core.config import Settings
from app.core.db import build_engine, build_session_factory
from app.services.alerts import AlertService
from app.services.notifications import NotificationService
from app.services.price_history import PriceHistoryService
from app.services.subscriptions import SubscriptionService


@dataclass
class AppContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker
    http_client: httpx.AsyncClient
    travelpayouts_client: TravelpayoutsRestClient
    subscription_service: SubscriptionService
    price_history_service: PriceHistoryService
    notification_service: NotificationService
    alert_service: AlertService

    async def close(self) -> None:
        await self.http_client.aclose()
        await self.engine.dispose()


def create_container(settings: Settings, *, bot: Bot | None = None) -> AppContainer:
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    http_client = httpx.AsyncClient()
    travelpayouts_client = TravelpayoutsRestClient(http_client=http_client, settings=settings)
    price_history_service = PriceHistoryService(session_factory=session_factory, settings=settings)
    notification_service = NotificationService(session_factory=session_factory, price_history_service=price_history_service, bot=bot)
    subscription_service = SubscriptionService(session_factory=session_factory, settings=settings)
    alert_service = AlertService(
        session_factory=session_factory,
        settings=settings,
        travelpayouts_client=travelpayouts_client,
        price_history_service=price_history_service,
        notification_service=notification_service,
    )
    return AppContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        travelpayouts_client=travelpayouts_client,
        subscription_service=subscription_service,
        price_history_service=price_history_service,
        notification_service=notification_service,
        alert_service=alert_service,
    )
