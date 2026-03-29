from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Chat, ErrorEvent, Message

from app.bot.keyboards.subscriptions import (
    calendar_keyboard,
    confirm_keyboard,
    date_input_mode_keyboard,
    edit_dates_keyboard,
    return_mode_keyboard,
    subscription_actions_keyboard,
    trip_type_keyboard,
    yes_no_keyboard,
)
from app.bot.states import NewSubscriptionStates
from app.clients.travelpayouts_rest import TravelpayoutsRestClient
from app.core.config import Settings
from app.domain.enums import BaggagePolicy, CheckTrigger, TripType
from app.domain.schemas import SubscriptionCreate
from app.services.alerts import AlertService
from app.services.subscriptions import SubscriptionService

logger = logging.getLogger(__name__)


def build_subscription_router(
    *,
    settings: Settings,
    subscription_service: SubscriptionService,
    alert_service: AlertService,
    travelpayouts_client: TravelpayoutsRestClient,
) -> Router:
    router = Router()

    async def ensure_access(message_or_callback: Message | CallbackQuery) -> bool:
        user = message_or_callback.from_user
        chat = message_or_callback.message.chat if isinstance(message_or_callback, CallbackQuery) else message_or_callback.chat
        if not _is_private_chat(chat):
            target = message_or_callback.message if isinstance(message_or_callback, CallbackQuery) else message_or_callback
            await target.answer(
                "Этот бот работает только в личном чате.\n"
                "Открой диалог с ботом один на один и повтори команду."
            )
            return False
        if user is None or user.id not in settings.allowed_user_ids:
            target = message_or_callback.message if isinstance(message_or_callback, CallbackQuery) else message_or_callback
            user_id = user.id if user is not None else "unknown"
            username = user.username if user is not None else None
            logger.warning(
                "telegram_access_denied",
                extra={"telegram_user_id": user_id, "telegram_username": username},
            )
            await target.answer(
                "Доступ запрещен.\n"
                f"Твой Telegram ID: <code>{user_id}</code>\n"
                "Добавь его в <code>TELEGRAM_ALLOWED_USER_IDS</code> и перезапусти worker."
            )
            return False
        return True

    @router.error()
    async def error_handler(event: ErrorEvent) -> bool:
        logger.exception("telegram_handler_failed", exc_info=event.exception)
        update = event.update
        if update.message is not None:
            await update.message.answer("Что-то пошло не так на этом шаге. Попробуй еще раз или начни заново через /new.")
        elif update.callback_query is not None and update.callback_query.message is not None:
            await update.callback_query.message.answer(
                "Что-то пошло не так на этом шаге. Попробуй еще раз или начни заново через /new."
            )
            await update.callback_query.answer()
        return True

    @router.message(Command("start"))
    async def start_handler(message: Message) -> None:
        if not await ensure_access(message):
            return
        await message.answer(_build_help_text())

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        if not await ensure_access(message):
            return
        await message.answer(_build_help_text())

    @router.message(Command("cancel"))
    async def cancel_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        await state.clear()
        await message.answer("Текущий диалог отменен.")

    @router.message(Command("new"))
    async def new_subscription_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        await state.clear()
        await state.update_data(
            currency=settings.travelpayouts_default_currency.upper(),
            check_interval_minutes=settings.default_check_interval_minutes,
            preferred_airlines=[],
            baggage_policy=BaggagePolicy.IGNORE.value,
        )
        await state.set_state(NewSubscriptionStates.name)
        await message.answer("Название подписки?")

    @router.message(Command("subscriptions"))
    @router.message(Command("subs"))
    async def subscriptions_handler(message: Message) -> None:
        if not await ensure_access(message):
            return
        subscriptions = await subscription_service.list_subscriptions(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
        )
        if not subscriptions:
            await message.answer("Подписок пока нет. Создай первую через /new")
            return

        for subscription in subscriptions:
            summary = _render_subscription(subscription)
            await message.answer(summary, reply_markup=subscription_actions_keyboard(subscription.id, subscription.enabled))

    @router.message(NewSubscriptionStates.name)
    async def name_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        await state.update_data(name=message.text.strip())
        await state.set_state(NewSubscriptionStates.origin)
        await message.answer("Откуда? Отправь IATA-код или название города.")

    @router.message(NewSubscriptionStates.origin)
    async def origin_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        normalized = await _resolve_airport_or_city_code(message.text, travelpayouts_client)
        if normalized is None:
            await message.answer("Не смог распознать origin. Попробуй IATA-код или более точное название.")
            return
        await state.update_data(origin_iata=normalized)
        await state.set_state(NewSubscriptionStates.destination)
        await message.answer("Куда? Отправь IATA-код или название города.")

    @router.message(NewSubscriptionStates.destination)
    async def destination_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        normalized = await _resolve_airport_or_city_code(message.text, travelpayouts_client)
        if normalized is None:
            await message.answer("Не смог распознать destination. Попробуй IATA-код или более точное название.")
            return
        await state.update_data(destination_iata=normalized)
        await state.set_state(NewSubscriptionStates.trip_type)
        await message.answer("Тип поездки?", reply_markup=trip_type_keyboard())

    @router.callback_query(NewSubscriptionStates.trip_type, F.data.startswith("new:trip:"))
    async def trip_type_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        trip_type = TripType.ONE_WAY if callback.data.endswith("one_way") else TripType.ROUND_TRIP
        await state.update_data(trip_type=trip_type.value)
        await state.set_state(NewSubscriptionStates.departure_mode)
        await callback.message.answer(
            "Как задать даты вылета?\n"
            "Можно выбрать через календарь или ввести вручную.",
            reply_markup=date_input_mode_keyboard("new:departure_mode"),
        )
        await callback.answer()

    @router.callback_query(NewSubscriptionStates.departure_mode, F.data.startswith("new:departure_mode:"))
    async def departure_mode_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        mode = callback.data.rsplit(":", 1)[-1]
        if mode == "manual":
            await state.update_data(calendar_context=None, calendar_mode=None, calendar_stage=None)
            await state.set_state(NewSubscriptionStates.departure_dates)
            await callback.message.answer(
                _manual_date_prompt("вылета", allow_retry=True),
                reply_markup=edit_dates_keyboard("departure"),
            )
        else:
            await _start_calendar_selection(
                message=callback.message,
                state=state,
                state_name=NewSubscriptionStates.departure_dates,
                context="departure",
                mode=mode,
            )
        await callback.answer()

    @router.message(NewSubscriptionStates.departure_dates)
    async def departure_dates_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        try:
            date_from, date_to = _parse_date_range(message.text)
        except ValueError:
            await message.answer(
                _manual_date_prompt("вылета", allow_retry=True),
                reply_markup=edit_dates_keyboard("departure"),
            )
            return

        await state.update_data(
            departure_date_from=date_from.isoformat(),
            departure_date_to=date_to.isoformat() if date_to else None,
            calendar_context=None,
            calendar_mode=None,
            calendar_stage=None,
        )
        await _after_departure_dates_selected(message=message, state=state)

    @router.callback_query(NewSubscriptionStates.return_mode, F.data.startswith("new:return:"))
    async def return_mode_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        if callback.data.endswith("dates"):
            await state.update_data(return_mode="dates")
            await state.set_state(NewSubscriptionStates.return_date_mode)
            await callback.message.answer(
                "Как задать даты возврата?\n"
                "Можно выбрать через календарь или ввести вручную.",
                reply_markup=date_input_mode_keyboard("new:return_date_mode"),
            )
        else:
            await state.update_data(return_mode="duration")
            await state.set_state(NewSubscriptionStates.duration)
            await callback.message.answer("Длительность поездки в днях: 3 или 3-7")
        await callback.answer()

    @router.callback_query(NewSubscriptionStates.return_date_mode, F.data.startswith("new:return_date_mode:"))
    async def return_date_mode_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        mode = callback.data.rsplit(":", 1)[-1]
        if mode == "manual":
            await state.update_data(calendar_context=None, calendar_mode=None, calendar_stage=None)
            await state.set_state(NewSubscriptionStates.return_dates)
            await callback.message.answer(
                _manual_date_prompt("возврата", allow_retry=True),
                reply_markup=edit_dates_keyboard("return"),
            )
        else:
            await _start_calendar_selection(
                message=callback.message,
                state=state,
                state_name=NewSubscriptionStates.return_dates,
                context="return",
                mode=mode,
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("new:calendar:"))
    async def calendar_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        _, _, context, action, *payload = callback.data.split(":")
        data = await state.get_data()
        if action == "noop":
            await callback.answer()
            return

        if data.get("calendar_context") != context:
            await callback.answer("Этот календарь уже устарел. Используй кнопку «Изменить даты».", show_alert=True)
            return

        mode = data.get("calendar_mode", "fixed")
        stage = data.get("calendar_stage", "from")
        from_key, to_key = _calendar_keys(context)

        if action == "cancel":
            await state.update_data(calendar_context=None, calendar_mode=None, calendar_stage=None)
            if context == "departure":
                await state.set_state(NewSubscriptionStates.departure_mode)
                await callback.message.answer(
                    "Выбор даты отменен.\nКак задать даты вылета?",
                    reply_markup=date_input_mode_keyboard("new:departure_mode"),
                )
            else:
                await state.set_state(NewSubscriptionStates.return_date_mode)
                await callback.message.answer(
                    "Выбор даты отменен.\nКак задать даты возврата?",
                    reply_markup=date_input_mode_keyboard("new:return_date_mode"),
                )
            await callback.answer()
            return

        if action == "nav":
            year = int(payload[0])
            month = int(payload[1])
            selected_from = date.fromisoformat(data[from_key]) if stage == "to" and data.get(from_key) else None
            await callback.message.edit_text(
                _calendar_prompt(context=context, mode=mode, stage=stage),
                reply_markup=calendar_keyboard(context=context, year=year, month=month, selected_from=selected_from),
            )
            await callback.answer()
            return

        if action != "pick":
            await callback.answer()
            return

        selected_date = date.fromisoformat(payload[0])
        if mode == "fixed":
            await state.update_data(
                **{
                    from_key: selected_date.isoformat(),
                    to_key: None,
                    "calendar_context": None,
                    "calendar_mode": None,
                    "calendar_stage": None,
                }
            )
            await callback.message.answer(f"Выбрана дата: <b>{_format_date(selected_date)}</b>")
            if context == "departure":
                await _after_departure_dates_selected(message=callback.message, state=state)
            else:
                await _after_return_dates_selected(message=callback.message, state=state)
            await callback.answer()
            return

        if stage == "from":
            await state.update_data(**{from_key: selected_date.isoformat(), to_key: None, "calendar_stage": "to"})
            await callback.message.edit_text(
                _calendar_prompt(context=context, mode=mode, stage="to"),
                reply_markup=calendar_keyboard(
                    context=context,
                    year=selected_date.year,
                    month=selected_date.month,
                    selected_from=selected_date,
                ),
            )
            await callback.answer(f"Начало диапазона: {_format_date(selected_date)}")
            return

        start_date = date.fromisoformat(data[from_key])
        if selected_date < start_date:
            await callback.answer("Конец диапазона не может быть раньше начала.", show_alert=True)
            return

        await state.update_data(
            **{
                to_key: selected_date.isoformat(),
                "calendar_context": None,
                "calendar_mode": None,
                "calendar_stage": None,
            }
        )
        await callback.message.answer(
            f"Выбран диапазон: <b>{_format_date(start_date)} - {_format_date(selected_date)}</b>"
        )
        if context == "departure":
            await _after_departure_dates_selected(message=callback.message, state=state)
        else:
            await _after_return_dates_selected(message=callback.message, state=state)
        await callback.answer()

    @router.message(NewSubscriptionStates.return_dates)
    async def return_dates_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        try:
            date_from, date_to = _parse_date_range(message.text)
        except ValueError:
            await message.answer(
                _manual_date_prompt("возврата", allow_retry=True),
                reply_markup=edit_dates_keyboard("return"),
            )
            return
        await state.update_data(
            return_date_from=date_from.isoformat(),
            return_date_to=date_to.isoformat() if date_to else None,
            calendar_context=None,
            calendar_mode=None,
            calendar_stage=None,
        )
        await _after_return_dates_selected(message=message, state=state)

    @router.message(NewSubscriptionStates.duration)
    async def duration_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        try:
            min_days, max_days = _parse_duration_range(message.text)
        except ValueError:
            await message.answer("Неверный формат. Используй 3 или 3-7")
            return
        await state.update_data(min_trip_duration_days=min_days, max_trip_duration_days=max_days)
        await state.set_state(NewSubscriptionStates.max_price)
        await message.answer(_max_price_prompt(), reply_markup=edit_dates_keyboard("departure"))

    @router.message(NewSubscriptionStates.max_price)
    async def max_price_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        try:
            parsed_price = _parse_price_input(message.text)
        except (InvalidOperation, ValueError):
            await message.answer(_max_price_prompt())
            return
        await state.update_data(max_price=str(parsed_price) if parsed_price is not None else None)
        await state.set_state(NewSubscriptionStates.direct_only)
        await message.answer("Только прямые рейсы?", reply_markup=yes_no_keyboard("new:direct"))

    @router.callback_query(NewSubscriptionStates.direct_only, F.data.startswith("new:direct:"))
    async def direct_only_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        await state.update_data(
            direct_only=callback.data.endswith("yes"),
            check_interval_minutes=settings.default_check_interval_minutes,
            preferred_airlines=[],
            baggage_policy=BaggagePolicy.IGNORE.value,
            currency=settings.travelpayouts_default_currency.upper(),
        )
        await state.set_state(NewSubscriptionStates.confirm)
        await callback.message.answer(_render_state_summary(await state.get_data()), reply_markup=confirm_keyboard())
        await callback.answer()

    @router.callback_query(F.data.startswith("new:edit:"))
    async def edit_dates_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        context = callback.data.rsplit(":", 1)[-1]
        await state.update_data(calendar_context=None, calendar_mode=None, calendar_stage=None)

        if context == "departure":
            await state.update_data(
                departure_date_from=None,
                departure_date_to=None,
                return_mode=None,
                return_date_from=None,
                return_date_to=None,
                min_trip_duration_days=None,
                max_trip_duration_days=None,
            )
            await state.set_state(NewSubscriptionStates.departure_mode)
            await callback.message.answer(
                "Давай выберем даты вылета заново.",
                reply_markup=date_input_mode_keyboard("new:departure_mode"),
            )
            await callback.answer()
            return

        if context == "return":
            await state.update_data(return_mode="dates", return_date_from=None, return_date_to=None)
            await state.set_state(NewSubscriptionStates.return_date_mode)
            await callback.message.answer(
                "Давай выберем даты возврата заново.",
                reply_markup=date_input_mode_keyboard("new:return_date_mode"),
            )
            await callback.answer()
            return

        await callback.answer()

    @router.callback_query(NewSubscriptionStates.confirm, F.data == "new:confirm:create")
    async def confirm_create_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        data = await state.get_data()
        payload = SubscriptionCreate(
            name=data["name"],
            origin_iata=data["origin_iata"],
            destination_iata=data["destination_iata"],
            trip_type=TripType(data["trip_type"]),
            departure_date_from=date.fromisoformat(data["departure_date_from"]),
            departure_date_to=date.fromisoformat(data["departure_date_to"]) if data.get("departure_date_to") else None,
            return_date_from=date.fromisoformat(data["return_date_from"]) if data.get("return_date_from") else None,
            return_date_to=date.fromisoformat(data["return_date_to"]) if data.get("return_date_to") else None,
            min_trip_duration_days=data.get("min_trip_duration_days"),
            max_trip_duration_days=data.get("max_trip_duration_days"),
            max_price=Decimal(data["max_price"]) if data.get("max_price") else None,
            currency=data.get("currency", settings.travelpayouts_default_currency.upper()),
            market=settings.travelpayouts_default_market,
            direct_only=data["direct_only"],
            baggage_policy=BaggagePolicy(data["baggage_policy"]),
            preferred_airlines=data.get("preferred_airlines", []),
            check_interval_minutes=data["check_interval_minutes"],
        )
        subscription_id = await subscription_service.create_subscription(
            telegram_user_id=callback.from_user.id,
            username=callback.from_user.username,
            payload=payload,
        )
        await state.clear()
        await callback.message.answer(
            f"Подписка создана: {subscription_id}\n"
            "Первая проверка будет запущена автоматически в ближайшую минуту."
        )
        await callback.answer()

    @router.callback_query(NewSubscriptionStates.confirm, F.data == "new:confirm:cancel")
    async def confirm_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        await state.clear()
        await callback.message.answer("Создание подписки отменено.")
        await callback.answer()

    @router.callback_query(F.data.startswith("sub:"))
    async def subscription_action_handler(callback: CallbackQuery) -> None:
        if not await ensure_access(callback):
            return
        _, action, subscription_id = callback.data.split(":", 2)
        subscription = await subscription_service.get_subscription(
            telegram_user_id=callback.from_user.id,
            username=callback.from_user.username,
            subscription_id=subscription_id,
        )
        if subscription is None:
            await callback.answer("Подписка не найдена", show_alert=True)
            return

        if action == "enable":
            await subscription_service.set_enabled(
                telegram_user_id=callback.from_user.id,
                username=callback.from_user.username,
                subscription_id=subscription_id,
                enabled=True,
            )
            await callback.message.answer("Подписка включена.")
        elif action == "disable":
            await subscription_service.set_enabled(
                telegram_user_id=callback.from_user.id,
                username=callback.from_user.username,
                subscription_id=subscription_id,
                enabled=False,
            )
            await callback.message.answer("Подписка выключена.")
        elif action == "delete":
            await subscription_service.delete(
                telegram_user_id=callback.from_user.id,
                username=callback.from_user.username,
                subscription_id=subscription_id,
            )
            await callback.message.answer("Подписка удалена.")
        elif action == "check":
            await callback.message.answer("Запускаю ручную проверку...")
            result = await alert_service.run_subscription_check(subscription_id=subscription_id, trigger=CheckTrigger.MANUAL)
            await callback.message.answer(
                f"Проверка завершена.\nСтатус: {result.status.value}\n"
                f"Найдено офферов: {result.offers_found}\nОтправлено уведомлений: {result.notifications_sent}"
            )
        elif action == "latest":
            items = await subscription_service.list_recent_offers(
                telegram_user_id=callback.from_user.id,
                username=callback.from_user.username,
                subscription_id=subscription_id,
                limit=5,
            )
            if not items:
                await callback.message.answer("По этой подписке пока нет сохраненных офферов.")
            else:
                lines = []
                for offer, price in items:
                    lines.append(
                        f"{offer.origin_iata}->{offer.destination_iata} | "
                        f"{offer.departure_at.date().isoformat() if offer.departure_at else '-'} | "
                        f"{price.price_amount} {price.currency}"
                    )
                await callback.message.answer("Последние варианты:\n" + "\n".join(lines))

        await callback.answer()

    return router


def _render_subscription(subscription) -> str:
    status = "включена" if subscription.enabled else "выключена"
    return (
        f"<b>{subscription.name}</b>\n"
        f"{subscription.origin_iata} -> {subscription.destination_iata}\n"
        f"Тип: {_render_trip_type(subscription.trip_type.value)}\n"
        f"Цена до: {_format_money(subscription.max_price)} {subscription.currency}\n"
        f"Прямые: {'да' if subscription.direct_only else 'нет'}\n"
        f"Интервал: {subscription.check_interval_minutes} мин\n"
        f"Статус: {status}"
    )


async def _resolve_airport_or_city_code(raw_text: str, client: TravelpayoutsRestClient) -> str | None:
    text = raw_text.strip().upper()
    if len(text) == 3 and text.isalpha():
        return text
    options = await client.autocomplete_places(raw_text.strip())
    for option in options[:5]:
        code = option.get("code")
        if code and len(code) == 3:
            return code.upper()
    return None


def _parse_date_range(value: str) -> tuple[date, date | None]:
    tokens = re.findall(r"\d{4}-\d{2}-\d{2}|\d{2}[./]\d{2}[./]\d{4}", value.strip())
    if not tokens:
        raise ValueError("Date value is missing")
    if len(tokens) > 2:
        raise ValueError("Too many dates in input")

    start_date = _parse_single_date(tokens[0])
    if len(tokens) == 1:
        return start_date, None

    end_date = _parse_single_date(tokens[1])
    if end_date < start_date:
        raise ValueError("End date must be after start date")
    return start_date, end_date


def _parse_duration_range(value: str) -> tuple[int, int | None]:
    text = value.strip()
    if "-" not in text:
        days = int(text)
        return days, days
    start, end = [part.strip() for part in text.split("-", 1)]
    start_days = int(start)
    end_days = int(end)
    if end_days < start_days:
        raise ValueError("Duration range is invalid")
    return start_days, end_days


def _render_state_summary(data: dict) -> str:
    currency = data.get("currency", "RUB")
    interval = data.get("check_interval_minutes", 60)
    parts = [
        "<b>Проверь подписку</b>",
        f"Название: {data['name']}",
        f"Маршрут: {data['origin_iata']} -> {data['destination_iata']}",
        f"Тип: {_render_trip_type(data['trip_type'])}",
        f"Вылет: {_format_date_range(data['departure_date_from'], data.get('departure_date_to'))}",
    ]
    if data.get("return_date_from"):
        parts.append(f"Возврат: {_format_date_range(data['return_date_from'], data.get('return_date_to'))}")
    if data.get("min_trip_duration_days"):
        parts.append(
            f"Длительность: {data['min_trip_duration_days']} .. {data.get('max_trip_duration_days') or data['min_trip_duration_days']} дней"
        )
    parts.extend(
        [
            f"Макс. цена: {_format_money(data.get('max_price'))}",
            f"Прямые: {'да' if data['direct_only'] else 'нет'}",
            f"Проверка: каждые {interval} минут",
            f"Валюта: {currency} (по умолчанию)",
        ]
    )
    return "\n".join(parts)


def _build_help_text() -> str:
    return (
        "Бот ищет дешевые авиабилеты по твоим подпискам и присылает уведомления.\n\n"
        "<b>Основные команды</b>\n"
        "/new - создать новую подписку\n"
        "/subscriptions - показать мои подписки\n"
        "/subs - короткая команда для списка подписок\n"
        "/help - показать инструкцию\n"
        "/cancel - отменить текущий диалог\n\n"
        "<b>Как пользоваться</b>\n"
        "1. Напиши /new\n"
        "2. Укажи маршрут, даты и лимит цены\n"
        "3. Бот начнет проверять цены автоматически\n\n"
        "<b>Подсказки</b>\n"
        "• Город можно вводить названием или IATA-кодом, например <code>MOW</code>, <code>BKK</code>, <code>NHA</code>\n"
        "• Максимальную цену можно писать как <code>45000</code>, <code>45 000</code> или просто <code>45</code> для 45 000 ₽\n"
        "• Валюта в боте фиксирована: <b>RUB</b>\n"
        "• Проверка выполняется автоматически каждые <b>60 минут</b>\n"
        "• Если ошибся в датах, используй кнопку <b>Изменить даты</b> в следующем сообщении"
    )


def _is_private_chat(chat: Chat | None) -> bool:
    return bool(chat and chat.type == "private")


async def _after_departure_dates_selected(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data["trip_type"] == TripType.ONE_WAY.value:
        await state.set_state(NewSubscriptionStates.max_price)
        await message.answer(_max_price_prompt(), reply_markup=edit_dates_keyboard("departure"))
        return

    await state.set_state(NewSubscriptionStates.return_mode)
    await message.answer("Как задавать обратный путь?", reply_markup=return_mode_keyboard(include_edit_departure=True))


async def _after_return_dates_selected(message: Message, state: FSMContext) -> None:
    await state.set_state(NewSubscriptionStates.max_price)
    await message.answer(_max_price_prompt(), reply_markup=edit_dates_keyboard("departure", "return"))


async def _start_calendar_selection(
    *,
    message: Message,
    state: FSMContext,
    state_name,
    context: str,
    mode: str,
) -> None:
    today = date.today()
    await state.update_data(calendar_context=context, calendar_mode=mode, calendar_stage="from")
    await state.set_state(state_name)
    await message.answer(
        _calendar_prompt(context=context, mode=mode, stage="from"),
        reply_markup=calendar_keyboard(context=context, year=today.year, month=today.month),
    )


def _calendar_keys(context: str) -> tuple[str, str]:
    if context == "departure":
        return "departure_date_from", "departure_date_to"
    return "return_date_from", "return_date_to"


def _manual_date_prompt(label: str, *, allow_retry: bool = False) -> str:
    text = (
        f"Введи дату {label}.\n"
        "Поддерживаются оба формата:\n"
        "• 01.06.2026\n"
        "• 2026-06-01\n"
        "Для диапазона можно так:\n"
        "• 01.06.2026 - 12.06.2026\n"
        "• 2026-06-01:2026-06-12"
    )
    if allow_retry:
        text += "\n\nЕсли ошибся, нажми кнопку ниже и выбери даты заново."
    return text


def _max_price_prompt() -> str:
    return (
        "Максимальная цена?\n"
        "Можно ввести:\n"
        "• 45000\n"
        "• 45 000\n"
        "• 45 или 45к, если удобно считать тысячами\n"
        "• - если лимита нет"
    )


def _calendar_prompt(*, context: str, mode: str, stage: str) -> str:
    label = "вылета" if context == "departure" else "возврата"
    if mode == "fixed":
        return f"Выбери дату {label} в календаре."
    if stage == "from":
        return f"Выбери первую дату {label}."
    return f"Теперь выбери последнюю дату {label}."


def _parse_single_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("Date format is invalid")


def _parse_price_input(raw_value: str | None) -> Decimal | None:
    value = (raw_value or "").strip().lower().replace(" ", "")
    if value == "-":
        return None
    if not value:
        raise ValueError("Price is required")

    multiplier = Decimal("1")
    if value.endswith(("k", "к")):
        multiplier = Decimal("1000")
        value = value[:-1]

    normalized = value.replace(",", ".")
    amount = Decimal(normalized)

    if normalized.isdigit() and 0 < int(normalized) < 1000:
        multiplier = Decimal("1000")

    amount *= multiplier
    if amount <= 0:
        raise ValueError("Price must be positive")

    if amount == amount.to_integral_value():
        return amount.quantize(Decimal("1"))
    return amount.quantize(Decimal("0.01"))


def _format_date(value: date | str) -> str:
    current = date.fromisoformat(value) if isinstance(value, str) else value
    return current.strftime("%d.%m.%Y")


def _format_date_range(date_from: date | str, date_to: date | str | None) -> str:
    start = _format_date(date_from)
    end = _format_date(date_to) if date_to else start
    return f"{start} - {end}"


def _format_money(value: Decimal | str | None) -> str:
    if value is None:
        return "-"
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if amount == amount.to_integral_value():
        return f"{int(amount):,}".replace(",", " ")
    return f"{amount:,.2f}".replace(",", " ").rstrip("0").rstrip(".")


def _render_trip_type(value: str) -> str:
    return "в одну сторону" if value == TripType.ONE_WAY.value else "туда-обратно"


def _render_baggage_policy(value: str) -> str:
    labels = {
        BaggagePolicy.IGNORE.value: "не важно",
        BaggagePolicy.OPTIONAL.value: "желательно",
        BaggagePolicy.REQUIRED.value: "обязательно",
    }
    return labels.get(value, value)
