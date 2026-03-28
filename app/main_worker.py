from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.bot.handlers.subscriptions import build_subscription_router
from app.core.config import get_settings
from app.core.container import create_container
from app.core.logging import configure_logging
from app.scheduler.jobs import build_scheduler


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    bot = Bot(token=settings.telegram_bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    container = create_container(settings, bot=bot)
    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_subscription_router(
            settings=settings,
            subscription_service=container.subscription_service,
            alert_service=container.alert_service,
            travelpayouts_client=container.travelpayouts_client,
        )
    )

    scheduler = build_scheduler(settings, container.alert_service)
    scheduler.start()

    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await container.close()


if __name__ == "__main__":
    asyncio.run(main())
